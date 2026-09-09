"""Opt-in tests against a disposable PostgreSQL database, with isolated schemas."""
from concurrent.futures import ThreadPoolExecutor
import os
from time import time
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from rpa_console.control import Control
from rpa_console.storage import Base, Database, Robot, Run


@pytest.fixture
def pg():
    url = os.getenv("RPA_TEST_DATABASE_URL")
    if not url:
        pytest.skip("RPA_TEST_DATABASE_URL not configured")
    db = Database(url)
    schema = "recovery_test_" + uuid4().hex
    with db.engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    db.engine = db.engine.execution_options(schema_translate_map={None: schema})
    Base.metadata.create_all(db.engine)
    try:
        yield db
    finally:
        with db.engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        db.engine.dispose()


def test_concurrent_dispatch_keeps_one_active_run(pg):
    control = Control(pg)
    robot = control.add_robot("concurrent")
    control.reconcile(robot["id"], {"deployments": [{"app_id": "demo", "version": "1"}]})
    snapshot = {"app_id": "demo", "version": "1", "account_id": "original", "inputs": {"date": "2099-01-01"}}
    with ThreadPoolExecutor(max_workers=4) as pool:
        runs = list(pool.map(lambda _: control.create_run(robot["id"], snapshot, "run"), range(4)))
        list(pool.map(lambda _: control.tick({robot["id"]}), range(4)))
    with pg.transaction() as session:
        saved = list(session.scalars(select(Run)))
        active = session.get(Robot, robot["id"]).active_run
        assert active in runs
        assert sum(r.data["status"] == "starting" for r in saved) == 1
        assert sum(r.data["status"] == "queued" for r in saved) == 3


def test_persisted_budget_and_event_replay_after_new_controller(pg):
    c = Control(pg)
    robot = c.add_robot("restart")
    c.reconcile(robot["id"], {"deployments": [{"app_id": "demo", "version": "1"}]})
    run = c.create_run(robot["id"], {"app_id": "demo", "version": "1", "account_id": "A", "inputs": {}}, "run")
    c.tick({robot["id"]})
    command = c.commands(robot["id"])[0]
    message = {"type": "program_started", "console_run_id": run, "execution_attempt_id": command["execution_attempt_id"],
               "seq": 1, "data": {"local_run_id": "local-run"}}
    c.accept_message(robot["id"], message)
    replacement = Control(pg)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda _: replacement.accept_message(robot["id"], message), range(3)))
    assert replacement.commands(robot["id"]) == []
    with pg.transaction() as session:
        saved = session.get(Run, run).data
        assert len(saved["attempts"]) == 1
        assert saved["executor_seq"] == 1


def test_concurrent_plan_trigger_and_scheduler_do_not_duplicate(pg):
    from cryptography.fernet import Fernet
    from datetime import datetime
    from rpa_console.credentials import CredentialStore
    from rpa_console.tasks import Tasks, ZONE
    now = [datetime(2026, 9, 8, 7, 59, tzinfo=ZONE).timestamp()]
    control = Control(pg, lambda: now[0], CredentialStore(Fernet.generate_key()))
    robot = control.add_robot("plan-robot")
    control.reconcile(robot["id"], {"deployments": [{"app_id": "a", "version": "1", "input_schema": {
        "type": "object", "required": ["date"], "properties": {"date": {"type": "string", "format": "date"}}}}]})
    plans = Tasks(control)
    plan = plans.save({"name": "daily", "robot_id": robot["id"], "app_id": "a", "version": "1",
        "input_bindings": {"date": {"kind": "relative_date", "offset_days": -1}}, "download_dir": None,
        "schedule": {"enabled": True, "cron": "0 8 * * *"}}, {"username": "test", "password": "test"})
    with ThreadPoolExecutor(max_workers=4) as pool:
        runs = list(pool.map(lambda _: plans.trigger(plan["id"], "same-click"), range(4)))
    assert len(set(runs)) == 1
    now[0] += 120
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: plans.tick(), range(4)))
    with pg.transaction() as s:
        rows = list(s.scalars(select(Run)))
        assert len(rows) == 2
        assert all(r.data["snapshot"]["inputs"]["date"] == "2026-09-07" for r in rows)


def test_maintenance_transition_serializes_with_new_run(pg):
    from concurrent.futures import TimeoutError as FutureTimeout
    from threading import Event
    from rpa_console.maintenance import gate, MaintenanceError, status
    control = Control(pg)
    robot = control.add_robot('maintenance-race')
    control.reconcile(robot['id'], {'deployments': [{'app_id': 'demo', 'version': '1'}]})
    entered = Event()
    def create():
        entered.set()
        return control.create_run(robot['id'], {'app_id': 'demo', 'version': '1', 'inputs': {}}, 'racing-run')
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pg.transaction() as s:
            gate(s).maintenance = True
            future = pool.submit(create)
            assert entered.wait(2)
            with pytest.raises(FutureTimeout):
                future.result(timeout=0.1)
        with pytest.raises(MaintenanceError):
            future.result(timeout=3)
    with pg.transaction() as s:
        assert list(s.scalars(select(Run))) == []
    assert status(pg)['drained'] is True
