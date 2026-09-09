from .maintenance import MaintenanceError
import asyncio
import base64
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import secrets
from time import time
from typing import Literal
from urllib.parse import urlencode

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, OperationalError

from .control import Conflict, Control, TERMINAL, remaining
from .credentials import CredentialError, CredentialStore
from .tasks import Tasks, cron_times
from .publishing import Publishing
from .storage import ApplicationSource, ImportJob, PublishedApplication, ApplicationRelease, RobotDeployment, DeploymentJob
from .storage import Task, RunTrigger, Database, Event, Evidence, LoginSession, Operation, Robot, Run, RunCredential, uid


@dataclass
class Config:
    database_url: str
    internal_token: str
    public_url: str = "https://console.example.invalid"
    evidence_dir: str = "/data/evidence"
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    tenant_key: str = ""
    admins: tuple = ()
    retention_days: int = 30
    credential_encryption_key: str = ""
    artifact_dir: str = ""

    @classmethod
    def env(cls):
        return cls(os.environ["DATABASE_URL"], os.environ["AGENT_INTERNAL_TOKEN"],
                   os.environ["PUBLIC_URL"].rstrip("/"), os.getenv("EVIDENCE_DIR", "/data/evidence"),
                   os.environ["FEISHU_APP_ID"], os.environ["FEISHU_APP_SECRET"],
                   os.environ["FEISHU_TENANT_KEY"], tuple(os.environ["ADMIN_OPEN_IDS"].split(",")),
                   int(os.getenv("RETENTION_DAYS", "30")), os.environ["CREDENTIAL_ENCRYPTION_KEY"], os.getenv("ARTIFACT_DIR", "/data/artifacts"))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Snapshot(StrictModel):
    release_id: str | None = None
    app_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    inputs: dict
    download_dir: str | None = None


class BusinessCredentials(StrictModel):
    username: SecretStr = Field(min_length=1, max_length=1024)
    password: SecretStr = Field(min_length=1, max_length=4096)
    expected_identity: SecretStr | None = Field(default=None, min_length=1, max_length=1024)

    def plaintext(self):
        return {field: getattr(self, field).get_secret_value() for field in type(self).model_fields if getattr(self, field) is not None}


class NewRun(StrictModel):
    request_id: str | None = Field(default=None, min_length=1, max_length=200)
    robot_id: str
    name: str = Field(min_length=1, max_length=200)
    snapshot: Snapshot
    credentials: BusinessCredentials


class Schedule(StrictModel):
    enabled: bool = False
    cron: str = Field(default="", max_length=200)
    timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"


class TaskConfig(StrictModel):
    release_id: str | None = None
    name: str = Field(min_length=1, max_length=200)
    robot_id: str
    app_id: str
    version: str
    input_bindings: dict
    download_dir: str | None = None
    schedule: Schedule = Field(default_factory=Schedule)
    credentials: BusinessCredentials | None = None
    revision: int | None = Field(default=None, ge=1)


class ScheduleChange(Schedule):
    revision: int = Field(ge=1)


class Trigger(StrictModel):
    request_id: str = Field(min_length=1, max_length=200)


class CronPreview(StrictModel):
    cron: str = Field(min_length=1, max_length=200)


class NewRobot(StrictModel):
    name: str = Field(min_length=1, max_length=100)


class GitCredentials(StrictModel):
    username: str | None = Field(default=None, max_length=200)
    token: SecretStr | None = Field(default=None, max_length=10000)
    ssh_private_key: SecretStr | None = Field(default=None, max_length=20000)

    def plaintext(self):
        return {key: value.get_secret_value() if isinstance(value, SecretStr) else value
                for key in type(self).model_fields if (value := getattr(self, key)) is not None}


class NewSource(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000)
    credentials: GitCredentials | None = None


class NewImport(StrictModel):
    source_id: str
    ref: str = Field(min_length=1, max_length=200)


class ConfirmImport(StrictModel):
    app_ids: list[str]


class NewDeployment(StrictModel):
    release_id: str


class ToolRequest(StrictModel):
    lease: str
    execution_attempt_id: str
    request_id: str = Field(min_length=1, max_length=200)
    action: str
    params: dict


class UsageReport(StrictModel):
    session_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=0)
    input: int = Field(ge=0)
    output: int = Field(ge=0)
    cache_read: int = Field(ge=0)
    cache_write: int = Field(ge=0)
    requests: int = Field(ge=0)
    unreported_responses: int = Field(ge=0)
    model_ms: float = Field(default=0, ge=0, allow_inf_nan=False)


def create_app(config=None, database=None):
    cfg = config or Config.env()
    db = database or Database(cfg.database_url)
    credentials = CredentialStore(cfg.credential_encryption_key)
    control = Control(db, credentials=credentials)
    tasks = Tasks(control)
    sockets, connected = {}, set()
    agent_seen = [time()]
    evidence_root = Path(cfg.evidence_dir)
    evidence_root.mkdir(parents=True, exist_ok=True)
    publishing = Publishing(db, credentials, cfg.artifact_dir or str(evidence_root.parent / "artifacts"))

    async def scheduler():
        while True:
            try:
                tasks.tick()
                control.tick(connected)
            except OperationalError:
                # Keep the loop alive after a transient database outage; no next time is committed.
                await asyncio.sleep(1)
                continue
            if time() - agent_seen[0] > 30:
                with db.transaction() as s:
                    abandoned = [r.id for r in s.scalars(select(Run)) if r.data["phase"] == "recovery" and not r.data["stop_reason"]]
                for run_id in abandoned:
                    control.request_stop(run_id, "agent_unavailable")
            for robot_id, socket in list(sockets.items()):
                try:
                    for command in control.commands(robot_id) + publishing.commands(robot_id):
                        await socket.send_json(command)
                except CredentialError:
                    with db.transaction() as s:
                        active_run = s.get(Robot, robot_id).active_run
                    if active_run:
                        control.request_stop(active_run, "credentials_unavailable")
                except (RuntimeError, OSError, WebSocketDisconnect):
                    connected.discard(robot_id)
                    control.disconnect(robot_id)
            await asyncio.sleep(0.5)

    @asynccontextmanager
    async def lifespan(app):
        # Apply the same per-run retention rule to screenshots saved before this update.
        obsolete = []
        with db.transaction() as s:
            run_ids = list(s.scalars(select(Evidence.run_id).distinct()))
            for run_id in run_ids:
                images = list(s.scalars(select(Evidence).where(Evidence.run_id == run_id)))
                available = [image for image in images if (evidence_root / image.id).is_file()]
                latest = max(available, key=lambda image: (evidence_root / image.id).stat().st_mtime_ns, default=None)
                for image in images:
                    if image is not latest:
                        s.delete(image)
                        obsolete.append(evidence_root / image.id)
        for path in obsolete:
            path.unlink(missing_ok=True)
        tasks.reset_after_restart()
        task = asyncio.create_task(scheduler())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    app = FastAPI(title="RPA Recovery Console", lifespan=lifespan)
    app.state.control, app.state.database = control, db

    @app.exception_handler(MaintenanceError)
    async def maintenance_error(request, error):
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.exception_handler(Conflict)
    async def conflict(request, error):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(IntegrityError)
    async def conflicting_write(request, error):
        return JSONResponse(status_code=409, content={"detail": "并发请求冲突，请重试原请求或刷新配置"})

    @app.exception_handler(CredentialError)
    async def credential_error(request, error):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Pydantic errors can contain the submitted object, including passwords.
        return JSONResponse(status_code=422, content={"detail": [
            {key: item[key] for key in ("loc", "msg", "type")} for item in error.errors()]})

    def identity(request: Request):
        cookie = request.cookies.get("rpa_session", "")
        with db.transaction() as s:
            row = s.get(LoginSession, sha256(cookie.encode()).hexdigest())
            if not row or row.expires <= time() or row.data.get("kind") != "user":
                raise HTTPException(401, "请通过企业飞书登录")
            user = row.data
            return {"name": user["name"], "open_id": user["open_id"], "admin": user["open_id"] in cfg.admins}

    def admin(request: Request, user=Depends(identity)):
        if not user["admin"]:
            raise HTTPException(403, "需要管理员权限")
        if request.method not in {"GET", "HEAD"} and request.headers.get("Origin") != cfg.public_url:
            raise HTTPException(403, "管理请求来源不匹配")
        return user

    def internal(request: Request):
        if not hmac.compare_digest(request.headers.get("Authorization", ""), "Bearer " + cfg.internal_token):
            raise HTTPException(401, "内部服务认证失败")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": "live"}

    @app.get("/api/auth/feishu/login")
    def login():
        state = secrets.token_urlsafe(32)
        with db.transaction() as s:
            s.add(LoginSession(id=sha256(state.encode()).hexdigest(), expires=time() + 600, data={"kind": "oauth_state"}))
        response = RedirectResponse("https://accounts.feishu.cn/open-apis/authen/v1/authorize?" + urlencode({
            "client_id": cfg.feishu_app_id, "redirect_uri": cfg.public_url + "/api/auth/feishu/callback",
            "response_type": "code", "state": state}))
        response.set_cookie("rpa_oauth", state, httponly=True, secure=True, samesite="lax", max_age=600)
        return response

    @app.get("/api/auth/feishu/callback")
    async def callback(request: Request, code: str, state: str):
        if not hmac.compare_digest(request.cookies.get("rpa_oauth", ""), state):
            raise HTTPException(401, "登录 state 无效")
        with db.transaction() as s:
            row = s.get(LoginSession, sha256(state.encode()).hexdigest())
            if not row or row.expires < time() or row.data.get("kind") != "oauth_state":
                raise HTTPException(401, "登录 state 已过期或使用")
            s.delete(row)
        async with httpx.AsyncClient(timeout=20) as client:
            token = (await client.post("https://open.feishu.cn/open-apis/authen/v2/oauth/token", json={
                "grant_type": "authorization_code", "client_id": cfg.feishu_app_id,
                "client_secret": cfg.feishu_app_secret, "code": code,
                "redirect_uri": cfg.public_url + "/api/auth/feishu/callback"})).json()
            if not token.get("access_token"):
                raise HTTPException(401, "飞书登录凭据交换失败")
            user_result = (await client.get("https://open.feishu.cn/open-apis/authen/v1/user_info",
                headers={"Authorization": "Bearer " + token["access_token"]})).json()
        user = user_result.get("data", {})
        if user_result.get("code") != 0 or user.get("tenant_key") != cfg.tenant_key or not user.get("open_id"):
            raise HTTPException(403, "仅允许配置企业的成员登录")
        session = secrets.token_urlsafe(32)
        with db.transaction() as s:
            s.add(LoginSession(id=sha256(session.encode()).hexdigest(), expires=time() + 43200,
                data={"kind": "user", "open_id": user["open_id"], "name": user.get("name", "企业成员")}))
        response = RedirectResponse("/runs")
        response.delete_cookie("rpa_oauth")
        response.set_cookie("rpa_session", session, httponly=True, secure=True, samesite="lax", max_age=43200)
        return response

    @app.get("/api/me")
    def me(user=Depends(identity)):
        return user

    @app.get("/api/robots", dependencies=[Depends(admin)])
    def robots():
        with db.transaction() as s:
            return [{"id": r.id, "name": r.name, "active_run": r.active_run, "online": r.id in connected,
                     "revoked": r.credential_hash is None, "deployments": r.deployments, "capabilities": r.capabilities, "deployment_job": r.deployment_job} for r in s.scalars(select(Robot))]

    @app.post("/api/robots", dependencies=[Depends(admin)])
    def add_robot(body: NewRobot):
        return control.add_robot(body.name)

    @app.post("/api/robots/{robot_id}/revoke", dependencies=[Depends(admin)])
    def revoke(robot_id: str):
        control.revoke(robot_id)
        return {"stop_requested": True}

    @app.post("/api/robots/{robot_id}/rotate", dependencies=[Depends(admin)])
    def rotate(robot_id: str):
        return {"credential": control.revoke(robot_id, rotate=True)}

    @app.post("/api/runs", dependencies=[Depends(admin)])
    def create_run(body: NewRun):
        def reject_secrets(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if any(part in key.lower() for part in ("password", "secret", "token", "credential")):
                        raise HTTPException(422, "账号密码请填写专用凭据字段，不能进入业务参数")
                    reject_secrets(item)
            elif isinstance(value, list):
                for item in value:
                    reject_secrets(item)
        reject_secrets(body.snapshot.inputs)
        return {"id": control.create_run(body.robot_id, body.snapshot.model_dump(), body.name,
                                         credentials=body.credentials.plaintext(),
                                         request_id="manual:" + body.request_id if body.request_id else None)}

    @app.get("/api/tasks", dependencies=[Depends(admin)])
    def list_tasks():
        with db.transaction() as s:
            return [tasks.view(task) for task in s.scalars(select(Task).order_by(Task.name, Task.id))]

    @app.get("/api/tasks/{task_id}", dependencies=[Depends(admin)])
    def get_task(task_id: str):
        with db.transaction() as s:
            return tasks.view(tasks.get(s, task_id))

    @app.post("/api/tasks", dependencies=[Depends(admin)])
    def create_task(body: TaskConfig):
        return tasks.save(body.model_dump(exclude={"credentials", "revision"}),
                          body.credentials.plaintext() if body.credentials else None)

    @app.patch("/api/tasks/{task_id}", dependencies=[Depends(admin)])
    def edit_task(task_id: str, body: TaskConfig):
        return tasks.save(body.model_dump(exclude={"credentials", "revision"}),
                          body.credentials.plaintext() if body.credentials else None,
                          task_id, body.revision)

    @app.put("/api/tasks/{task_id}/schedule", dependencies=[Depends(admin)])
    def update_schedule(task_id: str, body: ScheduleChange):
        return tasks.schedule(task_id, body.revision, body.model_dump(exclude={"revision"}))

    @app.post("/api/tasks/{task_id}/runs", dependencies=[Depends(admin)])
    def trigger_task(task_id: str, body: Trigger):
        return {"id": tasks.trigger(task_id, body.request_id)}

    @app.post("/api/schedules/preview", dependencies=[Depends(admin)])
    def preview_schedule(body: CronPreview):
        return {"timezone": "Asia/Shanghai", "dates": cron_times(body.cron, time())}

    @app.get("/api/application-sources", dependencies=[Depends(admin)])
    def sources():
        with db.transaction() as s:
            return [publishing.source_view(row) for row in s.scalars(select(ApplicationSource))]

    @app.post("/api/application-sources", dependencies=[Depends(admin)])
    def create_source(body: NewSource):
        return publishing.add_source(body.name, body.url, body.credentials.plaintext() if body.credentials else None)

    @app.get("/api/application-imports", dependencies=[Depends(admin)])
    def imports():
        with db.transaction() as s:
            return [publishing.import_view(row) for row in s.scalars(select(ImportJob).order_by(ImportJob.created.desc()).limit(100))]

    @app.post("/api/application-imports", dependencies=[Depends(admin)])
    def create_import(body: NewImport):
        return publishing.import_source(body.source_id, body.ref)

    @app.get("/api/application-imports/{job_id}", dependencies=[Depends(admin)])
    def import_detail(job_id: str):
        with db.transaction() as s:
            job = s.get(ImportJob, job_id)
            if not job:
                raise HTTPException(404, "导入作业不存在")
            return publishing.import_view(job)

    @app.post("/api/application-imports/{job_id}/confirm", dependencies=[Depends(admin)])
    def confirm_import(job_id: str, body: ConfirmImport):
        return publishing.confirm(job_id, body.app_ids)

    @app.get("/api/applications", dependencies=[Depends(admin)])
    def applications():
        with db.transaction() as s:
            return [{"id": row.id, "source_id": row.source_id, "app_id": row.app_id, "name": row.name}
                    for row in s.scalars(select(PublishedApplication).order_by(PublishedApplication.name))]

    @app.get("/api/applications/{app_id}/releases", dependencies=[Depends(admin)])
    def releases(app_id: str):
        with db.transaction() as s:
            return [publishing.release_view(row) for row in s.scalars(select(ApplicationRelease).where(ApplicationRelease.application_id == app_id))]

    @app.get("/api/application-releases/{release_id}/form", dependencies=[Depends(admin)])
    def release_form(release_id: str):
        with db.transaction() as s:
            release = s.get(ApplicationRelease, release_id)
            if not release:
                raise HTTPException(404, "发布版本不存在")
            return release.data["input_schema"]

    @app.get("/api/robots/{robot_id}/deployments", dependencies=[Depends(admin)])
    def deployments(robot_id: str):
        with db.transaction() as s:
            return {"deployments": [{"release_id": row.release_id, "status": row.status, **row.data}
                    for row in s.scalars(select(RobotDeployment).where(RobotDeployment.robot_id == robot_id))],
                    "jobs": [publishing.job_view(row) for row in s.scalars(select(DeploymentJob).where(DeploymentJob.robot_id == robot_id).order_by(DeploymentJob.created.desc()).limit(100))]}

    @app.post("/api/robots/{robot_id}/deployments", dependencies=[Depends(admin)])
    def install_release(robot_id: str, body: NewDeployment):
        return publishing.request_deployment(robot_id, body.release_id)

    @app.delete("/api/robots/{robot_id}/deployments/{release_id}", dependencies=[Depends(admin)])
    def uninstall_release(robot_id: str, release_id: str):
        return publishing.request_deployment(robot_id, release_id, "uninstall")

    @app.get("/api/deployment-jobs/{job_id}", dependencies=[Depends(admin)])
    def deployment_job(job_id: str):
        with db.transaction() as s:
            job = s.get(DeploymentJob, job_id)
            if not job:
                raise HTTPException(404, "部署作业不存在")
            return publishing.job_view(job)

    @app.get("/api/robot-deployment-jobs/{job_id}/artifact")
    def deployment_artifact(job_id: str, request: Request):
        robot_id = control.authenticate_robot(request.headers.get("Authorization", "").removeprefix("Bearer "))
        if not robot_id:
            raise HTTPException(401, "机器人认证失败")
        return FileResponse(publishing.artifact(robot_id, job_id), media_type="application/x-tar")

    @app.post("/api/runs/{run_id}/rerun", dependencies=[Depends(admin)])
    def rerun(run_id: str):
        with db.transaction() as s:
            run = s.get(Run, run_id)
            if not run or run.data["status"] not in TERMINAL:
                raise HTTPException(409, "只能重跑已结束的运行")
            return {"id": control.create_run(run.robot_id, run.data["snapshot"], run.data["name"], run.id,
                                             credentials=credentials.read(s, run.id))}

    @app.post("/api/runs/{run_id}/stop", dependencies=[Depends(admin)])
    def stop(run_id: str):
        control.request_stop(run_id)
        return {"requested": True}

    def view(run, business):
        d = run.data
        result = {"id": run.id, "name": d["name"], "status": d["status"], "created": run.created,
                  "ended": d.get("ended"), "seq": d["seq"]}
        if not business:
            result.update({**d, "robot_id": run.robot_id, "remaining_seconds": remaining(d, time())})
            result.pop("lease", None)
            result.pop("token_sessions", None)
        return result

    def read_run(run_id, business):
        with db.transaction() as s:
            run = s.get(Run, run_id)
            if not run:
                raise HTTPException(404, "运行不存在")
            result = view(run, business)
            result["evidence"] = [{"id": e.id, "url": "/api/business/screenshots/" + e.id} for e in s.scalars(select(Evidence).where(Evidence.run_id == run.id))]
            return result

    @app.get("/api/runs", dependencies=[Depends(admin)])
    def runs():
        with db.transaction() as s:
            return [view(r, False) for r in s.scalars(select(Run).order_by(Run.created.desc()).limit(500))]

    @app.get("/api/business/runs", dependencies=[Depends(identity)])
    def business_runs():
        with db.transaction() as s:
            return [view(r, True) for r in s.scalars(select(Run).order_by(Run.created.desc()).limit(500))]

    @app.get("/api/runs/{run_id}", dependencies=[Depends(admin)])
    def run(run_id: str):
        return read_run(run_id, False)

    @app.get("/api/business/runs/{run_id}", dependencies=[Depends(identity)])
    def business_run(run_id: str):
        return read_run(run_id, True)

    @app.get("/api/business/screenshots/{evidence_id}", dependencies=[Depends(identity)])
    def screenshot(evidence_id: str):
        with db.transaction() as s:
            evidence = s.get(Evidence, evidence_id)
            if not evidence or not (evidence_root / evidence.id).is_file():
                raise HTTPException(404, "截图不存在")
            return FileResponse(evidence_root / evidence.id, media_type=evidence.mime,
                                headers={"Cache-Control": "private, no-store"})

    @app.get("/api/runs/{run_id}/events", dependencies=[Depends(admin)])
    @app.get("/api/business/runs/{run_id}/events", dependencies=[Depends(identity)])
    async def events(request: Request, run_id: str, after: int = 0):
        business = "/business/" in request.url.path
        read_run(run_id, business)
        cursor = max(after, int(request.headers.get("Last-Event-ID", "0")))
        async def stream():
            nonlocal cursor
            while not await request.is_disconnected():
                # Revalidate session expiry on live streams too.
                try:
                    identity(request)
                except HTTPException:
                    return
                with db.transaction() as s:
                    batch = list(s.scalars(select(Event).where(Event.run_id == run_id, Event.seq > cursor).order_by(Event.seq).limit(100)))
                for event in batch:
                    cursor = event.seq
                    if event.data["kind"] == "operation":
                        continue
                    data = {"seq": event.seq, **event.data}
                    if business:
                        data = {key: data[key] for key in ("seq", "kind", "message", "at")}
                    yield f"id: {cursor}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                yield ": keepalive\n\n"
                await asyncio.sleep(1)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    def save_image(s, run, message):
        result = message.get("data" if message["type"] == "evidence" else "result", {})
        image = result.pop("image", None)
        if not image:
            return []
        data = base64.b64decode(image["data"], validate=True)
        if image["mimeType"] != "image/png" or not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 8 * 1024 * 1024:
            raise Conflict("截图格式或大小无效")
        # Stable attachment identity makes duplicate result replay idempotent.
        reference = f"event:{message['seq']}" if message["type"] == "evidence" else message["request_id"]
        evidence_id = sha256((message["console_run_id"] + reference).encode()).hexdigest()
        (evidence_root / evidence_id).write_bytes(data)
        obsolete = []
        for old in s.scalars(select(Evidence).where(Evidence.run_id == run.id, Evidence.id != evidence_id)):
            obsolete.append(evidence_root / old.id)
            s.delete(old)
        if not s.get(Evidence, evidence_id):
            s.add(Evidence(id=evidence_id, run_id=run.id, mime="image/png"))
        result["evidence_id"] = evidence_id
        return obsolete

    @app.websocket("/api/robots/connect")
    async def robot_connect(socket: WebSocket):
        token = socket.headers.get("Authorization", "").removeprefix("Bearer ")
        robot_id = control.authenticate_robot(token)
        if not robot_id or robot_id in sockets:
            await socket.close(code=1008)
            return
        await socket.accept()
        sockets[robot_id] = socket
        try:
            hello = await asyncio.wait_for(socket.receive_json(), 15)
            control.reconcile(robot_id, hello)
            publishing.reconcile(robot_id, hello)
            with db.transaction() as s:
                robot = s.get(Robot, robot_id)
                run = s.get(Run, robot.active_run or hello.get("active_run")) if robot.active_run or hello.get("active_run") else None
                after = run.data["executor_seq"] if run else 0
            await socket.send_json({"type": "sync", "console_run_id": run.id if run else None,
                                    "after_seq": after, "server_time": time()})
            # Replay finishes before fresh controls are enabled by the next ready frame.
            while True:
                message = await socket.receive_json()
                if message["type"] == "ready":
                    connected.add(robot_id)
                    continue
                if message["type"] == "deployment_report":
                    seq = publishing.accept(robot_id, message)
                    await socket.send_json({"type": "deployment_ack", "job_id": message["job_id"], "seq": seq})
                    continue
                obsolete = []
                def record_image(s, run, event):
                    obsolete.extend(save_image(s, run, event))
                seq = control.accept_message(robot_id, message, save_image=record_image)
                # Delete old files only after the new evidence and event have committed.
                for path in obsolete:
                    path.unlink(missing_ok=True)
                await socket.send_json({"type": "ack", "console_run_id": message["console_run_id"], "seq": seq})
        except (WebSocketDisconnect, ValueError, KeyError, asyncio.TimeoutError):
            with suppress(RuntimeError):
                await socket.close(code=1008)
        finally:
            connected.discard(robot_id)
            if sockets.get(robot_id) is socket:
                sockets.pop(robot_id, None)
            control.disconnect(robot_id)

    @app.get("/internal/agent/work", dependencies=[Depends(internal)])
    def work():
        agent_seen[0] = time()
        with db.transaction() as s:
            runs = list(s.scalars(select(Run)))
            ids = [r.id for r in runs if r.data["phase"] == "recovery"]
            expired = [r.id for r in runs if r.data["status"] in TERMINAL and r.data.get("ended", time()) < time() - cfg.retention_days * 86400]
        return {"runs": ids, "expired": expired}

    @app.post("/internal/runs/{run_id}/purge", dependencies=[Depends(internal)])
    def purge(run_id: str):
        with db.transaction() as s:
            run, robot, d = control._load(s, run_id)
            if d["status"] not in TERMINAL or robot.active_run == run.id or d.get("ended", time()) >= time() - cfg.retention_days * 86400:
                raise Conflict("运行未达到清理期限")
            for evidence in s.scalars(select(Evidence).where(Evidence.run_id == run_id)):
                (evidence_root / evidence.id).unlink(missing_ok=True)
            for table in (Evidence, Event, Operation, RunCredential, RunTrigger):
                s.execute(delete(table).where(table.run_id == run_id))
            s.delete(run)
            s.execute(delete(LoginSession).where(LoginSession.expires < time()))
        return {"purged": True}

    @app.post("/internal/runs/{run_id}/claim", dependencies=[Depends(internal)])
    def claim(run_id: str):
        return control.claim(run_id, connected)

    @app.post("/internal/runs/{run_id}/heartbeat", dependencies=[Depends(internal)])
    def heartbeat(run_id: str, body: dict):
        return control.agent_state(run_id, body["lease"], renew=True)

    @app.post("/internal/runs/{run_id}/operations", dependencies=[Depends(internal)])
    def operation(run_id: str, body: ToolRequest):
        return {"id": control.tool(run_id, body.lease, body.execution_attempt_id, body.request_id, body.action, body.params, connected)}

    @app.get("/internal/runs/{run_id}/operations/{request_id}", dependencies=[Depends(internal)])
    def result(run_id: str, request_id: str):
        with db.transaction() as s:
            op = s.get(Operation, request_id)
            if not op or op.run_id != run_id:
                raise HTTPException(404, "请求不存在")
            data = dict(op.data)
            result = dict(data.get("result") or {})
            if result.get("evidence_id"):
                evidence = s.get(Evidence, result["evidence_id"])
                if evidence and evidence.run_id == run_id and (evidence_root / evidence.id).is_file():
                    result["image"] = {"mimeType": "image/png", "data": base64.b64encode((evidence_root / evidence.id).read_bytes()).decode()}
                else:
                    result["screenshot_missing"] = "该截图已被替换或清理"
            return {"status": data["status"], "result": result}

    @app.post("/internal/runs/{run_id}/usage", dependencies=[Depends(internal)])
    def usage(run_id: str, body: UsageReport):
        with db.transaction() as s:
            if not s.get(Run, run_id):
                return {"recorded": False}
            run, _, data = control._load(s, run_id)
            sessions = data.setdefault("token_sessions", {})
            previous = sessions.get(body.session_id)
            if previous is None or body.revision > previous["revision"]:
                sessions[body.session_id] = body.model_dump(exclude={"session_id"})
                fields = ("input", "output", "cache_read", "cache_write", "requests", "unreported_responses")
                totals = {key: sum(item[key] for item in sessions.values()) for key in fields}
                totals["total"] = sum(totals[key] for key in ("input", "output", "cache_read", "cache_write"))
                data["token_usage"] = totals
                data["recovery_timings"] = {"model_ms": sum(item.get("model_ms", 0) for item in sessions.values())}
                run.data = data
        return {"recorded": True}

    @app.post("/internal/runs/{run_id}/agent-failed", dependencies=[Depends(internal)])
    def agent_failed(run_id: str, body: dict):
        if control.agent_state(run_id, body["lease"])["active"]:
            control.request_stop(run_id, body.get("reason") if body.get("reason") in {"request_budget_exhausted", "token_budget_exhausted", "repeated_response_truncation", "recovery_protocol_unsupported"} else "agent_unavailable")
        return {"recorded": True}

    return app
