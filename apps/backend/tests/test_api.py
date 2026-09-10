from hashlib import sha256
import base64
import os
from pathlib import Path
from time import time
import json

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import pytest

from rpa_console.api import Config, create_app
from rpa_console.storage import AuditLog, Base, Database, Evidence, LoginSession, Run, RunCredential, Operation, Event
from sqlalchemy import select

CREDENTIALS = {"username": "test-business-login", "password": "test-private-password-938!"}


@pytest.fixture
def app(tmp_path):
    db = Database("sqlite:///" + str(tmp_path / "api.db"))
    Base.metadata.create_all(db.engine)
    config = Config("unused", "internal-secret", public_url="https://console.test", evidence_dir=str(tmp_path / "evidence"), admins=("admin",),
                    credential_encryption_key=Fernet.generate_key().decode())
    with db.transaction() as s:
        for token, open_id in (("admin-session", "admin"), ("member-session", "member")):
            s.add(LoginSession(id=sha256(token.encode()).hexdigest(), expires=time() + 600,
                data={"kind": "user", "name": "test", "open_id": open_id}))
    application = create_app(config, db)
    application.state.test_config = config
    return application


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
                "snapshot": {"app_id": "app", "version": "1", "inputs": {"date": "2099-01-01"}},
                "credentials": CREDENTIALS}).json()["id"]
            start = ws.receive_json()
            assert start["action"] == "start"
            assert start["params"]["credentials"] == CREDENTIALS
            seq = 0
            def send(kind, data=None, command=None):
                nonlocal seq
                seq += 1
                message = {"type": kind, "console_run_id": run_id, "execution_attempt_id": (command or start)["execution_attempt_id"],
                           "seq": seq, "data": data or {}}
                if kind == "result": message.update(request_id=command["request_id"], status="succeeded", result=data or {})
                ws.send_json(message)
                response = ws.receive_json()
                assert response["type"] == "ack", response
                assert response["console_run_id"] == run_id
                return message
            send("program_started", {"local_run_id": "original-local"})
            send("resolved", {"inputs": {"date": "2099-01-01"}, "download_dir": "C:/Downloads"})
            png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")
            image = {"mimeType": "image/png", "data": base64.b64encode(png).decode()}
            first_image = send("evidence", {"step_id": "S1", "name": "S1.png", "image": image})
            ws.send_json(first_image)
            assert ws.receive_json()["seq"] == first_image["seq"]
            # Evidence is visible before the program finishes or Agent is invoked.
            evidence = client.get(f"/api/runs/{run_id}").json()["evidence"]
            assert len(evidence) == 1
            assert client.get(evidence[0]["url"]).content == png
            send("evidence", {"step_id": "S2", "name": "failure.png", "image": image})
            failure_evidence = client.get(f"/api/runs/{run_id}").json()["evidence"]
            assert len(failure_evidence) == 1
            assert failure_evidence[0]["id"] != evidence[0]["id"]
            assert client.get(evidence[0]["url"]).status_code == 404
            assert not (Path(app.state.test_config.evidence_dir) / evidence[0]["id"]).exists()
            send("attempt_finished", {"local_run_id": "original-local", "status": "failed", "recoverable": True})
            send("result", command=start)
            recovery = ws.receive_json()
            assert recovery["action"] == "open_recovery"
            send("recovery_started", {"capabilities": {"protocol": 2, "features": ["live_refs", "query", "observe_fields", "act_expect_read", "scope_path"]}})
            send("result", command=recovery)
            internal = {"Authorization": "Bearer internal-secret"}
            job = client.post(f"/internal/runs/{run_id}/claim", headers=internal, json={}).json()
            assert all(value not in json.dumps(job) for value in CREDENTIALS.values())
            observed = client.post(f"/internal/runs/{run_id}/operations", headers=internal, json={
                "lease": job["lease"], "execution_attempt_id": job["execution_attempt_id"], "request_id": "observe-1",
                "action": "observe", "params": {}})
            assert observed.status_code == 200
            observe = ws.receive_json()
            send("result", {"image": image, "nodes": []}, observe)
            result = client.get(f"/internal/runs/{run_id}/operations/observe-1", headers=internal).json()
            assert result["result"]["image"] == image
            assert len(client.get(f"/api/runs/{run_id}").json()["evidence"]) == 1
            assert client.get(failure_evidence[0]["url"]).status_code == 404
            response = client.post(f"/internal/runs/{run_id}/operations", headers=internal, json={
                "lease": job["lease"], "execution_attempt_id": job["execution_attempt_id"], "request_id": "resume-1", "action": "resume",
                "params": {"from_step": "S2", "step_result": {"observed": True}, "summary": "已核对现场，提交 S2 续跑并等待原程序校验。"}})
            assert response.status_code == 200, response.text
            resume = ws.receive_json()
            resumed = {**resume, "execution_attempt_id": resume["next_attempt_id"]}
            send("program_started", {"local_run_id": "resumed-local"}, resumed)
            send("evidence", {"step_id": "S2", "name": "S2.png", "image": image}, resumed)
            latest = client.get(f"/api/runs/{run_id}").json()["evidence"]
            stale_result = client.get(f"/internal/runs/{run_id}/operations/observe-1", headers=internal).json()
            assert "image" not in stale_result["result"]
            assert stale_result["result"]["screenshot_missing"] == "该截图已被替换或清理"
            assert stale_result["result"]["nodes"] == []
            send("evidence_missing", {"reason": "fixture capture failed"}, resumed)
            assert client.get(f"/api/runs/{run_id}").json()["evidence"] == latest
            send("attempt_finished", {"local_run_id": "resumed-local", "status": "succeeded"}, resumed)
            send("result", command=resume)
            detail = client.get(f"/api/runs/{run_id}").json()
            assert len(detail["attempts"]) == 2
            assert "account_id" not in detail["snapshot"]
            assert detail["recovery_rounds"][0]["summary"] == "已核对现场，提交 S2 续跑并等待原程序校验。"
            assert all(value not in json.dumps(detail) for value in CREDENTIALS.values())
            assert client.get("/api/robots").json()[0]["active_run"] == run_id
            send("ended", command=resumed)
            assert client.get(f"/api/runs/{run_id}").json()["status"] == "succeeded"
            assert client.get("/api/robots").json()[0]["active_run"] is None
            # A reconnect can still drain an old queued image after resume/end.
            ws.send_json(first_image)
            assert ws.receive_json()["seq"] == seq
            client.cookies.set("rpa_session", "member-session")
            business = client.get(f"/api/business/runs/{run_id}").json()
            assert business["evidence"] == latest
            assert len(business["evidence"]) == 1
            assert all(client.get(item["url"]).content == png for item in business["evidence"])
            assert not {"snapshot", "attempts", "robot_id", "lease", "conclusion"} & business.keys()
            with app.state.database.transaction() as session:
                for table in (Run, Operation, Event):
                    rows = [row.data for row in session.scalars(select(table))]
                    assert all(value not in json.dumps(rows) for value in CREDENTIALS.values())
                encrypted = session.get(RunCredential, run_id).encrypted
                assert all(value not in encrypted for value in CREDENTIALS.values())
                assert len(list(session.scalars(select(Evidence)))) == 1
            assert [p.name for p in Path(app.state.test_config.evidence_dir).iterdir()] == [latest[0]["id"]]
            assert TestClient(app, base_url="https://console.test").get(evidence[0]["url"]).status_code == 401


def queued_run(app):
    client = TestClient(app, base_url="https://console.test")
    client.cookies.set("rpa_session", "admin-session")
    client.headers["Origin"] = "https://console.test"
    robot = app.state.control.add_robot("credential-test")
    app.state.control.reconcile(robot["id"], {"deployments": [{"app_id": "app", "version": "1"}]})
    body = {"name": "run", "robot_id": robot["id"], "snapshot": {
        "app_id": "app", "version": "1", "inputs": {}}, "credentials": CREDENTIALS}
    return client, robot, body


def test_usage_reports_are_cumulative_idempotent_and_survive_run_end(app):
    client, _, body = queued_run(app)
    run_id = client.post("/api/runs", json=body).json()["id"]
    url = f"/internal/runs/{run_id}/usage"
    report = {"session_id": "session-one", "revision": 10, "input": 100, "output": 50,
              "cache_read": 200, "cache_write": 0, "requests": 3, "unreported_responses": 1}
    assert client.post(url, json=report).status_code == 401
    headers = {"Authorization": "Bearer internal-secret"}
    for payload in (report, report, {**report, "revision": 9, "input": 999}):
        assert client.post(url, json=payload, headers=headers).status_code == 200
    result = client.get(f"/api/runs/{run_id}").json()
    assert result["token_usage"]["total"] == 350
    assert "token_sessions" not in result
    with app.state.database.transaction() as s:
        row = s.get(Run, run_id)
        row.data = {**row.data, "status": "failed", "phase": "ended"}
    assert client.post(url, json={**report, "session_id": "session-two"}, headers=headers).status_code == 200
    assert client.get(f"/api/runs/{run_id}").json()["token_usage"]["total"] == 700
    assert client.post(url, json={**report, "input": -1}, headers=headers).status_code == 422


def test_startup_removes_older_screenshots_per_run(app):
    client, robot, body = queued_run(app)
    first = client.post("/api/runs", json=body).json()["id"]
    second = client.post("/api/runs", json={**body, "name": "second"}).json()["id"]
    root = Path(app.state.test_config.evidence_dir)
    with app.state.database.transaction() as s:
        for image_id, run_id, timestamp in (("old", first, 1), ("latest", first, 2), ("other-run", second, 3)):
            s.add(Evidence(id=image_id, run_id=run_id, mime="image/png"))
            target = root / image_id
            target.write_bytes(b"fixture screenshot")
            os.utime(target, (timestamp, timestamp))
    with TestClient(app, base_url="https://console.test") as restarted:
        restarted.cookies.set("rpa_session", "admin-session")
        assert [e["id"] for e in restarted.get(f"/api/runs/{first}").json()["evidence"]] == ["latest"]
        assert [e["id"] for e in restarted.get(f"/api/runs/{second}").json()["evidence"]] == ["other-run"]
        assert {p.name for p in root.iterdir()} == {"latest", "other-run"}
        assert restarted.get("/api/business/screenshots/old").status_code == 404


@pytest.mark.parametrize("invalid", ["format", "attempt", "sequence"])
def test_rejected_image_does_not_delete_last_accepted_screenshot(app, invalid):
    client, robot, body = queued_run(app)
    with client:
        with client.websocket_connect("/api/robots/connect", headers={"Authorization": "Bearer " + robot["credential"]}) as ws:
            ws.send_json({"type": "hello", "journal_complete": True, "requests": {}, "deployments": [{"app_id": "app", "version": "1"}]})
            assert ws.receive_json()["type"] == "sync"
            ws.send_json({"type": "ready"})
            run_id = client.post("/api/runs", json=body).json()["id"]
            start = ws.receive_json()
            event = {"type": "evidence", "console_run_id": run_id, "execution_attempt_id": start["execution_attempt_id"],
                "seq": 1, "data": {"image": {"mimeType": "image/png", "data": base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()}}}
            ws.send_json(event)
            assert ws.receive_json()["type"] == "ack"
            original = client.get(f"/api/runs/{run_id}").json()["evidence"]
            bad = {**event, "seq": 2}
            if invalid == "format": bad["data"] = {"image": {"mimeType": "image/png", "data": "bm90LXBuZw=="}}
            if invalid == "attempt": bad["execution_attempt_id"] = "stale-attempt"
            if invalid == "sequence": bad["seq"] = 3
            ws.send_json(bad)
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()
        assert client.get(f"/api/runs/{run_id}").json()["evidence"] == original
        assert client.get(original[0]["url"]).status_code == 200
        assert [p.name for p in Path(app.state.test_config.evidence_dir).iterdir()] == [original[0]["id"]]


def test_credentials_survive_restart_rerun_and_are_purged_with_run(app):
    client, robot, body = queued_run(app)
    response = client.post("/api/runs", json=body)
    assert response.status_code == 200, response.text
    first = response.json()["id"]
    assert client.post(f"/api/runs/{first}/stop", json={}).status_code == 200
    restarted = create_app(app.state.test_config, Database(str(app.state.database.engine.url)))
    with TestClient(restarted, base_url="https://console.test") as other:
        other.cookies.set("rpa_session", "admin-session")
        response = other.post(f"/api/runs/{first}/rerun", json={}, headers={"Origin": "https://console.test"})
        assert response.status_code == 200, response.text
        second = response.json()["id"]
        with restarted.state.database.transaction() as session:
            assert restarted.state.control.credentials.read(session, second) == CREDENTIALS
            assert session.get(RunCredential, first).encrypted != session.get(RunCredential, second).encrypted
            run = session.get(Run, first)
            run.data = {**run.data, "ended": time() - 31 * 86400}
        response = other.post(f"/internal/runs/{first}/purge", json={}, headers={"Authorization": "Bearer internal-secret"})
        assert response.status_code == 200, response.text
        with restarted.state.database.transaction() as session:
            assert session.get(RunCredential, first) is None
            assert restarted.state.control.credentials.read(session, second) == CREDENTIALS


def test_credentials_required_and_validation_never_echoes_submitted_secrets(app):
    client, robot, body = queued_run(app)
    missing = {key: value for key, value in body.items() if key != "credentials"}
    assert client.post("/api/runs", json=missing).status_code == 422
    invalid = {**body, "credentials": {**CREDENTIALS, "password": {"unexpected": CREDENTIALS["password"]}}}
    response = client.post("/api/runs", json=invalid)
    assert response.status_code == 422
    assert CREDENTIALS["password"] not in response.text
    assert all("input" not in error for error in response.json()["detail"])
    client.cookies.set("rpa_session", "member-session")
    assert client.post("/api/runs", json=body).status_code == 403


def test_wrong_encryption_key_does_not_dispatch_or_expose_credentials(app):
    from rpa_console.credentials import CredentialError, CredentialStore
    client, robot, body = queued_run(app)
    run_id = client.post("/api/runs", json=body).json()["id"]
    control = app.state.control
    control.tick({robot["id"]})
    control.credentials = CredentialStore(Fernet.generate_key())
    with pytest.raises(CredentialError):
        control.commands(robot["id"])
    control.request_stop(run_id, "credentials_unavailable")
    assert client.get("/api/robots").json()[0]["active_run"] is None
    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["status"] == "failed"
    assert all(value not in json.dumps(detail) for value in CREDENTIALS.values())


def test_robot_schema_reaches_api_and_rejects_invalid_inputs_before_queue(app):
    headers = {"Origin": "https://console.test"}
    client = TestClient(app, base_url="https://console.test")
    client.cookies.set("rpa_session", "admin-session")
    robot = client.post("/api/robots", json={"name": "schema-robot"}, headers=headers).json()
    declaration = {"app_id": "app", "version": "1", "input_schema": {
        "type": "object", "required": ["target_date"], "additionalProperties": False,
        "properties": {"target_date": {"type": "string", "format": "date"}}}}
    with client.websocket_connect("/api/robots/connect", headers={"Authorization": "Bearer " + robot["credential"]}) as ws:
        ws.send_json({"type": "hello", "requests": {}, "journal_complete": True, "deployments": [declaration]})
        assert ws.receive_json()["type"] == "sync"
        reported = client.get("/api/robots").json()[0]["deployments"][0]
        assert reported["schema_status"] == "valid"
        assert reported["input_schema"] == declaration["input_schema"]
        body = {"name": "schema-run", "robot_id": robot["id"], "credentials": CREDENTIALS,
                "snapshot": {"app_id": "app", "version": "1", "inputs": {"target_date": "2026-02-30"}}}
        assert client.post("/api/runs", headers=headers, json=body).status_code == 409
        assert client.get("/api/runs").json() == []
        body["snapshot"]["inputs"]["target_date"] = "2026-09-08"
        assert client.post("/api/runs", headers=headers, json=body).status_code == 200
    app.state.control.reconcile(robot["id"], {"requests": {}, "deployments": [
        {"app_id": "app", "version": "1", "schema_status": "invalid", "schema_error": "声明文件损坏"}]})
    assert client.post("/api/runs", headers=headers, json=body).status_code == 409


def test_plan_api_persists_permissions_and_immutable_run_credentials(app):
    headers = {"Origin": "https://console.test"}
    client = TestClient(app, base_url="https://console.test")
    client.cookies.set("rpa_session", "admin-session")
    robot = client.post("/api/robots", json={"name": "planned"}, headers=headers).json()
    app.state.control.reconcile(robot["id"], {"deployments": [{"app_id": "a", "version": "1", "input_schema": {
        "type": "object", "required": ["date"], "properties": {"date": {"type": "string", "format": "date"}}}}]})
    config = {"name": "plan", "robot_id": robot["id"], "app_id": "a", "version": "1",
              "input_bindings": {"date": {"kind": "literal", "value": "2026-09-08"}}, "credentials": CREDENTIALS}
    response = client.post("/api/tasks", headers=headers, json=config)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert "test-private" not in response.text and "test-business-login" not in response.text
    assert client.get("/api/runs").json() == []
    assert client.get("/api/tasks").json()[0]["id"] == plan["id"]
    trigger = {"request_id": "click-1"}
    run = client.post(f'/api/tasks/{plan["id"]}/runs', headers=headers, json=trigger).json()
    assert client.post(f'/api/tasks/{plan["id"]}/runs', headers=headers, json=trigger).json() == run
    updated = {**config, "revision": 1, "credentials": {**CREDENTIALS, "password": "REPLACEMENT"}}
    assert client.patch(f'/api/tasks/{plan["id"]}', headers=headers, json=updated).status_code == 200
    assert client.patch(f'/api/tasks/{plan["id"]}', headers=headers, json=updated).status_code == 409
    with app.state.database.transaction() as s:
        assert app.state.control.credentials.read(s, run["id"]) == CREDENTIALS
    client.cookies.set("rpa_session", "member-session")
    for path in ("/api/tasks", f'/api/tasks/{plan["id"]}'):
        assert client.get(path).status_code == 403
    assert client.post(f'/api/tasks/{plan["id"]}/runs', headers=headers, json=trigger).status_code == 403


def test_temporary_run_request_retries_are_idempotent(app):
    headers = {"Origin": "https://console.test"}
    client = TestClient(app, base_url="https://console.test")
    client.cookies.set("rpa_session", "admin-session")
    robot = client.post("/api/robots", json={"name": "temporary"}, headers=headers).json()
    app.state.control.reconcile(robot["id"], {"deployments": [{"app_id": "a", "version": "1"}]})
    body = {"name": "temporary", "robot_id": robot["id"], "snapshot": {"app_id": "a", "version": "1", "inputs": {}}, "credentials": CREDENTIALS, "request_id": "click-temp"}
    first = client.post("/api/runs", headers=headers, json=body)
    assert first.status_code == 200
    assert client.post("/api/runs", headers=headers, json=body).json() == first.json()
    assert client.post("/api/runs", headers=headers, json={**body, "name": "different"}).status_code == 409


def test_publishing_permissions_encrypted_source_and_assigned_artifact(app, tmp_path):
    from rpa_console.storage import ApplicationSource, ImportJob, Robot, DeploymentJob
    from uuid import uuid4
    client = TestClient(app, base_url="https://console.test")
    headers = {"Origin": "https://console.test"}
    paths = ["/api/application-sources", "/api/application-imports", "/api/applications",
             "/api/robots/missing/deployments", "/api/deployment-jobs/missing"]
    for path in paths:
        assert client.get(path).status_code == 401
    client.cookies.set("rpa_session", "member-session")
    for path in paths:
        assert client.get(path).status_code == 403
    client.cookies.set("rpa_session", "admin-session")
    body = {"name": "source", "url": "https://example.invalid/repo.git", "credentials": {"token": "PRIVATE_GIT_TEST_TOKEN"}}
    assert client.post(paths[0], json=body).status_code == 403
    source = client.post(paths[0], json=body, headers=headers)
    assert source.status_code == 200
    assert "PRIVATE_GIT_TEST_TOKEN" not in source.text
    source_id = source.json()["id"]
    control, db = app.state.control, app.state.database
    owner, other = control.add_robot("owner"), control.add_robot("other")
    import_id = str(uuid4())
    with db.transaction() as s:
        saved = s.get(ApplicationSource, source_id)
        assert saved.encrypted_credentials and "PRIVATE_GIT_TEST_TOKEN" not in saved.encrypted_credentials
        s.get(Robot, owner["id"]).capabilities = ["deploy-v1"]
        s.add(ImportJob(id=import_id, source_id=source_id, created=time(), status="ready", data={
            "ref": "main", "commit": "a" * 40, "artifact": "fixture.tar", "applications": [
                {"app_id": "sample", "name": "sample", "version": "1", "path": "apps/sample", "errors": [],
                 "input_schema": {"type": "object", "properties": {}}}]}))
    response = client.post(f"/api/application-imports/{import_id}/confirm", json={"app_ids": ["sample"]}, headers=headers)
    assert response.status_code == 200, response.text
    release = response.json()[0]
    job = client.post(f'/api/robots/{owner["id"]}/deployments', json={"release_id": release["id"]}, headers=headers).json()
    artifact = Path(app.state.test_config.evidence_dir).parent / "artifacts/fixture.tar"
    artifact.write_bytes(b"fixture-source-artifact")
    path = f'/api/robot-deployment-jobs/{job["id"]}/artifact'
    assert client.get(path).status_code == 401  # Admin cookie does not grant robot download access.
    owner_auth = {"Authorization": "Bearer " + owner["credential"]}
    assert client.get(path, headers=owner_auth).status_code == 409  # Queued is not assigned.
    with db.transaction() as s:
        s.get(DeploymentJob, job["id"]).status = "installing"
        s.get(Robot, owner["id"]).deployment_job = job["id"]
    assert client.get(path, headers={"Authorization": "Bearer " + other["credential"]}).status_code == 409
    assert client.get(path, headers=owner_auth).content == b"fixture-source-artifact"


def test_maintenance_rejects_new_run_with_visible_service_error(app):
    from rpa_console.maintenance import set_mode
    set_mode(app.state.database, True)
    client = TestClient(app, base_url='https://console.test')
    client.cookies.set('rpa_session', 'admin-session')
    response = client.post('/api/runs', headers={'Origin': 'https://console.test'}, json={
        'name': 'maintenance', 'robot_id': 'unused',
        'snapshot': {'app_id': 'app', 'version': '1', 'inputs': {}}, 'credentials': CREDENTIALS})
    assert response.status_code == 503
    assert '维护中' in response.json()['detail']


def test_run_history_is_filtered_and_paginated_by_the_server(app):
    with app.state.database.transaction() as session:
        robot = app.state.control.add_robot("history-robot")
        for index in range(23):
            session.add(Run(id=f"run-{index:02d}", robot_id=robot["id"], created=float(index), data={
                "name": f"月报 {index:02d}", "status": "failed" if index % 2 else "succeeded", "seq": 0,
                "recovery_used": 0,
                "snapshot": {"app_id": "sales" if index < 20 else "stock", "version": "1", "inputs": {}},
            }))
    client = TestClient(app, base_url="https://console.test")
    client.cookies.set("rpa_session", "admin-session")
    second = client.get("/api/runs/history?page=2&page_size=10").json()
    assert {key: second[key] for key in ("total", "page", "page_size", "pages")} == {
        "total": 23, "page": 2, "page_size": 10, "pages": 3}
    assert [item["id"] for item in second["items"]] == [f"run-{index:02d}" for index in range(12, 2, -1)]
    filtered = client.get("/api/runs/history?page=1&page_size=5&q=月报%202&status=succeeded&app_id=stock").json()
    assert filtered["total"] == 2
    assert [item["id"] for item in filtered["items"]] == ["run-22", "run-20"]
    assert client.get("/api/runs/history?page=0").status_code == 422

    client.cookies.set("rpa_session", "member-session")
    business = client.get("/api/business/runs/history?page=3&page_size=10").json()
    assert business["total"] == 23 and len(business["items"]) == 3
    assert "snapshot" not in business["items"][0]


def test_audit_log_records_admin_actions_without_secrets_and_supports_pagination(app):
    client = TestClient(app, base_url="https://console.test")
    client.cookies.set("rpa_session", "admin-session")
    headers = {"Origin": "https://console.test"}
    robot = None
    for index in range(12):
        response = client.post("/api/robots", json={"name": f"审计机器人 {index:02d}"}, headers=headers)
        assert response.status_code == 200
        robot = response.json()
    app.state.control.reconcile(robot["id"], {"deployments": [{"app_id": "audit-app", "version": "1"}]})
    run = client.post("/api/runs", headers=headers, json={
        "name": "敏感信息检查", "robot_id": robot["id"],
        "snapshot": {"app_id": "audit-app", "version": "1", "inputs": {"date": "2026-09-10"}},
        "credentials": CREDENTIALS,
    })
    assert run.status_code == 200
    page = client.get("/api/audit-logs?page=2&page_size=5&action=robot.create").json()
    assert page["total"] == 12 and page["pages"] == 3 and len(page["items"]) == 5
    assert all(item["actor_open_id"] == "admin" and item["actor_name"] == "test" for item in page["items"])
    assert all(item["action"] == "robot.create" for item in page["items"])
    found = client.get("/api/audit-logs?q=审计机器人%2007").json()
    assert found["total"] == 0  # Search is deliberately limited to actor and immutable target id.

    with app.state.database.transaction() as session:
        rows = list(session.scalars(select(AuditLog)))
        assert len(rows) == 13
        serialized = json.dumps([row.details for row in rows], ensure_ascii=False)
        assert all(secret not in serialized for secret in CREDENTIALS.values())
        assert "credential" not in serialized.lower() and "token" not in serialized.lower()

    client.cookies.set("rpa_session", "member-session")
    assert client.get("/api/audit-logs").status_code == 403
