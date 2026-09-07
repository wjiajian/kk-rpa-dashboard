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
