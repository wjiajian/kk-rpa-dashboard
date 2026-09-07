from copy import deepcopy
from sqlalchemy import select
import pytest

from rpa_console.control import BUDGET, Conflict, Control, remaining
from rpa_console.storage import Base, Database, Event, Operation, Robot, Run


@pytest.fixture
def env(tmp_path):
    db = Database("sqlite:///" + str(tmp_path / "control.db"))
    Base.metadata.create_all(db.engine)
    now = [1000.0]
    c = Control(db, lambda: now[0])
    robot = c.add_robot("robot")
    c.reconcile(robot["id"], {"deployments": [{"app_id": "app", "version": "1"}], "requests": {}})
    run = c.create_run(robot["id"], {"app_id": "app", "version": "1", "account_id": "A", "inputs": {"date": "2099-01-01"}, "download_dir": "/downloads"}, "demo")
    return Harness(c, db, robot["id"], run, now)


class Harness:
    def __init__(self, c, db, robot, run, now):
        self.c, self.db, self.robot, self.run, self.now = c, db, robot, run, now
        self.seq = 0
    def state(self):
        with self.db.transaction() as s:
            return deepcopy(s.get(Run, self.run).data)
    def owned(self):
        with self.db.transaction() as s:
            return s.get(Robot, self.robot).active_run
    def send(self, kind, data=None, attempt=None, **extra):
        self.seq += 1
        message = {"type": kind, "console_run_id": self.run, "execution_attempt_id": attempt or self.state()["attempt_id"], "seq": self.seq, "at": self.now[0], "data": data or {}, **extra}
        self.c.accept_message(self.robot, message)
        return message
    def result(self, command, status="succeeded", result=None):
        return self.send("result", attempt=command["execution_attempt_id"], request_id=command["request_id"], status=status, result=result or {})
    def start(self):
        self.c.tick({self.robot})
        command = self.c.commands(self.robot)[0]
        self.send("program_started", {"local_run_id": "local-1"})
        return command
    def recover(self):
        start = self.start()
        self.send("attempt_finished", {"local_run_id": "local-1", "status": "failed", "recoverable": True})
        self.result(start)
        self.c.tick({self.robot})
        op = self.c.commands(self.robot)[0]
        self.send("recovery_started")
        self.result(op)
        return self.c.claim(self.run, {self.robot})
    def tool(self, job, action, params=None, request="tool-1"):
        self.c.tool(self.run, job["lease"], job["execution_attempt_id"], request, action, params or {}, {self.robot})
        return self.c.commands(self.robot)[0]


def test_success_never_triggers_agent_and_only_releases_on_end(env):
    command = env.start()
    env.send("attempt_finished", {"local_run_id": "local-1", "status": "succeeded"})
    env.result(command)
    env.c.tick({env.robot})
    assert env.owned() == env.run
    assert env.c.commands(env.robot) == []
    env.send("ended")
    assert env.state()["status"] == "succeeded"
    assert env.owned() is None
    env.c.request_stop(env.run)
    assert env.state()["status"] == "succeeded"


def test_budget_survives_second_attempt_long_program_and_restart(env):
    job = env.recover()
    env.now[0] += 360
    env.c.agent_state(env.run, job["lease"], True)  # Expired leases cannot renew.
    job = env.c.claim(env.run, {env.robot})
    op = env.tool(job, "resume", {"from_step": "S2"})
    new_attempt = env.state()["attempt_id"]
    assert op["execution_attempt_id"] != new_attempt
    assert op["next_attempt_id"] == new_attempt
    env.send("program_started", {"local_run_id": "local-2"})
    env.now[0] += 4000
    env.c = Control(env.db, lambda: env.now[0])
    assert remaining(env.state(), env.now[0]) == 540
    env.send("attempt_finished", {"local_run_id": "local-2", "status": "failed", "recoverable": True})
    env.result(op)
    env.c.tick({env.robot})
    reopen = env.c.commands(env.robot)[0]
    assert reopen["params"]["local_run_id"] == "local-2"
    assert reopen["params"]["remaining_seconds"] == 540
    assert "locator_overrides" not in reopen["params"]
    env.send("recovery_started")
    env.result(reopen)
    env.now[0] += 540
    env.c.tick({env.robot})
    assert env.state()["stop_reason"] == "budget_exhausted"
    assert env.owned() == env.run
    env.send("ended")
    assert env.state()["status"] == "failed"


def test_duplicate_failure_and_operation_do_not_repeat(env):
    job = env.recover()
    op = env.tool(job, "act", {"operation": "click", "target": "button"})
    assert env.c.commands(env.robot) == []
    env.c.tool(env.run, job["lease"], job["execution_attempt_id"], op["request_id"], "act", op["params"], {env.robot})
    assert env.c.commands(env.robot) == []
    with pytest.raises(Conflict):
        env.c.tool(env.run, job["lease"], job["execution_attempt_id"], op["request_id"], "act", {"operation": "download"}, {env.robot})
    message = env.result(op)
    env.c.accept_message(env.robot, message)
    with env.db.transaction() as s:
        assert len(list(s.scalars(select(Operation).where(Operation.id == op["request_id"])))) == 1


def test_lost_reply_reconnect_never_resends_accepted_click(env):
    job = env.recover()
    op = env.tool(job, "act", {"operation": "click", "target": "button"})
    env.c.disconnect(env.robot)
    env.now[0] += 120
    env.c.reconcile(env.robot, {"active_run": env.run, "execution_attempt_id": job["execution_attempt_id"],
        "phase": "recovery", "journal_complete": True, "requests": {op["request_id"]: "succeeded"}})
    assert env.c.commands(env.robot) == []
    with pytest.raises(Conflict): env.c.claim(env.run, {env.robot})
    env.result(op)
    assert remaining(env.state(), env.now[0]) == 780
    env.c.claim(env.run, {env.robot})


def test_unknown_action_never_releases_robot(env):
    job = env.recover()
    op = env.tool(job, "act", {"operation": "download", "target": "download"})
    env.result(op, "unknown")
    assert env.state()["status"] == "uncertain"
    env.c.request_stop(env.run)
    env.c.tick({env.robot})
    assert env.owned() == env.run
    with pytest.raises(Conflict): env.c.claim(env.run, {env.robot})


def test_revoke_stops_active_run_and_rejects_new_tools(env):
    job = env.recover()
    env.c.revoke(env.robot)
    with pytest.raises(Conflict): env.tool(job, "observe")
    env.c.tick({env.robot})
    assert env.c.commands(env.robot)[0]["action"] == "stop"
    assert env.owned() == env.run
    env.send("ended")
    assert env.owned() is None


def test_wrong_robot_old_attempt_and_arbitrary_tools_rejected(env):
    job = env.recover()
    for action in ("bash", "python", "write", "edit", "install"):
        with pytest.raises(Conflict): env.tool(job, action)
    with pytest.raises(Conflict):
        env.c.tool(env.run, job["lease"], "stale", "x", "observe", {}, {env.robot})
    with pytest.raises(Conflict):
        env.c.accept_message("another-robot", {"console_run_id": env.run, "seq": 99, "type": "ended"})


def test_preparation_failure_does_not_open_recovery(env):
    command = env.start()
    env.send("attempt_finished", {"local_run_id": "local-1", "status": "failed", "recoverable": False})
    env.result(command)
    env.c.tick({env.robot})
    env.c.tick({env.robot})
    assert env.c.commands(env.robot)[0]["action"] == "stop"


def test_queue_keeps_same_robot_until_confirmation(env):
    env.recover()
    second = env.c.create_run(env.robot, env.state()["snapshot"], "next")
    env.c.request_stop(env.run)
    env.c.tick({env.robot})
    assert env.owned() == env.run
    env.send("ended")
    env.c.tick({env.robot})
    assert env.owned() == second


def test_unaccepted_request_may_only_be_sent_after_explicit_journal_absence(env):
    job = env.recover()
    op = env.tool(job, "observe")
    env.c.disconnect(env.robot)
    assert env.c.commands(env.robot) == []
    env.c.reconcile(env.robot, {"active_run": env.run, "phase": "recovery", "execution_attempt_id": job["execution_attempt_id"],
        "journal_complete": True, "requests": {}})
    commands = env.c.commands(env.robot)
    assert [c["request_id"] for c in commands] == [op["request_id"]]


def test_resume_rejection_keeps_source_and_budget(env):
    job = env.recover()
    op = env.tool(job, "resume", {"from_step": "invalid"})
    env.result(op, "failed", {"recovery_active": True})
    assert env.state()["attempt_id"] == job["execution_attempt_id"]
    assert env.state()["phase"] == "recovery"
    assert env.state()["recovery_since"] == 1000
