from contextlib import contextmanager
from time import time
from uuid import uuid4

from sqlalchemy import JSON, Float, ForeignKey, String, create_engine, select, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Robot(Base):
    __tablename__ = "robots"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    credential_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    active_run: Mapped[str | None] = mapped_column(String, nullable=True)
    deployments: Mapped[list] = mapped_column(JSON, default=list)


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
