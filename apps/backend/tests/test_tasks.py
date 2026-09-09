from copy import deepcopy
from datetime import datetime

from cryptography.fernet import Fernet
import pytest
from sqlalchemy import select

from rpa_console.control import Control, Conflict
from rpa_console.credentials import CredentialStore
from rpa_console.storage import Base, Database, Run, TaskCredential
from rpa_console.tasks import Tasks, ZONE, cron_times

SCHEMA = {"type": "object", "required": ["date"], "additionalProperties": False,
          "properties": {"date": {"type": "string", "format": "date"}}}
SECRETS = {"username": "ACCOUNT_TEST", "password": "SECRET_PASSWORD"}


@pytest.fixture
def plans(tmp_path):
    db = Database("sqlite:///" + str(tmp_path / "plans.db"))
    Base.metadata.create_all(db.engine)
    now = [datetime(2026, 9, 8, 7, 59, tzinfo=ZONE).timestamp()]
    control = Control(db, lambda: now[0], CredentialStore(Fernet.generate_key()))
    robot = control.add_robot("robot")
    control.reconcile(robot["id"], {"deployments": [{"app_id": "app", "version": "1", "input_schema": SCHEMA}]})
    tasks = Tasks(control)
    config = {"name": "daily", "robot_id": robot["id"], "app_id": "app", "version": "1",
              "input_bindings": {"date": {"kind": "relative_date", "offset_days": -1}}, "download_dir": None,
              "schedule": {"enabled": True, "cron": "0 8 * * *", "timezone": "Asia/Shanghai"}}
    task = tasks.save(config, SECRETS)
    return tasks, now, config, task


def test_atomic_trigger_keeps_inputs_and_credentials_after_plan_edit(plans):
    tasks, now, config, task = plans
    first = tasks.trigger(task["id"], "click-one")
    assert tasks.trigger(task["id"], "click-one") == first
    changed = deepcopy(config)
    changed["input_bindings"]["date"]["offset_days"] = 0
    updated = tasks.save(changed, {**SECRETS, "password": "NEW_PASSWORD"}, task["id"], 1)
    assert updated["revision"] == 2
    with pytest.raises(Conflict, match="刷新"):
        tasks.save(config, None, task["id"], 1)
    assert tasks.trigger(task["id"], "click-one") == first
    second = tasks.trigger(task["id"], "click-two")
    with tasks.db.transaction() as s:
        assert s.get(Run, first).data["snapshot"]["inputs"] == {"date": "2026-09-07"}
        assert s.get(Run, second).data["snapshot"]["inputs"] == {"date": "2026-09-08"}
        assert tasks.credentials.read(s, first) == SECRETS
        assert tasks.credentials.read(s, second)["password"] == "NEW_PASSWORD"
        assert "SECRET_PASSWORD" not in s.get(TaskCredential, task["id"]).encrypted
        assert len(list(s.scalars(select(Run)))) == 2


def test_due_slot_fixed_and_restarts_skip_missed_runs(plans):
    tasks, now, config, task = plans
    now[0] = datetime(2026, 9, 8, 8, 5, tzinfo=ZONE).timestamp()
    tasks.tick()
    tasks.tick()
    with tasks.db.transaction() as s:
        runs = list(s.scalars(select(Run)))
        assert len(runs) == 1
        assert runs[0].data["scheduled_for"] == datetime(2026, 9, 8, 8, tzinfo=ZONE).timestamp()
        assert runs[0].data["snapshot"]["inputs"]["date"] == "2026-09-07"
    now[0] = datetime(2026, 9, 10, 9, tzinfo=ZONE).timestamp()
    tasks.reset_after_restart()
    tasks.tick()
    with tasks.db.transaction() as s:
        assert len(list(s.scalars(select(Run)))) == 1
        assert tasks.get(s, task["id"]).next_run_at > now[0]


def test_disabled_schedule_keeps_queue_and_invalid_schema_pauses(plans):
    tasks, now, config, task = plans
    run = tasks.trigger(task["id"], "first")
    tasks.schedule(task["id"], 1, {"enabled": False, "cron": "0 8 * * *"})
    now[0] += 3600
    tasks.tick()
    with tasks.db.transaction() as s:
        assert s.get(Run, run).data["status"] == "queued"
    tasks.schedule(task["id"], 2, {"enabled": True, "cron": "* * * * *"})
    tasks.control.reconcile(config["robot_id"], {"deployments": []})
    now[0] += 60
    tasks.tick()
    with tasks.db.transaction() as s:
        row = tasks.get(s, task["id"])
        assert not row.enabled
        assert row.data["last_error"]
        assert len(list(s.scalars(select(Run)))) == 1


def test_cron_rejects_seconds_and_impossible_dates():
    for expression in ("* * * * * *", "0 8 31 2 *", "bad"):
        with pytest.raises(Conflict):
            cron_times(expression, 0)
    times = cron_times("0 8 * * *", datetime(2026, 9, 8, 7, tzinfo=ZONE).timestamp())
    assert datetime.fromtimestamp(times[0], ZONE).hour == 8


def test_maintenance_persists_blocks_triggers_and_preserves_queue(plans):
    from rpa_console.maintenance import MaintenanceError, set_mode, status
    from rpa_console.storage import Robot, Task
    tasks, now, config, task = plans
    run = tasks.trigger(task['id'], 'before-maintenance')
    set_mode(tasks.db, True)
    assert status(tasks.db)['maintenance'] is True
    with pytest.raises(MaintenanceError):
        tasks.trigger(task['id'], 'during-maintenance')
    with pytest.raises(MaintenanceError):
        tasks.control.create_run(config['robot_id'], {'app_id': 'app', 'version': '1', 'inputs': {'date': '2026-09-08'}}, 'temporary', credentials=SECRETS)
    now[0] = datetime(2026, 9, 10, 9, tzinfo=ZONE).timestamp()
    tasks.tick()
    tasks.control.tick({config['robot_id']})
    with tasks.db.transaction() as s:
        assert len(list(s.scalars(select(Run)))) == 1
        assert s.get(Run, run).data['phase'] == 'queued'
        assert s.get(Robot, config['robot_id']).active_run is None
        assert s.get(Task, task['id']).enabled
    # A new service instance sees the same gate; exit skips all missed schedule slots.
    assert status(Database(str(tasks.db.engine.url)))['maintenance'] is True
    set_mode(tasks.db, False, now[0])
    tasks.tick()
    with tasks.db.transaction() as s:
        assert len(list(s.scalars(select(Run)))) == 1
        assert s.get(Task, task['id']).next_run_at == datetime(2026, 9, 11, 8, tzinfo=ZONE).timestamp()
    tasks.control.tick({config['robot_id']})
    with tasks.db.transaction() as s:
        assert s.get(Robot, config['robot_id']).active_run == run
    set_mode(tasks.db, True)
    assert status(tasks.db)['drained'] is False
    assert tasks.control.commands(config['robot_id'])[0]['action'] == 'start'
    tasks.control.request_stop(run)
    tasks.control.tick({config['robot_id']})
    assert any(command['action'] == 'stop' for command in tasks.control.commands(config['robot_id']))
