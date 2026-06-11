"""Wiring tests for the orchestrator. NO API calls.

The three agent functions are monkeypatched with fakes and SessionLocal is
pointed at a throwaway SQLite file, so these tests prove persistence,
sequencing, and per-target error isolation deterministically and for free.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import events
import orchestrator
from db import AgentOutput, Base, Email, Run, Target

FAKE_RESEARCH = {"summary": "s", "signals": [], "candidate_hooks": []}
# chosen_hook deliberately contains an em-dash: the agents are mocked here,
# so the clean value asserted below proves the ORCHESTRATOR's persistence
# guard, independent of the writer's own sanitization.
FAKE_DRAFT = {
    "subject": "Fake subject",
    "body": "Fake body",
    "chosen_hook": "fake — hook",
    "reasoning": "r",
}
FAKE_CRITIQUE = {
    "critique": {
        "subject_line": {"score": "pass", "note": "ok"},
        "opener": {"score": "pass", "note": "ok"},
        "generic_phrases": [],
        "cta_strength": {"score": "pass", "note": "ok"},
        "spam_and_ai_tells": [],
    },
    "final_subject": "Final subject",
    "final_body": "Final body",
    "changes_made": "none",
}

TARGETS = [
    {"id": "t-001", "company_name": "Alpha Dental", "url": "a.example.com", "notes": "n1"},
    {"id": "t-002", "company_name": "Beta Salon", "url": "b.example.com", "notes": "n2"},
]


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    """Point the orchestrator at a fresh throwaway DB for each test."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'wiring_test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(orchestrator, "SessionLocal", factory)
    monkeypatch.setattr(orchestrator, "init_db", lambda: None)
    # Throwaway DBs restart run ids at 1, so clear the global bus between
    # tests to keep event histories from colliding.
    events.bus.reset()
    return factory


def _patch_agents(monkeypatch, *, writer_fails_for: str | None = None):
    async def fake_researcher(target):
        return dict(FAKE_RESEARCH, summary=f"research for {target['company_name']}")

    async def fake_writer(research, service, tone="direct"):
        if writer_fails_for and writer_fails_for in research["summary"]:
            raise RuntimeError("writer exploded")
        return dict(FAKE_DRAFT)

    async def fake_critic(draft, service, research):
        return dict(FAKE_CRITIQUE)

    monkeypatch.setattr(orchestrator, "run_researcher", fake_researcher)
    monkeypatch.setattr(orchestrator, "run_writer", fake_writer)
    monkeypatch.setattr(orchestrator, "run_critic", fake_critic)


@pytest.mark.asyncio
async def test_happy_path_persists_everything(session_factory, monkeypatch):
    _patch_agents(monkeypatch)
    service = orchestrator.load_service_spec()

    run_id = await orchestrator.run_batch(TARGETS, service, concurrency=2)

    with session_factory() as s:
        run = s.get(Run, run_id)
        assert run.status == "completed"
        assert run.service_id == service["id"]
        assert run.target_count == 2

        targets = s.scalars(select(Target).where(Target.run_id == run_id)).all()
        assert len(targets) == 2
        assert all(t.status == "completed" for t in targets)
        # raw_notes round-trips the full input dict
        assert json.loads(targets[0].raw_notes)["company_name"] == "Alpha Dental"

        outputs = s.scalars(select(AgentOutput).where(AgentOutput.run_id == run_id)).all()
        assert len(outputs) == 6  # 3 agents x 2 targets
        per_target = {t.id: [o.agent for o in outputs if o.target_id == t.id] for t in targets}
        for agents in per_target.values():
            assert agents == ["researcher", "writer", "critic"]  # sequential order
        assert all(json.loads(o.output_json) for o in outputs)
        assert all(o.model for o in outputs)
        assert all(o.latency_ms is not None and o.latency_ms >= 0 for o in outputs)

        emails = s.scalars(select(Email).where(Email.run_id == run_id)).all()
        assert len(emails) == 2
        for email in emails:
            assert email.subject == "Final subject"
            assert email.body == "Final body"
            assert email.chosen_hook == "fake, hook"  # em-dash stripped at persistence
            assert email.source == "critic"
            assert email.send_status == "draft"


@pytest.mark.asyncio
async def test_one_target_failing_does_not_kill_batch(session_factory, monkeypatch):
    _patch_agents(monkeypatch, writer_fails_for="Beta Salon")
    service = orchestrator.load_service_spec()

    run_id = await orchestrator.run_batch(TARGETS, service, concurrency=2)

    with session_factory() as s:
        run = s.get(Run, run_id)
        assert run.status == "completed"  # partial success still completes
        assert "writer exploded" in (run.notes or "")  # error is inspectable

        by_name = {
            t.name: t
            for t in s.scalars(select(Target).where(Target.run_id == run_id)).all()
        }
        assert by_name["Alpha Dental"].status == "completed"
        assert by_name["Beta Salon"].status == "failed"

        # failed target got its researcher output persisted, then stopped
        failed_outputs = s.scalars(
            select(AgentOutput).where(AgentOutput.target_id == by_name["Beta Salon"].id)
        ).all()
        assert [o.agent for o in failed_outputs] == ["researcher"]

        emails = s.scalars(select(Email).where(Email.run_id == run_id)).all()
        assert len(emails) == 1
        assert emails[0].target_id == by_name["Alpha Dental"].id


@pytest.mark.asyncio
async def test_event_stream_records_full_sequence(session_factory, monkeypatch):
    _patch_agents(monkeypatch)
    service = orchestrator.load_service_spec()

    run_id = await orchestrator.run_batch(TARGETS, service, concurrency=2)

    history, queue = events.bus.subscribe(run_id)
    events.bus.unsubscribe(run_id, queue)
    types = [e["type"] for e in history]

    assert types[0] == "run_started"
    assert history[0]["target_count"] == 2
    assert types[-1] == "run_completed"
    assert history[-1]["status"] == "completed"
    assert types.count("target_completed") == 2
    assert all("ts" in e and e["run_id"] == run_id for e in history)

    # per target: agents start and finish in pipeline order
    target_ids = {e["target_id"] for e in history if "target_id" in e}
    assert len(target_ids) == 2
    for tid in target_ids:
        agent_seq = [
            (e["type"], e["agent"])
            for e in history
            if e.get("target_id") == tid and "agent" in e
        ]
        assert agent_seq == [
            ("agent_started", "researcher"),
            ("agent_finished", "researcher"),
            ("agent_started", "writer"),
            ("agent_finished", "writer"),
            ("agent_started", "critic"),
            ("agent_finished", "critic"),
        ]


@pytest.mark.asyncio
async def test_event_stream_reports_target_failure(session_factory, monkeypatch):
    _patch_agents(monkeypatch, writer_fails_for="Beta Salon")
    service = orchestrator.load_service_spec()

    run_id = await orchestrator.run_batch(TARGETS, service, concurrency=2)

    history, queue = events.bus.subscribe(run_id)
    events.bus.unsubscribe(run_id, queue)

    failures = [e for e in history if e["type"] == "target_failed"]
    assert len(failures) == 1
    assert failures[0]["target_name"] == "Beta Salon"
    assert "writer exploded" in failures[0]["error"]
    assert history[-1] == {
        **history[-1],
        "type": "run_completed",
        "status": "completed",
    }


@pytest.mark.asyncio
async def test_all_targets_failing_marks_run_failed(session_factory, monkeypatch):
    _patch_agents(monkeypatch, writer_fails_for="research for")  # matches every target
    service = orchestrator.load_service_spec()

    run_id = await orchestrator.run_batch(TARGETS, service, concurrency=2)

    with session_factory() as s:
        run = s.get(Run, run_id)
        assert run.status == "failed"
        targets = s.scalars(select(Target).where(Target.run_id == run_id)).all()
        assert all(t.status == "failed" for t in targets)
        assert s.scalars(select(Email).where(Email.run_id == run_id)).all() == []
