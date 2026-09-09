"""Persistent plan configuration and atomic creation of immutable run inputs."""
from .maintenance import gate, require_accepting
from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from croniter import croniter, CroniterBadCronError, CroniterBadDateError
from sqlalchemy import select

from .control import Conflict
from .credentials import CredentialError
from .schemas import input_schema, schema_validator, validate_inputs, require_installed_release
from .storage import Task, RunTrigger, ApplicationRelease, uid

ZONE = ZoneInfo("Asia/Shanghai")


def cron_times(expression, now, count=5):
    if not isinstance(expression, str) or len(expression.split()) != 5:
        raise Conflict("请输入五段 Cron：分 时 日 月 星期")
    try:
        iterator = croniter(expression, datetime.fromtimestamp(now, ZONE), day_or=True)
        return [iterator.get_next(datetime).timestamp() for _ in range(count)]
    except (CroniterBadCronError, CroniterBadDateError, ValueError, OverflowError):
        raise Conflict("Cron 表达式无效或没有可执行日期") from None


def resolve_bindings(schema, bindings, at):
    if not isinstance(bindings, dict):
        raise Conflict("计划参数绑定必须为对象")
    values = {}
    for key, binding in bindings.items():
        if not isinstance(binding, dict):
            raise Conflict(f"参数 {key} 的绑定无效")
        if binding.get("kind") == "literal" and set(binding) == {"kind", "value"}:
            values[key] = binding["value"]
        elif binding.get("kind") == "relative_date" and set(binding) == {"kind", "offset_days"}:
            field = schema.get("properties", {}).get(key, {})
            offset = binding["offset_days"]
            if not isinstance(field, dict) or field.get("format") != "date" or type(offset) is not int:
                raise Conflict(f"参数 {key} 不接受该日期偏移")
            try:
                values[key] = (datetime.fromtimestamp(at, ZONE).date() + timedelta(days=offset)).isoformat()
            except (OverflowError, ValueError):
                raise Conflict(f"参数 {key} 的日期偏移超出范围") from None
        else:
            raise Conflict(f"参数 {key} 的绑定无效")
    return values


class Tasks:
    def __init__(self, control):
        self.control, self.db, self.credentials = control, control.db, control.credentials
        self.clock = control.clock

    def get(self, s, task_id, lock=False):
        query = select(Task).where(Task.id == task_id)
        task = s.scalar(query.with_for_update() if lock else query)
        if task is None:
            raise Conflict("计划不存在")
        return task

    def view(self, task):
        return {"id": task.id, "name": task.name, "robot_id": task.robot_id,
                "revision": task.revision, "next_run_at": task.next_run_at,
                **deepcopy(task.data), "schedule": {"enabled": task.enabled,
                    "cron": task.data.get("cron", ""), "timezone": "Asia/Shanghai"},
                "credentials_configured": {"username": True, "password": True}}

    def deployment(self, s, robot_id, app_id, version, release_id=None):
        robot = self.db.lock_robot(s, robot_id)
        if not robot.credential_hash:
            raise Conflict("机器人凭据已撤销")
        deployment = next((d for d in robot.deployments if d["app_id"] == app_id and d["version"] == version and d.get("release_id") == release_id), None)
        if not deployment or deployment.get("schema_status") == "invalid" or input_schema(deployment) is None:
            raise Conflict("计划需要已部署且参数声明有效的应用版本")
        try:
            if release_id:
                require_installed_release(s, robot_id, release_id)
            schema_validator(input_schema(deployment))
        except ValueError as error:
            raise Conflict(str(error)) from error
        return deployment

    def validate_config(self, s, config, at):
        deployment = self.deployment(s, config["robot_id"], config["app_id"], config["version"], config.get("release_id"))
        values = resolve_bindings(input_schema(deployment), config["input_bindings"], at)
        try:
            validate_inputs(deployment, values)
        except ValueError as error:
            raise Conflict(str(error)) from error
        schedule = config["schedule"]
        expression = schedule["cron"].strip()
        if schedule["enabled"] or expression:
            cron_times(expression, at)
        return values

    def save(self, config, credentials=None, task_id=None, revision=None):
        if not config["name"].strip():
            raise Conflict("请输入计划名称")
        with self.db.transaction() as s:
            task = self.get(s, task_id, True) if task_id else None
            if task and task.revision != revision:
                raise Conflict("计划已被修改，请刷新后重新编辑")
            self.validate_config(s, config, self.clock())
            if task is None:
                if not credentials:
                    raise Conflict("新计划必须填写账号密码")
                task = Task(id=uid(), name=config["name"], robot_id=config["robot_id"], revision=1, data={})
                s.add(task)
                s.flush()
            else:
                task.revision += 1
            task.name, task.robot_id = config["name"], config["robot_id"]
            schedule = config["schedule"]
            task.enabled = schedule["enabled"]
            task.next_run_at = cron_times(schedule["cron"], self.clock(), 1)[0] if task.enabled else None
            task.data = {**task.data, **{key: deepcopy(config[key]) for key in ("app_id", "version", "input_bindings", "download_dir")}}
            task.data.update(release_id=config.get("release_id"), cron=schedule["cron"].strip(), last_error=None)
            release = s.get(ApplicationRelease, config["release_id"]) if config.get("release_id") else None
            task.data = {**task.data, "commit": release.commit if release else None}
            if credentials is not None:
                self.credentials.save_task(s, task.id, credentials)
            return self.view(task)

    def schedule(self, task_id, revision, schedule):
        with self.db.transaction() as s:
            task = self.get(s, task_id, True)
            if task.revision != revision:
                raise Conflict("计划已被修改，请刷新后重试")
            config = {**task.data, "robot_id": task.robot_id, "schedule": schedule}
            if schedule["enabled"]:
                self.validate_config(s, config, self.clock())
            task.enabled = schedule["enabled"]
            task.next_run_at = cron_times(schedule["cron"], self.clock(), 1)[0] if task.enabled else None
            task.revision += 1
            task.data = {**task.data, "cron": schedule["cron"].strip(), "last_error": None}
            return self.view(task)

    def trigger_in_session(self, s, task, request_id, scheduled_for=None):
        intent = {"task_id": task.id, "scheduled_for": scheduled_for}
        existing = s.get(RunTrigger, request_id)
        if existing:
            if existing.intent != intent:
                raise Conflict("请求标识已被不同的运行请求使用")
            return existing.run_id
        config = {**task.data, "robot_id": task.robot_id, "schedule": {"enabled": False, "cron": ""}}
        values = self.validate_config(s, config, scheduled_for if scheduled_for is not None else self.clock())
        snapshot = {"app_id": task.data["app_id"], "version": task.data["version"],
                    "inputs": values, "download_dir": task.data["download_dir"]}
        if task.data.get("release_id"):
            snapshot["release_id"] = task.data["release_id"]
        run_id = self.control.create_run_in_session(s, task.robot_id, snapshot, task.name,
            credentials=self.credentials.read_task(s, task.id), request_id=request_id, intent=intent,
            metadata={"task_id": task.id, "trigger": "scheduled" if scheduled_for is not None else "manual_task",
                      "scheduled_for": scheduled_for})
        task.data = {**task.data, "last_run_id": run_id, "last_error": None}
        return run_id

    def trigger(self, task_id, request_id):
        with self.db.transaction() as s:
            require_accepting(s)
            return self.trigger_in_session(s, self.get(s, task_id, True), "manual:" + request_id)

    def reset_after_restart(self):
        with self.db.transaction() as s:
            for task in s.scalars(select(Task).where(Task.enabled == True).with_for_update()):
                task.next_run_at = cron_times(task.data["cron"], self.clock(), 1)[0]

    def tick(self):
        now = self.clock()
        with self.db.transaction() as s:
            ids = list(s.scalars(select(Task.id).where(Task.enabled == True, Task.next_run_at <= now)))
        for task_id in ids:
            with self.db.transaction() as s:
                if gate(s).maintenance:
                    return
                task = self.get(s, task_id, True)
                if not task.enabled or task.next_run_at is None or task.next_run_at > now:
                    continue
                try:
                    # A delayed loop emits only the most recent due slot.
                    scheduled = croniter(task.data["cron"], datetime.fromtimestamp(now + 0.001, ZONE), day_or=True).get_prev(datetime).timestamp()
                    request_id = f"scheduled:{task.id}:{int(scheduled)}"
                    self.trigger_in_session(s, task, request_id, scheduled)
                    task.next_run_at = cron_times(task.data["cron"], now, 1)[0]
                except (Conflict, CredentialError) as error:
                    task.enabled, task.next_run_at = False, None
                    task.revision += 1
                    task.data = {**task.data, "last_error": str(error)}
