"""Operator maintenance: drain active work, retain queues, skip missed schedules."""
import argparse
import json
import os
from time import time

from sqlalchemy import select

from .storage import Database, ServiceState, Robot, ImportJob, Task


class MaintenanceError(Exception):
    pass


def gate(session):
    state = session.scalar(select(ServiceState).where(ServiceState.id == 1).with_for_update())
    if state is None:
        raise RuntimeError("缺少维护状态，请完成数据库迁移")
    return state


def require_accepting(session):
    if gate(session).maintenance:
        raise MaintenanceError("控制台维护中，暂不接收新运行")


def set_mode(db, enabled, now=None):
    from .tasks import cron_times
    with db.transaction() as s:
        state = gate(s)
        if state.maintenance and not enabled:
            at = time() if now is None else now
            for task in s.scalars(select(Task).where(Task.enabled == True).with_for_update()):
                task.next_run_at = cron_times(task.data["cron"], at, 1)[0]
        state.maintenance = enabled


def status(db):
    with db.transaction() as s:
        enabled = gate(s).maintenance
        robots = list(s.scalars(select(Robot)))
        runs = [r.active_run for r in robots if r.active_run]
        deployments = [r.deployment_job for r in robots if r.deployment_job]
        imports = list(s.scalars(select(ImportJob.id).where(ImportJob.status == "fetching")))
        return {"maintenance": enabled, "drained": enabled and not (runs or deployments or imports),
                "active_runs": runs, "active_deployments": deployments, "active_imports": imports}


def main():
    parser = argparse.ArgumentParser(description="升级维护入口；drained 后仍需停止服务再备份")
    parser.add_argument("action", choices=["status", "enter", "exit"])
    args = parser.parse_args()
    db = Database(os.environ["DATABASE_URL"])
    if args.action != "status":
        set_mode(db, args.action == "enter")
    print(json.dumps(status(db), ensure_ascii=False))


if __name__ == "__main__":
    main()
