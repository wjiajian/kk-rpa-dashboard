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
from urllib.parse import urlencode

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select

from .control import Conflict, Control, TERMINAL, remaining
from .storage import Database, Event, Evidence, LoginSession, Operation, Robot, Run, uid


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

    @classmethod
    def env(cls):
        return cls(os.environ["DATABASE_URL"], os.environ["AGENT_INTERNAL_TOKEN"],
                   os.environ["PUBLIC_URL"].rstrip("/"), os.getenv("EVIDENCE_DIR", "/data/evidence"),
                   os.environ["FEISHU_APP_ID"], os.environ["FEISHU_APP_SECRET"],
                   os.environ["FEISHU_TENANT_KEY"], tuple(os.environ["ADMIN_OPEN_IDS"].split(",")),
                   int(os.getenv("RETENTION_DAYS", "30")))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Snapshot(StrictModel):
    app_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    inputs: dict
    download_dir: str | None = None


class NewRun(StrictModel):
    robot_id: str
    name: str = Field(min_length=1, max_length=200)
    snapshot: Snapshot


class NewRobot(StrictModel):
    name: str = Field(min_length=1, max_length=100)


class ToolRequest(StrictModel):
    lease: str
    execution_attempt_id: str
    request_id: str = Field(min_length=1, max_length=200)
    action: str
    params: dict


def create_app(config=None, database=None):
    cfg = config or Config.env()
    db = database or Database(cfg.database_url)
    control = Control(db)
    sockets, connected = {}, set()
    agent_seen = [time()]
    evidence_root = Path(cfg.evidence_dir)
    evidence_root.mkdir(parents=True, exist_ok=True)

    async def scheduler():
        while True:
            control.tick(connected)
            if time() - agent_seen[0] > 30:
                with db.transaction() as s:
                    abandoned = [r.id for r in s.scalars(select(Run)) if r.data["phase"] == "recovery" and not r.data["stop_reason"]]
                for run_id in abandoned:
                    control.request_stop(run_id, "agent_unavailable")
            for robot_id, socket in list(sockets.items()):
                try:
                    for command in control.commands(robot_id):
                        await socket.send_json(command)
                except (RuntimeError, OSError, WebSocketDisconnect):
                    connected.discard(robot_id)
                    control.disconnect(robot_id)
            await asyncio.sleep(0.5)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(scheduler())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    app = FastAPI(title="RPA Recovery Console", lifespan=lifespan)
    app.state.control, app.state.database = control, db

    @app.exception_handler(Conflict)
    async def conflict(request, error):
        return JSONResponse(status_code=409, content={"detail": str(error)})

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
                     "revoked": r.credential_hash is None, "deployments": r.deployments} for r in s.scalars(select(Robot))]

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
                        raise HTTPException(422, "凭据必须在机器人账号配置中提供，不能进入业务参数")
                    reject_secrets(item)
            elif isinstance(value, list):
                for item in value:
                    reject_secrets(item)
        reject_secrets(body.snapshot.inputs)
        return {"id": control.create_run(body.robot_id, body.snapshot.model_dump(), body.name)}

    @app.post("/api/runs/{run_id}/rerun", dependencies=[Depends(admin)])
    def rerun(run_id: str):
        with db.transaction() as s:
            run = s.get(Run, run_id)
            if not run or run.data["status"] not in TERMINAL:
                raise HTTPException(409, "只能重跑已结束的运行")
            return {"id": control.create_run(run.robot_id, run.data["snapshot"], run.data["name"], run.id)}

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
            if not evidence:
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
                    data = {"seq": event.seq, **event.data}
                    if business:
                        data = {key: data[key] for key in ("seq", "kind", "message", "at")}
                    cursor = event.seq
                    yield f"id: {cursor}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                yield ": keepalive\n\n"
                await asyncio.sleep(1)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    def save_image(message):
        result = message.get("result", {})
        image = result.pop("image", None)
        if not image:
            return
        data = base64.b64decode(image["data"], validate=True)
        if image["mimeType"] != "image/png" or not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 8 * 1024 * 1024:
            raise Conflict("截图格式或大小无效")
        # Stable attachment identity makes duplicate result replay idempotent.
        evidence_id = sha256((message["console_run_id"] + message["request_id"]).encode()).hexdigest()
        (evidence_root / evidence_id).write_bytes(data)
        with db.transaction() as s:
            if not s.get(Evidence, evidence_id):
                s.add(Evidence(id=evidence_id, run_id=message["console_run_id"], mime="image/png"))
        result["evidence_id"] = evidence_id

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
                if message["type"] == "result":
                    with db.transaction() as s:
                        op = s.get(Operation, message["request_id"])
                        source = s.get(Run, op.run_id) if op else None
                        if not source or source.robot_id != robot_id or source.id != message["console_run_id"]:
                            raise Conflict("证据与请求归属不匹配")
                    save_image(message)
                seq = control.accept_message(robot_id, message)
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
            for table in (Evidence, Event, Operation):
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
                result["image"] = {"mimeType": "image/png", "data": base64.b64encode((evidence_root / result["evidence_id"]).read_bytes()).decode()}
            return {"status": data["status"], "result": result}

    @app.post("/internal/runs/{run_id}/agent-failed", dependencies=[Depends(internal)])
    def agent_failed(run_id: str, body: dict):
        if control.agent_state(run_id, body["lease"])["active"]:
            control.request_stop(run_id, "agent_unavailable")
        return {"recorded": True}

    return app
