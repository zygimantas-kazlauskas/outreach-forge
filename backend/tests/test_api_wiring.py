"""API wiring tests. NO API calls — agents mocked, throwaway DB, ASGI transport.

Covers the run surface (POST /runs background kickoff, SSE event stream live and
replay, run snapshot, emails listing), the real dry_run send over the API, the
startup lifespan that builds the schema, and the Block 6 webhook endpoint.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import events
import main
import orchestrator
import send
from db import Base, Email, Run, Target, Unsubscribe
from tests.test_orchestrator_wiring import TARGETS, _patch_agents

WEBHOOK_SECRET = "whsec_" + base64.b64encode(b"api-test-signing-key").decode()


def _signed_headers(body: str) -> dict[str, str]:
    ts = str(int(time.time()))  # fresh, so it passes the replay window
    sig = send.compute_webhook_signature(WEBHOOK_SECRET, "msg_api", ts, body)
    return {
        "svix-id": "msg_api",
        "svix-timestamp": ts,
        "svix-signature": f"v1,{sig}",
    }


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
    # The send service holds its own SessionLocal/init_db; point them at the
    # same throwaway DB so /emails/{id}/send sees the run's emails.
    monkeypatch.setattr(send, "SessionLocal", factory)
    monkeypatch.setattr(send, "init_db", lambda: None)
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
async def test_startup_lifespan_creates_schema_so_fresh_db_get_is_404(tmp_path, monkeypatch):
    # A brand-new DB file with NO tables created up front (unlike the api_db fixture).
    engine = create_engine(
        f"sqlite:///{tmp_path / 'fresh.db'}",
        connect_args={"check_same_thread": False},
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(main, "SessionLocal", factory)
    # The startup lifespan must build the schema; point its init_db at this engine.
    monkeypatch.setattr(main, "init_db", lambda: Base.metadata.create_all(engine))

    async with main.app.router.lifespan_context(main.app):
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/runs/1")
    # The schema exists because the lifespan ran, so a missing run is a clean 404.
    # Without the startup init_db this GET would hit a missing table and 500.
    assert resp.status_code == 404


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

    # send is real now and defaults to dry_run: no network, row marked dry_run.
    # (Deep safety-layer coverage lives in test_send.py; this just proves the
    # endpoint is wired end to end over the API.)
    sent = await client.post(
        f"/emails/{emails[0]['email_id']}/send",
        json={"recipient_email": "lead@example.com"},
    )
    assert sent.status_code == 200
    body = sent.json()
    assert body["mode"] == "dry_run"
    assert body["send_status"] == "dry_run"
    assert body["recipient_email"] == "lead@example.com"
    assert body["provider_message_id"].startswith("dry-run-")
    check_names = {c["check"] for c in body["checks"]}
    assert {"recipient", "suppressed", "mode"} <= check_names

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


# --- unsubscribes endpoint ----------------------------------------------------


@pytest.mark.asyncio
async def test_post_unsubscribes_creates_normalizes_and_is_idempotent(api_db, client):
    # First add: created, and the address is normalized (case + whitespace).
    first = await client.post("/unsubscribes", json={"email": "  Opt.Out@Example.COM "})
    assert first.status_code == 201
    assert first.json() == {"email": "opt.out@example.com", "created": True}

    # Re-adding the same address (different case) is idempotent: created=False.
    again = await client.post("/unsubscribes", json={"email": "opt.out@example.com"})
    assert again.status_code == 201
    assert again.json() == {"email": "opt.out@example.com", "created": False}

    # Exactly one row exists, stored normalized, with the default manual source.
    with api_db() as s:
        rows = s.scalars(
            select(Unsubscribe).where(Unsubscribe.email == "opt.out@example.com")
        ).all()
        assert len(rows) == 1 and rows[0].source == "manual"


# --- webhook endpoint ---------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_without_secret_configured_is_503(api_db, client, monkeypatch):
    monkeypatch.delenv("RESEND_WEBHOOK_SECRET", raising=False)
    resp = await client.post("/webhooks/resend", content="{}", headers={})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_webhook_rejects_a_bad_signature(api_db, client, monkeypatch):
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", WEBHOOK_SECRET)
    body = json.dumps({"type": "email.delivered", "data": {"email_id": "x"}})
    resp = await client.post(
        "/webhooks/resend",
        content=body,
        # Fresh timestamp (passes the replay window) so the signature is what fails.
        headers={"svix-id": "m", "svix-timestamp": str(int(time.time())), "svix-signature": "v1,wrong"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_webhook_rejects_a_stale_timestamp(api_db, client, monkeypatch):
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", WEBHOOK_SECRET)
    body = json.dumps({"type": "email.delivered", "data": {"email_id": "x"}})
    # ~67 minutes old: a correctly-signed payload that must still be rejected as
    # a replay (signature is valid; only the timestamp is stale).
    stale = str(int(time.time()) - 4000)
    sig = send.compute_webhook_signature(WEBHOOK_SECRET, "msg_api", stale, body)
    resp = await client.post(
        "/webhooks/resend",
        content=body,
        headers={"svix-id": "msg_api", "svix-timestamp": stale, "svix-signature": f"v1,{sig}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_webhook_valid_complaint_suppresses_address(api_db, client, monkeypatch):
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", WEBHOOK_SECRET)
    # Seed a run/target/email so the complaint maps to a known provider id.
    with api_db() as s:
        run = Run(service_id="svc", target_count=1)
        s.add(run)
        s.flush()
        target = Target(run_id=run.id, demo_id="t", name="Acme", raw_notes="{}")
        s.add(target)
        s.flush()
        email = Email(
            run_id=run.id,
            target_id=target.id,
            subject="s",
            body="b",
            provider_message_id="pm-web",
            recipient_email="angry@example.com",
        )
        s.add(email)
        s.commit()

    body = json.dumps(
        {"type": "email.complained", "data": {"email_id": "pm-web", "to": ["angry@example.com"]}}
    )
    resp = await client.post("/webhooks/resend", content=body, headers=_signed_headers(body))
    assert resp.status_code == 200
    assert any("unsubscribed" in a for a in resp.json()["applied"])

    with api_db() as s:
        row = s.scalars(
            select(Unsubscribe).where(Unsubscribe.email == "angry@example.com")
        ).first()
        assert row is not None and row.source == "complaint"
