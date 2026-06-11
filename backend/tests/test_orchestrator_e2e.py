"""End-to-end orchestrator test. MAKES REAL ANTHROPIC API CALLS (~$0.30-0.60).

Gated behind RUN_E2E=1 so it can never run accidentally as part of the
normal suite. Run deliberately with:

    RUN_E2E=1 .venv/Scripts/python.exe -m pytest tests/test_orchestrator_e2e.py -s

Runs all 3 demo targets through the full researcher → writer → critic
pipeline against a fresh throwaway DB (so the count assertions are exact
and the dev DB is untouched), then prints every final email for review.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import orchestrator
from db import AgentOutput, Base, Email, Run, Target

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_E2E") != "1",
    reason="paid e2e test; set RUN_E2E=1 to run deliberately",
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
SEED_PATH = BACKEND_DIR / "seed" / "demo_targets.json"


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    """Fresh dedicated DB so 'exactly N rows' assertions hold on every run."""
    db_path = tmp_path / "e2e_outreach_forge.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(orchestrator, "SessionLocal", factory)
    monkeypatch.setattr(orchestrator, "init_db", lambda: None)
    print(f"\n[e2e] test database: {db_path}")
    return factory


@pytest.mark.asyncio
async def test_full_batch_end_to_end(session_factory):
    targets = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    assert len(targets) == 3, "expected 3 demo targets in seed file"
    service = orchestrator.load_service_spec()

    run_id = await orchestrator.run_batch(targets, service, concurrency=3)

    with session_factory() as s:
        # exactly 1 run row, completed
        runs = s.scalars(select(Run)).all()
        assert len(runs) == 1
        assert runs[0].id == run_id
        assert runs[0].status == "completed", f"run failed; notes: {runs[0].notes!r}"

        # exactly 3 targets, all completed
        target_rows = s.scalars(select(Target)).all()
        assert len(target_rows) == 3
        for t in target_rows:
            assert t.status == "completed", f"target {t.name!r} is {t.status!r}"

        # exactly 9 agent_outputs: researcher + writer + critic per target
        outputs = s.scalars(select(AgentOutput)).all()
        assert len(outputs) == 9
        for t in target_rows:
            agents = sorted(o.agent for o in outputs if o.target_id == t.id)
            assert agents == ["critic", "researcher", "writer"], (
                f"target {t.name!r} has agents {agents}"
            )

        # exactly 3 emails, non-empty subject and body, draft status
        emails = s.scalars(select(Email)).all()
        assert len(emails) == 3
        names = {t.id: t.name for t in target_rows}
        for email in emails:
            assert email.subject and email.subject.strip()
            assert email.body and email.body.strip()
            assert email.send_status == "draft"

        # print every final email for human review
        for email in emails:
            print("\n" + "=" * 72)
            print(f"TARGET:  {names[email.target_id]}")
            print(f"SUBJECT: {email.subject}")
            print("-" * 72)
            print(email.body)
        print("=" * 72)

        # one full emails row, all columns, for inspection
        e = emails[0]
        print("\n[e2e] full emails row (id={}):".format(e.id))
        for col in Email.__table__.columns:
            print(f"  {col.name} = {getattr(e, col.name)!r}")
