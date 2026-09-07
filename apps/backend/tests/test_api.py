from hashlib import sha256
from time import time

from fastapi.testclient import TestClient
import pytest

from rpa_console.api import Config, create_app
from rpa_console.storage import Base, Database, LoginSession


@pytest.fixture
def app(tmp_path):
    db = Database("sqlite:///" + str(tmp_path / "api.db"))
    Base.metadata.create_all(db.engine)
    config = Config("unused", "internal-secret", public_url="https://console.test", evidence_dir=str(tmp_path / "evidence"), admins=("admin",))
    with db.transaction() as s:
        for token, open_id in (("admin-session", "admin"), ("member-session", "member")):
            s.add(LoginSession(id=sha256(token.encode()).hexdigest(), expires=time() + 600,
                data={"kind": "user", "name": "test", "open_id": open_id}))
    return create_app(config, db)


def test_permissions_and_csrf_are_server_enforced(app):
    client = TestClient(app, base_url="https://console.test")
    assert client.get("/api/robots").status_code == 401
    client.cookies.set("rpa_session", "member-session")
    assert client.get("/api/robots").status_code == 403
    assert client.post("/api/runs/missing/stop", json={}).status_code == 403
    assert client.get("/api/business/runs").status_code == 200
    client.cookies.set("rpa_session", "admin-session")
    assert client.post("/api/robots", json={"name": "r1"}).status_code == 403
    assert client.post("/api/robots", json={"name": "r1"}, headers={"Origin": "https://console.test"}).status_code == 200
    assert client.get("/internal/agent/work").status_code == 401


def test_live_websocket_run_failure_to_agent_resume_and_success(app):
    headers = {"Origin": "https://console.test"}
    with TestClient(app, base_url="https://console.test") as client:
        client.cookies.set("rpa_session", "admin-session")
        robot = client.post("/api/robots", json={"name": "r1"}, headers=headers).json()
        with client.websocket_connect("/api/robots/connect", headers={"Authorization": "Bearer " + robot["credential"]}) as ws:
            ws.send_json({"type": "hello", "journal_complete": True, "requests": {}, "deployments": [{"app_id": "app", "version": "1"}]})
            assert ws.receive_json()["type"] == "sync"
            ws.send_json({"type": "ready"})
            run_id = client.post("/api/runs", headers=headers, json={"name": "run", "robot_id": robot["id"],
                "snapshot": {"app_id": "app", "version": "1", "account_id": "original", "inputs": {"date": "2099-01-01"}}}).json()["id"]
            start = ws.receive_json()
            assert start["action"] == "start"
            seq = 0
            def send(kind, data=None, command=None):
                nonlocal seq
                seq += 1
                message = {"type": kind, "console_run_id": run_id, "execution_attempt_id": (command or start)["execution_attempt_id"],
                           "seq": seq, "data": data or {}}
                if kind == "result": message.update(request_id=command["request_id"], status="succeeded", result={})
                ws.send_json(message)
                response = ws.receive_json()
                assert response["type"] == "ack", response
                assert response["console_run_id"] == run_id
            send("program_started", {"local_run_id": "original-local"})
            send("resolved", {"inputs": {"date": "2099-01-01"}, "download_dir": "C:/Downloads"})
            send("attempt_finished", {"local_run_id": "original-local", "status": "failed", "recoverable": True})
            send("result", command=start)
            recovery = ws.receive_json()
            assert recovery["action"] == "open_recovery"
            send("recovery_started")
            send("result", command=recovery)
            internal = {"Authorization": "Bearer internal-secret"}
            job = client.post(f"/internal/runs/{run_id}/claim", headers=internal, json={}).json()
            response = client.post(f"/internal/runs/{run_id}/operations", headers=internal, json={
                "lease": job["lease"], "execution_attempt_id": job["execution_attempt_id"], "request_id": "resume-1", "action": "resume",
                "params": {"from_step": "S2", "step_result": {"observed": True}}})
            assert response.status_code == 200, response.text
            resume = ws.receive_json()
            resumed = {**resume, "execution_attempt_id": resume["next_attempt_id"]}
            send("program_started", {"local_run_id": "resumed-local"}, resumed)
            send("attempt_finished", {"local_run_id": "resumed-local", "status": "succeeded"}, resumed)
            send("result", command=resume)
            detail = client.get(f"/api/runs/{run_id}").json()
            assert len(detail["attempts"]) == 2
            assert client.get("/api/robots").json()[0]["active_run"] == run_id
            send("ended", command=resumed)
            assert client.get(f"/api/runs/{run_id}").json()["status"] == "succeeded"
            assert client.get("/api/robots").json()[0]["active_run"] is None
            client.cookies.set("rpa_session", "member-session")
            business = client.get(f"/api/business/runs/{run_id}").json()
            assert not {"snapshot", "attempts", "robot_id", "lease", "conclusion"} & business.keys()
