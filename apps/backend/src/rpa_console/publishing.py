"""Git import catalogue and durable robot installation coordination."""
from .maintenance import gate
from copy import deepcopy
import json
from pathlib import Path
import re
from time import time
from urllib.parse import urlsplit

from sqlalchemy import select

from .control import Conflict, TERMINAL
from .storage import (ApplicationSource, ImportJob, PublishedApplication, ApplicationRelease,
                      RobotDeployment, DeploymentJob, Robot, Run, Task, uid)


class Publishing:
    def __init__(self, database, credentials, artifact_dir):
        self.db, self.credentials = database, credentials
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def add_source(self, name, url, credentials=None):
        address = urlsplit(url)
        if (address.scheme not in {"https", "ssh"} or not address.hostname or address.password
                or (address.scheme == "https" and address.username) or address.query or address.fragment
                or any(c.isspace() for c in url)):
            raise Conflict("Git 来源必须为不含口令的 HTTPS 或 SSH URL")
        if not name.strip():
            raise Conflict("请输入来源名称")
        secret = credentials or {}
        if address.scheme == "https" and secret.get("ssh_private_key"):
            raise Conflict("HTTPS 来源请使用账号和只读令牌")
        if address.scheme == "ssh" and secret.get("token"):
            raise Conflict("SSH 来源请使用只读部署密钥")
        with self.db.transaction() as s:
            source_id = uid()
            encrypted = self.credentials.cipher.encrypt(json.dumps({"source_id": source_id, "credentials": secret}).encode()).decode() if secret else None
            source = ApplicationSource(id=source_id, name=name.strip(), url=url, encrypted_credentials=encrypted)
            s.add(source)
            return self.source_view(source)

    @staticmethod
    def source_view(source):
        return {"id": source.id, "name": source.name, "url": source.url, "credentials_configured": bool(source.encrypted_credentials)}

    def import_source(self, source_id, ref):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", ref):
            raise Conflict("请输入分支、tag 或完整 commit")
        with self.db.transaction() as s:
            if s.get(ApplicationSource, source_id) is None:
                raise Conflict("Git 来源不存在")
            job = ImportJob(id=uid(), source_id=source_id, status="queued", data={"ref": ref}, created=time())
            s.add(job)
            return self.import_view(job)

    @staticmethod
    def import_view(job):
        return {"id": job.id, "source_id": job.source_id, "created": job.created, "status": job.status,
                **{k: v for k, v in job.data.items() if k != "artifact"}}

    def confirm(self, job_id, selected):
        if not selected or len(selected) != len(set(selected)):
            raise Conflict("请选择要导入的应用")
        with self.db.transaction() as s:
            job = s.scalar(select(ImportJob).where(ImportJob.id == job_id).with_for_update())
            if not job or job.status not in {"ready", "confirmed"}:
                raise Conflict("导入尚未完成预览")
            # Serialize confirmation of the same source across import jobs.
            s.scalar(select(ApplicationSource).where(ApplicationSource.id == job.source_id).with_for_update())
            previews = {entry["app_id"]: entry for entry in job.data["applications"] if not entry.get("error")}
            if any(key not in previews for key in selected):
                raise Conflict("选中的应用存在声明错误或不在本次预览中")
            releases = []
            for key in selected:
                entry = previews[key]
                app = s.scalar(select(PublishedApplication).where(PublishedApplication.source_id == job.source_id, PublishedApplication.app_id == key))
                if not app:
                    app = PublishedApplication(id=uid(), source_id=job.source_id, app_id=key, name=entry["name"])
                    s.add(app)
                    s.flush()
                release = s.scalar(select(ApplicationRelease).where(ApplicationRelease.application_id == app.id, ApplicationRelease.commit == job.data["commit"]))
                if not release:
                    release = ApplicationRelease(id=uid(), application_id=app.id, commit=job.data["commit"],
                        version=entry["version"], data={**deepcopy(entry), "artifact": job.data["artifact"]})
                    s.add(release)
                releases.append(self.release_view(release))
            job.status = "confirmed"
            job.data = {**job.data, "release_ids": sorted(set(job.data.get("release_ids", []) + [r["id"] for r in releases]))}
            return releases

    @staticmethod
    def release_view(release):
        return {"id": release.id, "application_id": release.application_id, "commit": release.commit,
                "version": release.version, **{k: v for k, v in release.data.items() if k not in {"artifact", "error"}}}

    @staticmethod
    def job_view(job):
        return {"id": job.id, "robot_id": job.robot_id, "release_id": job.release_id,
                "status": job.status, "created": job.created,
                **{k: v for k, v in job.data.items() if k in {"action", "error", "stage", "ended"}}}

    def referenced(self, s, robot_id, release_id):
        return (any(t.data.get("release_id") == release_id for t in s.scalars(select(Task).where(Task.robot_id == robot_id)))
                or any(r.data["status"] not in TERMINAL and r.data["snapshot"].get("release_id") == release_id
                       for r in s.scalars(select(Run).where(Run.robot_id == robot_id))))

    def request_deployment(self, robot_id, release_id, action="install"):
        with self.db.transaction() as s:
            robot = self.db.lock_robot(s, robot_id)
            if not robot.credential_hash or "deploy-v1" not in robot.capabilities:
                raise Conflict("请先连接支持发布的新版执行端")
            release = s.get(ApplicationRelease, release_id)
            if not release:
                raise Conflict("发布版本不存在")
            active = s.scalar(select(DeploymentJob).where(DeploymentJob.robot_id == robot_id,
                DeploymentJob.release_id == release_id, DeploymentJob.status.in_(["queued", "installing", "uncertain"])))
            if active:
                if active.data["action"] != action:
                    raise Conflict("该版本已有未结束的部署作业")
                return self.job_view(active)
            if action == "uninstall" and self.referenced(s, robot_id, release_id):
                raise Conflict("该版本仍被计划或未结束运行引用")
            deployment = s.get(RobotDeployment, (robot_id, release_id))
            job = DeploymentJob(id=uid(), robot_id=robot_id, release_id=release_id, created=time(),
                status="queued", data={"action": action, "sent": False, "seq": 0})
            if action == "install" and deployment and deployment.status == "installed":
                job.status, job.data = "installed", {**job.data, "ended": time()}
            elif action == "uninstall" and (not deployment or deployment.status != "installed"):
                raise Conflict("机器人尚未安装该版本")
            s.add(job)
            return self.job_view(job)

    def commands(self, robot_id):
        with self.db.transaction() as s:
            maintenance = gate(s).maintenance
            robot = self.db.lock_robot(s, robot_id)
            if maintenance and not robot.deployment_job:
                return []
            if not robot.credential_hash or "deploy-v1" not in robot.capabilities or robot.active_run:
                return []
            job = s.get(DeploymentJob, robot.deployment_job) if robot.deployment_job else None
            if not job:
                if any(r.data["status"] not in TERMINAL for r in s.scalars(select(Run).where(Run.robot_id == robot_id))):
                    return []
                job = s.scalar(select(DeploymentJob).where(DeploymentJob.robot_id == robot_id, DeploymentJob.status == "queued").order_by(DeploymentJob.created).limit(1))
                if not job:
                    return []
                if job.data["action"] == "uninstall" and self.referenced(s, robot_id, job.release_id):
                    job.status, job.data = "failed", {**job.data, "error": "版本新增了计划或运行引用", "ended": time()}
                    return []
                robot.deployment_job = job.id
                job.status = "installing"
            if job.status == "uncertain" or job.data.get("sent"):
                return []
            release = s.get(ApplicationRelease, job.release_id)
            job.data = {**job.data, "sent": True}
            return [{"type": "deployment", "job_id": job.id, "action": job.data["action"],
                "release_id": release.id, "commit": release.commit, "deployment": self.release_view(release),
                "artifact_url": f"/api/robot-deployment-jobs/{job.id}/artifact"}]

    def reconcile(self, robot_id, hello):
        with self.db.transaction() as s:
            robot = self.db.lock_robot(s, robot_id)
            robot.capabilities = hello.get("capabilities", [])
            if robot.deployment_job:
                job = s.get(DeploymentJob, robot.deployment_job)
                if job and job.status == "installing":
                    job.data = {**job.data, "sent": False}
        for report in hello.get("deployment_reports", []):
            self.accept(robot_id, report)

    def accept(self, robot_id, report):
        with self.db.transaction() as s:
            robot = self.db.lock_robot(s, robot_id)
            job = s.get(DeploymentJob, report["job_id"])
            if not job or job.robot_id != robot_id:
                raise Conflict("部署作业不属于该机器人")
            seq = report.get("seq")
            if type(seq) is not int or seq < 1:
                raise Conflict("部署事件序号无效")
            if seq <= job.data.get("seq", 0):
                return job.data["seq"]
            if job.status in {"installed", "uninstalled", "failed"}:
                raise Conflict("部署作业已经结束")
            status = report.get("status")
            if status not in {"installing", "installed", "uninstalled", "failed", "uncertain"}:
                raise Conflict("部署结果无效")
            if status == "installed" and job.data["action"] != "install" or status == "uninstalled" and job.data["action"] != "uninstall":
                raise Conflict("部署结果与操作不符")
            if robot.deployment_job != job.id:
                raise Conflict("部署作业未占用此机器人")
            job.status = status
            # Executor supplies only static stage/error labels, not installer stdout.
            job.data = {**job.data, "seq": seq, "stage": str(report.get("stage", ""))[:100], "error": str(report.get("error", ""))[:500]}
            if status in {"installed", "uninstalled"}:
                release = s.get(ApplicationRelease, job.release_id)
                deployment = s.get(RobotDeployment, (robot_id, job.release_id))
                if not deployment:
                    deployment = RobotDeployment(robot_id=robot_id, release_id=job.release_id, status=status, data={})
                    s.add(deployment)
                deployment.status = status
                deployment.data = {"confirmed": time()}
                inventory = [d for d in robot.deployments if d.get("release_id") != job.release_id]
                if status == "installed":
                    inventory.append({"release_id": release.id, "app_id": release.data["app_id"], "version": release.version,
                        "input_schema": release.data["input_schema"], "schema_status": "valid", "commit": release.commit})
                robot.deployments = inventory
            if status in {"installed", "uninstalled", "failed"}:
                robot.deployment_job = None
                job.data = {**job.data, "ended": time()}
            return seq

    def artifact(self, robot_id, job_id):
        with self.db.transaction() as s:
            job = s.get(DeploymentJob, job_id)
            if not job or job.robot_id != robot_id or job.status != "installing" or job.data["action"] != "install":
                raise Conflict("没有可下载的已分配安装作业")
            release = s.get(ApplicationRelease, job.release_id)
            path = self.artifact_dir / release.data["artifact"]
            if not path.is_file():
                raise Conflict("发布制品不可用")
            return path
