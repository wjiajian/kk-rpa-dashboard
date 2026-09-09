from contextlib import contextmanager
from time import time
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Integer, UniqueConstraint, Float, ForeignKey, String, create_engine, select, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class ServiceState(Base):
    __tablename__ = "service_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    maintenance: Mapped[bool] = mapped_column(Boolean, default=False)


@event.listens_for(ServiceState.__table__, "after_create")
def seed_service_state(table, connection, **kwargs):
    connection.execute(table.insert().values(id=1, maintenance=False))


class Robot(Base):
    __tablename__ = "robots"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    credential_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    active_run: Mapped[str | None] = mapped_column(String, nullable=True)
    deployments: Mapped[list] = mapped_column(JSON, default=list)
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    deployment_job: Mapped[str | None] = mapped_column(String, nullable=True)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    robot_id: Mapped[str] = mapped_column(ForeignKey("robots.id"), index=True)
    created: Mapped[float] = mapped_column(Float, default=time)
    data: Mapped[dict] = mapped_column(JSON)


class Operation(Base):
    __tablename__ = "operations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    data: Mapped[dict] = mapped_column(JSON)


class RunCredential(Base):
    __tablename__ = "run_credentials"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    encrypted: Mapped[str] = mapped_column(String)


class Event(Base):
    __tablename__ = "events"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    expires: Mapped[float] = mapped_column(Float)
    data: Mapped[dict] = mapped_column(JSON)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    mime: Mapped[str] = mapped_column(String)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    robot_id: Mapped[str] = mapped_column(ForeignKey("robots.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    next_run_at: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    data: Mapped[dict] = mapped_column(JSON)


class TaskCredential(Base):
    __tablename__ = "task_credentials"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    encrypted: Mapped[str] = mapped_column(String)


class RunTrigger(Base):
    __tablename__ = "run_triggers"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), unique=True)
    intent: Mapped[dict] = mapped_column(JSON)


class ApplicationSource(Base):
    __tablename__ = "application_sources"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)
    encrypted_credentials: Mapped[str | None] = mapped_column(String, nullable=True)


class ImportJob(Base):
    __tablename__ = "import_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("application_sources.id"))
    created: Mapped[float] = mapped_column(Float, default=time)
    status: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON)


class PublishedApplication(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("source_id", "app_id", name="uq_source_app"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("application_sources.id"))
    app_id: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)


class ApplicationRelease(Base):
    __tablename__ = "application_releases"
    __table_args__ = (UniqueConstraint("application_id", "commit", name="uq_app_commit"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"))
    commit: Mapped[str] = mapped_column(String)
    version: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON)


class RobotDeployment(Base):
    __tablename__ = "robot_deployments"
    robot_id: Mapped[str] = mapped_column(ForeignKey("robots.id"), primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("application_releases.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class DeploymentJob(Base):
    __tablename__ = "deployment_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    robot_id: Mapped[str] = mapped_column(ForeignKey("robots.id"), index=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("application_releases.id"))
    created: Mapped[float] = mapped_column(Float, default=time)
    status: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON)


class Database:
    def __init__(self, url):
        self.engine = create_engine(url, pool_pre_ping=True)
        if self.engine.dialect.name == "sqlite":
            @event.listens_for(self.engine, "connect")
            def enable_foreign_keys(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")

    @contextmanager
    def transaction(self):
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            yield session

    def lock_robot(self, session, robot_id):
        robot = session.scalar(select(Robot).where(Robot.id == robot_id).with_for_update())
        if robot is None:
            raise ValueError("机器人不存在")
        return robot
