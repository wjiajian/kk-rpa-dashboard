from contextlib import contextmanager
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import tarfile

from cryptography.fernet import Fernet
import pytest
from sqlalchemy import select

from rpa_console.control import Control, Conflict
from rpa_console.credentials import CredentialStore
from rpa_console.publishing import Publishing
from rpa_console.publisher import Publisher, prepare_source
from rpa_console.storage import (Base, Database, ApplicationSource, ImportJob, ApplicationRelease,
    PublishedApplication, Robot, RobotDeployment, DeploymentJob, Run)


@pytest.fixture
def publishing(tmp_path):
    db = Database("sqlite:///" + str(tmp_path / "publishing.db"))
    Base.metadata.create_all(db.engine)
    return Publishing(db, CredentialStore(Fernet.generate_key()), tmp_path / "artifacts")


def make_repository(path):
    app = path / "apps" / "sample"
    app.mkdir(parents=True)
    (app / "app.toml").write_text('app_id="sample"\nname="Sample"\nentrypoint="sample.cli:main"\n[console]\ninput_schema="input.schema.json"\napplication="sample.program:APPLICATION"\nallowed_hosts=["example.invalid"]\n')
    (app / "input.schema.json").write_text('{"type":"object","additionalProperties":false,"properties":{}}')
    (app / "pyproject.toml").write_text('[project]\nname="sample"\nversion="1.0"\nrequires-python=">=3.12"\n[tool.uv.sources]\ncore={path="../../packages/core"}\n')
    (path / "packages/core").mkdir(parents=True)
    (path / "packages/core/pyproject.toml").write_text('[project]\nname="core"\nversion="1.0"\n')
    for filename in ("requirement.md", "elements.toml", "uv.lock"):
        (app / filename).write_text("# test fixture")
    (app / ".env").write_text("PRIVATE_FIXTURE=excluded")
    def git(*args):
        return subprocess.check_output(["git", "-C", str(path), *args], stderr=subprocess.DEVNULL).decode().strip()
    git("init", "--quiet")
    git("add", ".")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
    return git


def run_import(service, tmp_path, monkeypatch):
    from rpa_console import publisher
    git = make_repository(tmp_path / "repository")
    source = service.add_source("test", "https://example.invalid/repo.git", {"token": "PRIVATE_READ_TOKEN"})
    with service.db.transaction() as s:
        s.get(ApplicationSource, source["id"]).url = str(tmp_path / "repository")
    original = publisher.git_environment
    @contextmanager
    def local_test_transport(credentials, directory):
        with original(credentials, directory) as env:
            # Only test fixtures use the local Git transport; the public API refuses it.
            yield {**env, "GIT_ALLOW_PROTOCOL": "file"}
    monkeypatch.setattr(publisher, "git_environment", local_test_transport)
    job = service.import_source(source["id"], git("rev-parse", "HEAD"))
    assert Publisher(service).run_once()
    with service.db.transaction() as s:
        saved = service.import_view(s.get(ImportJob, job["id"]))
    assert saved["status"] == "ready", saved
    return job, git


def test_real_git_import_pins_commit_excludes_secrets_and_confirms_once(publishing, tmp_path, monkeypatch):
    job, git = run_import(publishing, tmp_path, monkeypatch)
    release = publishing.confirm(job["id"], ["sample"])[0]
    assert publishing.confirm(job["id"], ["sample"])[0]["id"] == release["id"]
    assert release["commit"] == git("rev-parse", "HEAD")
    assert release["module"] == "sample.program"
    assert "PRIVATE_READ_TOKEN" not in json.dumps(release)
    with tarfile.open(publishing.artifact_dir / (job["id"] + ".tar")) as archive:
        names = archive.getnames()
        assert "packages/core/pyproject.toml" in names
        assert "apps/sample/.env" not in names
    (tmp_path / "repository/apps/sample/requirement.md").write_text("new requirement")
    git("add", ".")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "next")
    with publishing.db.transaction() as s:
        assert s.get(ApplicationRelease, release["id"]).commit != git("rev-parse", "HEAD")
    next_job = publishing.import_source(job["source_id"], git("rev-parse", "HEAD"))
    Publisher(publishing).run_once()
    next_release = publishing.confirm(next_job["id"], ["sample"])[0]
    assert next_release["id"] != release["id"] and next_release["version"] == release["version"]


def test_sources_reject_embedded_secrets_and_invalid_transports(publishing):
    for url in ("file:///private/source", "https://user:SECRET@example.invalid/repo", "ssh://git:SECRET@example.invalid/repo", "git://example.invalid/repo"):
        with pytest.raises(Conflict):
            publishing.add_source("source", url)


def test_archive_path_and_link_rejection(tmp_path):
    for name, kind in (("../escape", tarfile.REGTYPE), ("safe", tarfile.SYMTYPE)):
        raw = tmp_path / "raw.tar"
        with tarfile.open(raw, "w") as output:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.linkname = "../escape"
            output.addfile(member, io.BytesIO(b""))
        with pytest.raises(ValueError):
            prepare_source(raw, tmp_path / "source", tmp_path / "filtered.tar")
        assert not (tmp_path.parent / "escape").exists()


def test_installation_ownership_release_identity_and_uninstall_refs(publishing, tmp_path, monkeypatch):
    job, _ = run_import(publishing, tmp_path, monkeypatch)
    release = publishing.confirm(job["id"], ["sample"])[0]
    control = Control(publishing.db, credentials=publishing.credentials)
    robot = control.add_robot("r")
    control.reconcile(robot["id"], {"deployments": []})
    publishing.reconcile(robot["id"], {"capabilities": ["deploy-v1"]})
    install = publishing.request_deployment(robot["id"], release["id"])
    command = publishing.commands(robot["id"])[0]
    assert command["job_id"] == install["id"]
    assert publishing.commands(robot["id"]) == []
    with publishing.db.transaction() as s:
        assert s.get(Robot, robot["id"]).deployment_job == install["id"]
    report = {"job_id": install["id"], "seq": 1, "status": "installed", "stage": "complete"}
    assert publishing.accept(robot["id"], report) == 1
    assert publishing.accept(robot["id"], report) == 1
    snapshot = {"app_id": "sample", "version": "1.0", "release_id": release["id"], "inputs": {}}
    run = control.create_run(robot["id"], snapshot, "published")
    with pytest.raises(Conflict, match="引用"):
        publishing.request_deployment(robot["id"], release["id"], "uninstall")
    with pytest.raises(Conflict):
        control.create_run(robot["id"], {**snapshot, "release_id": None}, "legacy-is-not-release")
    control.request_stop(run)
    remove = publishing.request_deployment(robot["id"], release["id"], "uninstall")
    with pytest.raises(Conflict, match="卸载"):
        control.create_run(robot["id"], snapshot, "new-reference")
    assert publishing.commands(robot["id"])[0]["action"] == "uninstall"
    publishing.accept(robot["id"], {"job_id": remove["id"], "seq": 1, "status": "uninstalled"})
    with publishing.db.transaction() as s:
        assert s.get(RobotDeployment, (robot["id"], release["id"])).status == "uninstalled"
        assert not s.get(Robot, robot["id"]).deployment_job
    with pytest.raises(Conflict):
        control.create_run(robot["id"], snapshot, "historical-rerun", rerun_of=run)


def test_invalid_source_cipher_fails_job_without_blocking_worker(publishing):
    source = publishing.add_source("broken", "https://example.invalid/repo.git")
    with publishing.db.transaction() as s:
        s.get(ApplicationSource, source["id"]).encrypted_credentials = "invalid-ciphertext"
    job = publishing.import_source(source["id"], "main")
    assert Publisher(publishing).run_once()
    with publishing.db.transaction() as s:
        saved = s.get(ImportJob, job["id"])
        assert saved.status == "failed"
        assert "invalid-ciphertext" not in saved.data["error"]
    assert Publisher(publishing).run_once() is False


def test_uncertain_install_holds_robot_until_executor_cleanup_report(publishing, tmp_path, monkeypatch):
    job, _ = run_import(publishing, tmp_path, monkeypatch)
    release = publishing.confirm(job['id'], ['sample'])[0]
    control = Control(publishing.db, credentials=publishing.credentials)
    robot = control.add_robot('cleanup')
    publishing.reconcile(robot['id'], {'capabilities': ['deploy-v1']})
    install = publishing.request_deployment(robot['id'], release['id'])
    publishing.commands(robot['id'])
    publishing.accept(robot['id'], {'job_id': install['id'], 'seq': 1, 'status': 'uncertain', 'stage': 'restart'})
    assert publishing.commands(robot['id']) == []
    assert publishing.request_deployment(robot['id'], release['id'])['id'] == install['id']
    with publishing.db.transaction() as s:
        assert s.get(Robot, robot['id']).deployment_job == install['id']
    cleanup = {'job_id': install['id'], 'seq': 2, 'status': 'failed', 'stage': 'operator_cleanup'}
    publishing.reconcile(robot['id'], {'capabilities': ['deploy-v1'], 'deployment_reports': [cleanup]})
    assert publishing.accept(robot['id'], cleanup) == 2
    with publishing.db.transaction() as s:
        assert s.get(Robot, robot['id']).deployment_job is None
        assert s.get(RobotDeployment, (robot['id'], release['id'])) is None
    assert publishing.request_deployment(robot['id'], release['id'])['id'] != install['id']


def test_maintenance_pauses_new_deployments_but_allows_assigned_reconciliation(publishing, tmp_path, monkeypatch):
    from rpa_console.maintenance import set_mode, status
    job, _ = run_import(publishing, tmp_path, monkeypatch)
    release = publishing.confirm(job['id'], ['sample'])[0]
    robot = Control(publishing.db).add_robot('maintenance')
    publishing.reconcile(robot['id'], {'capabilities': ['deploy-v1']})
    install = publishing.request_deployment(robot['id'], release['id'])
    set_mode(publishing.db, True)
    assert publishing.commands(robot['id']) == []
    queued_import = publishing.import_source(job['source_id'], 'main')
    assert Publisher(publishing).run_once() is False
    with publishing.db.transaction() as s:
        assert s.get(ImportJob, queued_import['id']).status == 'queued'
    set_mode(publishing.db, False)
    publishing.commands(robot['id'])
    set_mode(publishing.db, True)
    assert status(publishing.db)['drained'] is False
    publishing.reconcile(robot['id'], {'capabilities': ['deploy-v1']})
    assert publishing.commands(robot['id'])[0]['job_id'] == install['id']
    publishing.accept(robot['id'], {'job_id': install['id'], 'seq': 1, 'status': 'failed', 'stage': 'dependencies'})
    assert status(publishing.db)['drained'] is True


def test_plan_commit_survives_database_reload(publishing, tmp_path, monkeypatch):
    from rpa_console.storage import Task
    from rpa_console.tasks import Tasks
    imported, _ = run_import(publishing, tmp_path, monkeypatch)
    release = publishing.confirm(imported['id'], ['sample'])[0]
    control = Control(publishing.db, credentials=publishing.credentials)
    robot = control.add_robot('plan-version')
    publishing.reconcile(robot['id'], {'capabilities': ['deploy-v1']})
    job = publishing.request_deployment(robot['id'], release['id'])
    publishing.commands(robot['id'])
    publishing.accept(robot['id'], {'job_id': job['id'], 'seq': 1, 'status': 'installed'})
    tasks = Tasks(control)
    plan = tasks.save({'name': 'version-plan', 'robot_id': robot['id'], 'app_id': release['app_id'],
                      'version': release['version'], 'release_id': release['id'], 'input_bindings': {},
                      'download_dir': None, 'schedule': {'enabled': False, 'cron': ''}},
                     {'username': 'fixture', 'password': 'fixture'})
    with publishing.db.transaction() as s:
        assert tasks.view(s.get(Task, plan['id']))['commit'] == release['commit']
