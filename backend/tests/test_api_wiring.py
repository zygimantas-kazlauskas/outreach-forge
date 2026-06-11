"""API wiring tests. NO API calls — agents mocked, throwaway DB, ASGI transport.

Covers the full Block 4 surface: POST /runs background kickoff, SSE event
stream (live and replay), run snapshot, emails listing, and the send stub.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import events
import main
import orchestrator
from db import Base
from tests.test_orchestrator_wiring import TARGETS, _patch_agents


@pytest.fixture()
def api_db(tmp_path, monkeypatch):
    """Fresh throwaway DB shared by the orchestrator and the API layer."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'api_test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(orchestrator, "SessionLocal", factory)
    monkeypatch.setattr(orchestrator, "init_db", lambda: None)
    monkeypatch.setattr(main, "SessionLocal", factory)
    events.bus.reset()
    return factory


@pytest_asyncio.fixture()
async def client():
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _run_payload(**overrides) -> dict:
    payload = {"service_id": "ai-voice-agents", "targets": TARGETS, "concurrency": 2}
    payload.update(overrides)
    return payload


async def _collect_events(client: httpx.AsyncClient, run_id: int) -> list[dict]:
    collected: list[dict] = []
    async with client.stream("GET", f"/runs/{run_id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[len("data: "):])
            collected.append(event)
            if event["type"] == "run_completed":
                break
    return collected


@pytest.mark.asyncio
async def test_post_runs_unknown_service_is_404(api_db, client):
    response = await client.post("/runs", json=_run_payload(service_id="nope"))
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_post_runs_empty_targets_is_422(api_db, client):
    response = await client.post("/runs", json=_run_payload(targets=[]))
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_missing_run_is_404(api_db, client):
    for path in ("/runs/999", "/runs/999/events", "/runs/999/emails"):
        response = await client.get(path)
        assert response.status_code == 404, path


@pytest.mark.asyncio
async def test_full_run_flow_with_live_events(api_db, client, monkeypatch):
    _patch_agents(monkeypatch)

    response = await client.post("/runs", json=_run_payload())
    assert response.status_code == 202
    body = response.json()
    run_id = body["run_id"]
    assert body["status"] == "running"
    assert body["target_count"] == 2

    # stream events while the background task works
    collected = await _collect_events(client, run_id)
    types = [e["type"] for e in collected]
    assert types[0] == "run_started"
    assert types[-1] == "run_completed"
    assert collected[-1]["status"] == "completed"
    assert types.count("target_completed") == 2
    assert types.count("agent_finished") == 6

    # snapshot reflects the finished run
    snapshot = (await client.get(f"/runs/{run_id}")).json()
    assert snapshot["status"] == "completed"
    assert snapshot["targets"] == {"pending": 0, "completed": 2, "failed": 0}
    assert snapshot["emails"] == 2

    # emails endpoint returns the final drafts
    emails = (await client.get(f"/runs/{run_id}/emails")).json()
    assert len(emails) == 2
    for email in emails:
        assert email["subject"] == "Final subject"
        assert email["body"] == "Final body"
        assert email["send_status"] == "draft"
        assert email["target_name"] in {"Alpha Dental", "Beta Salon"}

    # send stays a stub until Block 6
    send = await client.post(f"/emails/{emails[0]['email_id']}/send")
    assert send.status_code == 501
    missing_send = await client.post("/emails/999/send")
    assert missing_send.status_code == 404


@pytest.mark.asyncio
async def test_late_subscriber_gets_history_replay(api_db, client, monkeypatch):
    _patch_agents(monkeypatch)

    run_id = (await client.post("/runs", json=_run_payload())).json()["run_id"]

    # let the background run finish before connecting
    for _ in range(200):
        snapshot = (await client.get(f"/runs/{run_id}")).json()
        if snapshot["status"] != "running":
            break
        await asyncio.sleep(0.01)
    assert snapshot["status"] == "completed"

    collected = await _collect_events(client, run_id)
    types = [e["type"] for e in collected]
    assert types[0] == "run_started"
    assert types[-1] == "run_completed"
    assert types.count("target_completed") == 2


@pytest.mark.asyncio
async def test_failed_target_reported_in_events_and_snapshot(api_db, client, monkeypatch):
    _patch_agents(monkeypatch, writer_fails_for="Beta Salon")

    run_id = (await client.post("/runs", json=_run_payload())).json()["run_id"]
    collected = await _collect_events(client, run_id)

    failures = [e for e in collected if e["type"] == "target_failed"]
    assert len(failures) == 1
    assert failures[0]["target_name"] == "Beta Salon"
    assert "writer exploded" in failures[0]["error"]
    assert collected[-1]["status"] == "completed"  # partial success

    snapshot = (await client.get(f"/runs/{run_id}")).json()
    assert snapshot["targets"] == {"pending": 0, "completed": 1, "failed": 1}
    assert snapshot["emails"] == 1
