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
    run = c.create_run(robot["id"], {"app_id": "app", "version": "1", "inputs": {"date": "2099-01-01"}, "download_dir": "/downloads"}, "demo")
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
        if action in {"resume", "give_up"}:
            params = {"summary": "已检查现场，提交本轮接管结果。", **(params or {})}
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


def test_environment_failure_is_visible_without_agent_tool_logs(env):
    env.c.tick({env.robot})
    start = env.c.commands(env.robot)[0]
    env.result(start, "failed", {"phase": "prepare", "error": "本机未部署指定应用版本"})
    with env.db.transaction() as s:
        events = [e.data for e in s.scalars(select(Event).where(Event.run_id == env.run))]
    failure = next(e for e in events if e["kind"] == "preparation_failed")
    assert failure["details"]["error"] == "本机未部署指定应用版本"
    assert not any(e["kind"] in {"operation", "agent_summary"} for e in events)


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


def test_three_complete_recovery_rounds_stop_before_fourth_and_preserve_time_budget(env):
    job = env.recover()
    for number in range(1, 4):
        assert job["recovery_round"] == number
        assert job["max_recovery_rounds"] == 3
        # Several operations in one takeover do not consume extra rounds.
        for action in ("context", "observe", "act"):
            env.result(env.tool(job, action, request=f"{number}-{action}"))
        env.now[0] += 10
        resume = env.tool(job, "resume", {"from_step": "S2", "summary": f"第 {number} 轮：已提交 S2，等待原程序校验。"}, request=f"resume-{number}")
        env.send("program_started", {"local_run_id": f"local-{number + 1}"})
        env.now[0] += 4000  # Program time is still outside the 900-second budget.
        env.send("attempt_finished", {"local_run_id": f"local-{number + 1}", "status": "failed", "recoverable": True})
        env.result(resume)
        env.c = Control(env.db, lambda: env.now[0])
        env.c.tick({env.robot})
        if number < 3:
            opening = env.c.commands(env.robot)[0]
            assert opening["action"] == "open_recovery"
            env.send("recovery_started")
            env.result(opening)
            job = env.c.claim(env.run, {env.robot})
    env.c.tick({env.robot})
    assert env.state()["stop_reason"] == "rounds_exhausted"
    assert remaining(env.state(), env.now[0]) == BUDGET - 30
    assert [c["action"] for c in env.c.commands(env.robot)] == ["stop"]
    with pytest.raises(Conflict):
        env.c.claim(env.run, {env.robot})
    assert env.owned() == env.run
    env.send("ended")
    assert env.owned() is None
    with env.db.transaction() as s:
        events = [e.data for e in s.scalars(select(Event).where(Event.run_id == env.run))]
    assert len([e for e in events if e["kind"] == "agent_summary"]) == 3
    assert not any(e["kind"] == "operation" for e in events)


def test_expired_or_disconnected_agent_cannot_reset_the_round_limit(env):
    job = env.recover()
    for number in (2, 3):
        env.c.disconnect(env.robot)
        env.c.reconcile(env.robot, {"active_run": env.run, "phase": "recovery",
            "execution_attempt_id": job["execution_attempt_id"], "journal_complete": True, "requests": {}})
        env.c = Control(env.db, lambda: env.now[0])
        job = env.c.claim(env.run, {env.robot})
        assert job["recovery_round"] == number
    env.now[0] += 31
    with pytest.raises(Conflict, match="3 轮"):
        env.c.claim(env.run, {env.robot})
    env.c.tick({env.robot})
    assert env.state()["stop_reason"] == "rounds_exhausted"
    assert len(env.state()["recovery_rounds"]) == 3


def test_resume_requires_one_final_summary_and_duplicate_does_not_repeat_it(env):
    job = env.recover()
    with pytest.raises(Conflict, match="总结"):
        env.tool(job, "resume", {"summary": " ", "from_step": "S2"})
    assert env.state()["phase"] == "recovery"
    summary = "已恢复报表页并提交 S2，等待原校验。"
    op = env.tool(job, "resume", {"summary": summary, "from_step": "S2"})
    env.c.tool(env.run, job["lease"], job["execution_attempt_id"], op["request_id"], "resume", op["params"], {env.robot})
    with env.db.transaction() as s:
        events = [e.data for e in s.scalars(select(Event).where(Event.run_id == env.run)) if e.data["kind"] == "agent_summary"]
    assert len(events) == 1
    assert events[0]["message"] == f"Agent 第 1 轮接管总结\n{summary}"


def test_budget_exhaustion_stops_first_round_and_records_its_conclusion(env):
    env.recover()
    env.now[0] += BUDGET
    env.c.tick({env.robot})
    assert env.state()["stop_reason"] == "budget_exhausted"
    assert len(env.state()["recovery_rounds"]) == 1
    assert "900 秒" in env.state()["recovery_rounds"][0]["summary"]


def test_agent_activity_shows_progress_without_dom_or_tool_parameters(env):
    job = env.recover()
    observe = env.tool(job, "observe", {"target": "private-locator"}, request="observe")
    with env.db.transaction() as s:
        activity = [e.data for e in s.scalars(select(Event).where(Event.run_id == env.run)) if e.data["kind"] == "agent_activity"]
    assert activity[-1]["message"] == "第 1 轮 · 观察页面：执行中"
    result = env.result(observe, result={"nodes": [{"locator": "private-locator", "text": "large DOM dump"}], "text": "page details"})
    env.c.accept_message(env.robot, result)
    click = env.tool(job, "act", {"operation": "click", "target": "private-locator", "value": "private-value"}, request="click")
    env.result(click, "failed", {"error": "raw exception with page details"})
    with env.db.transaction() as s:
        activity = [e.data for e in s.scalars(select(Event).where(Event.run_id == env.run)) if e.data["kind"] == "agent_activity"]
        assert s.get(Operation, observe["request_id"]).data["result"]["text"] == "page details"
    assert sum(e["message"] == "第 1 轮 · 观察页面：已完成" for e in activity) == 1
    assert activity[-1]["message"] == "第 1 轮 · 点击页面控件：失败，等待处理"
    assert all(e["details"] == {} for e in activity)
    assert all(value not in str(activity) for value in ("private-locator", "private-value", "large DOM dump", "page details"))


def test_observation_failure_log_identifies_error_without_raw_dom(env):
    job = env.recover()
    command = env.tool(job, "observe", {}, request="observe")
    env.result(command, result={"observation_error": "TypeError", "observation_stage": "dom", "text": "private DOM"})
    command = env.tool(job, "observe", {}, request="observe-again")
    env.result(command, result={"observation_error": "KeyError", "observation_stage": "target", "text": "private DOM"})
    with env.db.transaction() as s:
        activity = [e.data for e in s.scalars(select(Event).where(Event.run_id == env.run)) if e.data["kind"] == "agent_activity"]
    assert any("页面读取失败（TypeError）" in e["message"] for e in activity)
    assert "观察目标无效（KeyError），请先观察整页" in activity[-1]["message"]
    assert "private DOM" not in str(activity)
