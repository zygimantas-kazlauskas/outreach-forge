"""SQLAlchemy 2.0 (sync) models and SQLite session setup for Outreach Forge.

We use the SYNC engine on purpose: at this scale async SQLite buys only
locking complexity. The async we care about lives in the LLM calls; the
orchestrator runs per-target pipelines concurrently and wraps each DB write
in asyncio.to_thread with a fresh Session, so the engine is configured with
check_same_thread=False.

The .db file lives at backend/outreach_forge.db and is gitignored. Run this
module directly (python db.py) to create the file and all tables.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import ForeignKey, Integer, Text, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

DB_PATH = Path(__file__).parent / "outreach_forge.db"
ENGINE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(ENGINE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _enable_sqlite_fk(dbapi_connection, connection_record) -> None:
    # SQLite ignores ON DELETE CASCADE unless foreign keys are enabled per
    # connection. The ORM-level cascades handle session deletes regardless,
    # but this keeps DB-level integrity honest too.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    status: Mapped[str] = mapped_column(default="pending")  # pending/running/completed/failed
    service_id: Mapped[str]
    target_count: Mapped[int]
    notes: Mapped[Optional[str]]

    targets: Mapped[list["Target"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    agent_outputs: Mapped[list["AgentOutput"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    emails: Mapped[list["Email"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class Target(Base):
    __tablename__ = "targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    demo_id: Mapped[str]
    name: Mapped[str]
    url: Mapped[Optional[str]]
    raw_notes: Mapped[str] = mapped_column(Text)  # input text the researcher receives
    status: Mapped[str] = mapped_column(default="pending")  # pending/completed/failed

    run: Mapped["Run"] = relationship(back_populates="targets")
    agent_outputs: Mapped[list["AgentOutput"]] = relationship(
        back_populates="target", cascade="all, delete-orphan"
    )
    emails: Mapped[list["Email"]] = relationship(
        back_populates="target", cascade="all, delete-orphan"
    )


class AgentOutput(Base):
    __tablename__ = "agent_outputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    target_id: Mapped[int] = mapped_column(ForeignKey("targets.id", ondelete="CASCADE"))
    agent: Mapped[str]  # researcher/writer/critic
    output_json: Mapped[str] = mapped_column(Text)  # full structured dict as JSON
    model: Mapped[str]
    latency_ms: Mapped[Optional[int]]
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    run: Mapped["Run"] = relationship(back_populates="agent_outputs")
    target: Mapped["Target"] = relationship(back_populates="agent_outputs")


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    target_id: Mapped[int] = mapped_column(ForeignKey("targets.id", ondelete="CASCADE"))
    subject: Mapped[str]
    body: Mapped[str] = mapped_column(Text)
    chosen_hook: Mapped[Optional[str]]
    source: Mapped[str] = mapped_column(default="critic")
    send_status: Mapped[str] = mapped_column(default="draft")
    # Headroom for later Resend tracking, intentionally nullable now.
    provider_message_id: Mapped[Optional[str]]
    opened_at: Mapped[Optional[datetime]]
    replied_at: Mapped[Optional[datetime]]
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    run: Mapped["Run"] = relationship(back_populates="emails")
    target: Mapped["Target"] = relationship(back_populates="emails")


def init_db() -> None:
    """Create the SQLite file and all tables if they do not already exist."""
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    init_db()
    print(f"Initialized database and tables at {DB_PATH}")
