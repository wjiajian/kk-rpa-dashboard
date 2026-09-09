"""Single publisher process: fetch pinned Git source and statically preview applications."""
from .maintenance import gate
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib

from sqlalchemy import select

from .control import Conflict
from .credentials import CredentialStore
from .publishing import Publishing
from .schemas import schema_validator
from .storage import ApplicationSource, Database, ImportJob

EXCLUDED = {".git", ".venv", "profiles", "runs", "runtime", "__pycache__", "node_modules", ".env"}
MAX_ARCHIVE = 512 * 1024 * 1024


def excluded(path):
    return any(part in EXCLUDED or part.endswith(".local.toml") or part.endswith(".local.clixml")
               or part.startswith(".env.") and part != ".env.example" for part in path.parts)


def safe_member(member):
    path = PurePosixPath(member.name)
    if path.is_absolute() or ".." in path.parts or "\\" in member.name or ":" in member.name:
        raise ValueError("源码包包含越界路径")
    if not member.isdir() and not member.isfile():
        raise ValueError("源码包不支持链接或特殊文件")
    return path


def prepare_source(raw_archive, source_root, artifact):
    total = 0
    names = set()
    with tarfile.open(raw_archive, "r:") as source, tarfile.open(artifact, "w:") as output:
        for member in source:
            relative = safe_member(member)
            if str(relative) in names:
                raise ValueError("源码包包含重复路径")
            names.add(str(relative))
            if excluded(relative):
                continue
            total += member.size
            if total > MAX_ARCHIVE:
                raise ValueError("源码包超过 512 MiB")
            if relative.name == ".gitmodules":
                raise ValueError("首版不支持 Git 子模块")
            destination = source_root.joinpath(*relative.parts)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            data = source.extractfile(member).read()
            if data.startswith(b"version https://git-lfs.github.com/spec/v1"):
                raise ValueError("首版不支持 Git LFS 文件")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            member.mode = 0o755 if member.mode & 0o111 else 0o644
            member.uid = member.gid = 0
            member.uname = member.gname = ""
            output.addfile(member, io.BytesIO(data))


def scan_applications(root):
    applications = []
    seen = set()
    for manifest in sorted((root / "apps").glob("*/app.toml")):
        relative = manifest.parent.relative_to(root).as_posix()
        entry = {"path": relative, "app_id": relative, "name": relative}
        try:
            app = tomllib.loads(manifest.read_text(encoding="utf-8"))
            if not all(isinstance(app.get(key), str) and app[key] for key in ("app_id", "name", "entrypoint")):
                raise ValueError("app.toml 缺少 app_id/name/entrypoint")
            entry.update(app_id=app["app_id"], name=app["name"])
            if app["app_id"] in seen:
                raise ValueError("仓库内 app_id 重复")
            seen.add(app["app_id"])
            for name in ("requirement.md", "elements.toml", "pyproject.toml", "uv.lock"):
                if not (manifest.parent / name).is_file():
                    raise ValueError(f"缺少 {name}")
            project = tomllib.loads((manifest.parent / "pyproject.toml").read_text())
            metadata = project.get("project", {})
            if not all(isinstance(metadata.get(k), str) and metadata[k] for k in ("name", "version", "requires-python")):
                raise ValueError("pyproject.toml 需要静态名称、版本和 Python 要求")
            console = app.get("console", {})
            reference = console.get("input_schema")
            if not isinstance(reference, str) or not reference or Path(reference).is_absolute():
                raise ValueError("缺少 console.input_schema 相对路径")
            schema_path = (manifest.parent / reference).resolve()
            if not schema_path.is_relative_to(manifest.parent.resolve()):
                raise ValueError("参数声明必须位于应用目录内")
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            schema_validator(schema)
            application = console.get("application", "")
            if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:APPLICATION", application):
                raise ValueError("console.application 必须为模块路径:APPLICATION")
            hosts = console.get("allowed_hosts")
            if (not isinstance(hosts, list) or not hosts or any(not isinstance(h, str)
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", h) for h in hosts)):
                raise ValueError("console.allowed_hosts 必须声明允许访问的业务域名")
            # Validate local dependency paths recursively while retaining repository layout.
            pending, checked = [manifest.parent], set()
            while pending:
                folder = pending.pop().resolve()
                if folder in checked:
                    continue
                if not folder.is_relative_to(root.resolve()) or not (folder / "pyproject.toml").is_file():
                    raise ValueError("本地依赖缺失或超出源码目录")
                checked.add(folder)
                config = tomllib.loads((folder / "pyproject.toml").read_text())
                for dependency in config.get("tool", {}).get("uv", {}).get("sources", {}).values():
                    for alternative in dependency if isinstance(dependency, list) else [dependency]:
                        if isinstance(alternative, dict) and "path" in alternative:
                            if Path(alternative["path"]).is_absolute():
                                raise ValueError("本地依赖必须为仓库内相对路径")
                            pending.append(folder / alternative["path"])
            entry.update(version=metadata["version"], package=metadata["name"], requires_python=metadata["requires-python"],
                module=application.split(":")[0], input_schema=schema, allowed_hosts=hosts)
        except (ValueError, OSError, TypeError, AttributeError) as error:
            # Parser errors may include source content; only our explicit validation messages are exposed.
            entry["error"] = str(error) if type(error) is ValueError else f"声明读取失败（{type(error).__name__}）"
        applications.append(entry)
    if not applications:
        raise ValueError("未找到 apps/*/app.toml")
    duplicate_ids = {entry["app_id"] for entry in applications if sum(other["app_id"] == entry["app_id"] for other in applications) > 1}
    for entry in applications:
        if entry["app_id"] in duplicate_ids:
            entry["error"] = "仓库内 app_id 重复"
    return applications


@contextmanager
def git_environment(credentials, directory):
    # No inherited model/business secrets, global helpers, or interactive credential prompts.
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "SSL_CERT_FILE", "SSL_CERT_DIR") if key in os.environ}
    env.update(HOME=str(directory), GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0",
               GIT_ALLOW_PROTOCOL="https:ssh", GIT_LFS_SKIP_SMUDGE="1")
    if credentials.get("token"):
        askpass = directory / "askpass.py"
        askpass.write_text("#!" + sys.executable + "\nimport os,sys\nprint(os.environ['GIT_SOURCE_USERNAME'] if 'username' in sys.argv[1].lower() else os.environ['GIT_SOURCE_TOKEN'])\n")
        askpass.chmod(0o700)
        env.update(GIT_ASKPASS=str(askpass), GIT_SOURCE_USERNAME=credentials.get("username") or "git", GIT_SOURCE_TOKEN=credentials["token"])
    key_path = directory / "source-key"
    if credentials.get("ssh_private_key"):
        key_path.write_text(credentials["ssh_private_key"])
        key_path.chmod(0o600)
    known_hosts = os.getenv("GIT_KNOWN_HOSTS_FILE", "/data/git/known_hosts")
    ssh = ["ssh", "-F", os.devnull, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known_hosts}"]
    if key_path.exists():
        ssh += ["-o", "IdentitiesOnly=yes", "-i", str(key_path)]
    env["GIT_SSH_COMMAND"] = shlex.join(ssh)
    yield env


class Publisher:
    def __init__(self, publishing):
        self.service, self.db = publishing, publishing.db

    def run_once(self):
        with self.db.transaction() as s:
            if gate(s).maintenance:
                return False
            job = s.scalar(select(ImportJob).where(ImportJob.status.in_(["queued", "fetching"])).order_by(ImportJob.created).limit(1))
            if not job:
                return False
            job.status = "fetching"
            source = s.get(ApplicationSource, job.source_id)
            encrypted, source_id = source.encrypted_credentials, source.id
            job_id, url, ref = job.id, source.url, job.data.get("commit", job.data["ref"])
        artifact = self.service.artifact_dir / f"{job_id}.tar"
        try:
            secret = {}
            if encrypted:
                payload = json.loads(self.service.credentials.cipher.decrypt(encrypted))
                if payload.get("source_id") != source_id:
                    raise ValueError("Git 凭据来源不匹配")
                secret = payload["credentials"]
            with tempfile.TemporaryDirectory(prefix="rpa-import-") as temporary:
                directory = Path(temporary)
                repo, root = directory / "git", directory / "source"
                repo.mkdir(); root.mkdir()
                with git_environment(secret, directory) as env:
                    def git(*args, output=None):
                        result = subprocess.run(["git", "-C", str(repo), *args], env=env, stdin=subprocess.DEVNULL,
                            stdout=output if output else subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
                        if result.returncode:
                            raise ValueError(f"Git {args[0]} 失败，请检查来源、引用和只读凭据")
                        return result.stdout.decode().strip() if result.stdout else ""
                    git("init", "--quiet")
                    git("fetch", "--depth=1", "--no-tags", "--", url, ref)
                    commit = git("rev-parse", "FETCH_HEAD^{commit}")
                    with self.db.transaction() as s:
                        job = s.get(ImportJob, job_id)
                        job.data = {**job.data, "commit": commit}
                    tree = git("ls-tree", "-r", commit)
                    if any(line.startswith("160000 ") for line in tree.splitlines()):
                        raise ValueError("首版不支持 Git 子模块")
                    raw = directory / "source.tar"
                    with raw.open("wb") as output:
                        git("archive", "--format=tar", commit, output=output)
                staged = directory / "filtered.tar"
                prepare_source(raw, root, staged)
                applications = scan_applications(root)
                # Import job owns this path; confirmed releases never rewrite it.
                shutil.copyfile(staged, artifact)
                with self.db.transaction() as s:
                    job = s.get(ImportJob, job_id)
                    job.status = "ready"
                    job.data = {**job.data, "artifact": artifact.name, "applications": applications}
        except Exception as error:
            artifact.unlink(missing_ok=True)
            message = str(error) if type(error) is ValueError else f"导入失败（{type(error).__name__}）"
            with self.db.transaction() as s:
                job = s.get(ImportJob, job_id)
                job.status, job.data = "failed", {**job.data, "error": message}
        return True


def main():
    import fcntl
    service = Publishing(Database(os.environ["DATABASE_URL"]), CredentialStore(os.environ["CREDENTIAL_ENCRYPTION_KEY"]), os.environ.get("ARTIFACT_DIR", "/data/artifacts"))
    # One worker per shared artifact directory, including after a container restart.
    with (service.artifact_dir / ".publisher.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        worker = Publisher(service)
        while True:
            try:
                if not worker.run_once():
                    time.sleep(1)
            except Exception as error:
                print(f"发布作业循环失败：{type(error).__name__}", flush=True)
                time.sleep(3)


if __name__ == "__main__":
    main()
