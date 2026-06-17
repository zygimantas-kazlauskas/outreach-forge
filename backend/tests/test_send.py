"""Send-service safety tests. NO Resend credentials and NO network: the single
network seam, send._post_resend, is mocked and asserted against, so dry_run and
every refusal are proven to never reach the wire.

Covers each safety layer (dry_run default, suppression in every mode, allowlist,
daily cap, recipient resolution, already-sent guard) plus the webhook signature
check and event processing (delivered/opened/bounced/complained).
"""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import send
from db import Base, Email, Run, Target, Unsubscribe

# Every env var that could arm or alter a live send. Cleared per test so the
# developer's real environment can never bleed into the suite.
SEND_ENV_VARS = (
    "SEND_MODE",
    "RECIPIENT_ALLOWLIST",
    "SEND_DAILY_LIMIT",
    "RESEND_API_KEY",
    "SEND_FROM",
    "RESEND_WEBHOOK_SECRET",
)

WEBHOOK_SECRET = "whsec_" + base64.b64encode(b"super-secret-signing-key").decode()


@pytest.fixture()
def send_db(tmp_path, monkeypatch):
    """Throwaway DB wired into the send service, with a clean send-env."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'send_test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(send, "SessionLocal", factory)
    monkeypatch.setattr(send, "init_db", lambda: None)
    monkeypatch.setattr(send, "SEND_LOG_PATH", tmp_path / "send_log.jsonl")
    for var in SEND_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    return factory


class FakeNetwork:
    """Stand-in for send._post_resend that records calls instead of making
    them. An empty .calls list is the proof a path never touched the wire."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.result: dict = {"id": "resend-abc123"}

    async def __call__(self, api_key: str, payload: dict) -> dict:
        self.calls.append({"api_key": api_key, "payload": payload})
        return self.result


@pytest.fixture()
def network(monkeypatch):
    fake = FakeNetwork()
    monkeypatch.setattr(send, "_post_resend", fake)
    return fake


def _seed_email(
    factory,
    *,
    body: str = "Hello there.",
    subject: str = "Subject",
    raw_notes: str | None = None,
    sent_at: datetime | None = None,
    send_status: str = "draft",
    provider_message_id: str | None = None,
    recipient_email: str | None = None,
) -> int:
    with factory() as s:
        run = Run(service_id="svc", target_count=1)
        s.add(run)
        s.flush()
        target = Target(
            run_id=run.id,
            demo_id="t-1",
            name="Acme",
            raw_notes=raw_notes if raw_notes is not None else json.dumps({"company_name": "Acme"}),
        )
        s.add(target)
        s.flush()
        email = Email(
            run_id=run.id,
            target_id=target.id,
            subject=subject,
            body=body,
            sent_at=sent_at,
            send_status=send_status,
            provider_message_id=provider_message_id,
            recipient_email=recipient_email,
        )
        s.add(email)
        s.commit()
        return email.id


def _arm_live(monkeypatch, *, allowlist: str | None = None, limit: str | None = None) -> None:
    monkeypatch.setenv("SEND_MODE", "live")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("SEND_FROM", "Me <me@mydomain.com>")
    if allowlist is not None:
        monkeypatch.setenv("RECIPIENT_ALLOWLIST", allowlist)
    if limit is not None:
        monkeypatch.setenv("SEND_DAILY_LIMIT", limit)


# --- dry_run (default mode) ---------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_is_default_and_never_touches_network(send_db, network):
    eid = _seed_email(send_db, body="Hi there.")
    result = await send.send_email(eid, "Lead@Example.com")

    assert result["mode"] == "dry_run"
    assert result["send_status"] == "dry_run"
    assert result["recipient_email"] == "lead@example.com"  # normalized
    assert result["provider_message_id"].startswith("dry-run-")
    assert network.calls == []  # the wire was never touched

    with send_db() as s:
        row = s.get(Email, eid)
        assert row.send_status == "dry_run"
        assert row.recipient_email == "lead@example.com"
        assert row.sent_at is None  # cap counts by sent_at; dry_run must not set it
        assert row.body == "Hi there."  # stored draft stays clean (no footer)


@pytest.mark.asyncio
async def test_unknown_send_mode_fails_safe_to_dry_run(send_db, network, monkeypatch):
    # Anything other than "live" (case-insensitive) is dry_run, including typos.
    monkeypatch.setenv("SEND_MODE", "sandbox")
    eid = _seed_email(send_db)
    result = await send.send_email(eid, "lead@example.com")
    assert result["mode"] == "dry_run"
    assert network.calls == []


# --- suppression (enforced in EVERY mode) -------------------------------------


@pytest.mark.asyncio
async def test_suppressed_address_refused_even_in_dry_run(send_db, network):
    send.record_unsubscribe("blocked@example.com")
    eid = _seed_email(send_db)
    with pytest.raises(send.SendRefused) as exc:
        await send.send_email(eid, "Blocked@Example.com")  # case-insensitive match
    assert exc.value.check == "suppressed"
    assert exc.value.http_status == 403
    assert network.calls == []


# --- recipient resolution -----------------------------------------------------


@pytest.mark.asyncio
async def test_send_refused_without_a_recipient(send_db, network):
    eid = _seed_email(send_db, raw_notes=json.dumps({"company_name": "Acme"}))
    with pytest.raises(send.SendRefused) as exc:
        await send.send_email(eid)  # no override, no email on the target row
    assert exc.value.check == "recipient"
    assert exc.value.http_status == 400
    assert network.calls == []


@pytest.mark.asyncio
async def test_recipient_resolved_from_target_row(send_db, network):
    eid = _seed_email(send_db, raw_notes=json.dumps({"email": "fromrow@example.com"}))
    result = await send.send_email(eid)  # no override
    assert result["recipient_email"] == "fromrow@example.com"


# --- already-sent guard -------------------------------------------------------


@pytest.mark.asyncio
async def test_already_sent_email_is_refused(send_db, network):
    eid = _seed_email(send_db, send_status="sent")
    with pytest.raises(send.SendRefused) as exc:
        await send.send_email(eid, "lead@example.com")
    assert exc.value.check == "already_sent"
    assert exc.value.http_status == 409
    assert network.calls == []


# --- live-mode safety layers --------------------------------------------------


@pytest.mark.asyncio
async def test_live_send_refused_when_recipient_not_on_allowlist(send_db, network, monkeypatch):
    _arm_live(monkeypatch, allowlist="ok@example.com")
    eid = _seed_email(send_db)
    with pytest.raises(send.SendRefused) as exc:
        await send.send_email(eid, "stranger@example.com")
    assert exc.value.check == "allowlist"
    assert exc.value.http_status == 403
    assert network.calls == []


@pytest.mark.asyncio
async def test_live_send_refused_when_daily_cap_reached(send_db, network, monkeypatch):
    _arm_live(monkeypatch, limit="1")
    # One real send already today (counted by sent_at).
    _seed_email(send_db, send_status="sent", sent_at=datetime.now(timezone.utc))
    eid = _seed_email(send_db)
    with pytest.raises(send.SendRefused) as exc:
        await send.send_email(eid, "lead@example.com")
    assert exc.value.check == "daily_cap"
    assert exc.value.http_status == 429
    assert network.calls == []


@pytest.mark.asyncio
async def test_live_send_refused_without_api_key(send_db, network, monkeypatch):
    monkeypatch.setenv("SEND_MODE", "live")  # armed, but no key/sender configured
    eid = _seed_email(send_db)
    with pytest.raises(send.SendRefused) as exc:
        await send.send_email(eid, "lead@example.com")
    assert exc.value.check == "config"
    assert exc.value.http_status == 503
    assert network.calls == []


@pytest.mark.asyncio
async def test_live_send_calls_resend_once_and_marks_sent(send_db, network, monkeypatch):
    _arm_live(monkeypatch, allowlist="ok@example.com")
    network.result = {"id": "resend-xyz789"}
    eid = _seed_email(send_db, body="Hi.")

    result = await send.send_email(eid, "ok@example.com")

    assert result["mode"] == "live"
    assert result["send_status"] == "sent"
    assert result["provider_message_id"] == "resend-xyz789"

    assert len(network.calls) == 1
    call = network.calls[0]
    assert call["api_key"] == "re_test_key"
    payload = call["payload"]
    assert payload["from"] == "Me <me@mydomain.com>"
    assert payload["to"] == ["ok@example.com"]
    assert payload["text"].startswith("Hi.")
    assert send.UNSUBSCRIBE_FOOTER in payload["text"]  # opt-out footer on the wire

    with send_db() as s:
        row = s.get(Email, eid)
        assert row.send_status == "sent"
        assert row.sent_at is not None
        assert row.provider_message_id == "resend-xyz789"
        assert row.body == "Hi."  # stored draft never carries the footer


# --- A1: atomic send-claim (no double-send under concurrency) ------------------


@pytest.mark.asyncio
async def test_send_claim_is_atomic_exactly_one_winner(send_db):
    eid = _seed_email(send_db)
    # Two claims race on the same row; the guarded UPDATE lets exactly one win.
    results = await asyncio.gather(
        asyncio.to_thread(send._claim_for_send, eid),
        asyncio.to_thread(send._claim_for_send, eid),
    )
    assert sum(bool(r) for r in results) == 1
    with send_db() as s:
        assert s.get(Email, eid).send_status == "sending"


@pytest.mark.asyncio
async def test_concurrent_live_sends_only_one_reaches_the_wire(send_db, network, monkeypatch):
    _arm_live(monkeypatch, allowlist="ok@example.com")
    eid = _seed_email(send_db, body="Hi.")

    results = await asyncio.gather(
        send.send_email(eid, "ok@example.com"),
        send.send_email(eid, "ok@example.com"),
        return_exceptions=True,
    )

    assert len(network.calls) == 1  # the race never double-sends
    sent = [r for r in results if isinstance(r, dict)]
    refused = [r for r in results if isinstance(r, send.SendRefused)]
    assert len(sent) == 1 and sent[0]["send_status"] == "sent"
    assert len(refused) == 1 and refused[0].check == "already_sent"

    with send_db() as s:
        assert s.get(Email, eid).send_status == "sent"


@pytest.mark.asyncio
async def test_provider_failure_releases_claim_for_retry(send_db, network, monkeypatch):
    _arm_live(monkeypatch, allowlist="ok@example.com")
    eid = _seed_email(send_db, body="Hi.")

    async def boom(api_key, payload):
        raise send.SendRefused("provider", "Resend returned 500", 502)

    monkeypatch.setattr(send, "_post_resend", boom)
    with pytest.raises(send.SendRefused):
        await send.send_email(eid, "ok@example.com")

    # Claim released back to draft so a legitimate retry can proceed.
    with send_db() as s:
        assert s.get(Email, eid).send_status == "draft"


# --- webhook signature verification -------------------------------------------


def test_webhook_signature_roundtrip():
    sig = send.compute_webhook_signature(WEBHOOK_SECRET, "msg_1", "1700000000", "{}")
    assert send.verify_webhook_signature(WEBHOOK_SECRET, "msg_1", "1700000000", "{}", f"v1,{sig}")
    # wrong signature, tampered body, and a missing secret all fail closed
    assert not send.verify_webhook_signature(WEBHOOK_SECRET, "msg_1", "1700000000", "{}", "v1,deadbeef")
    assert not send.verify_webhook_signature(WEBHOOK_SECRET, "msg_1", "1700000000", "tampered", f"v1,{sig}")
    assert not send.verify_webhook_signature("", "msg_1", "1700000000", "{}", f"v1,{sig}")


# --- webhook event processing -------------------------------------------------


def test_delivered_opened_bounced_update_the_row(send_db):
    eid = _seed_email(send_db, provider_message_id="pm-1")

    send.process_webhook_event({"type": "email.delivered", "data": {"email_id": "pm-1"}})
    with send_db() as s:
        assert s.get(Email, eid).send_status == "delivered"

    send.process_webhook_event(
        {"type": "email.opened", "data": {"email_id": "pm-1"}, "created_at": "2026-01-01T00:00:00Z"}
    )
    with send_db() as s:
        assert s.get(Email, eid).opened_at is not None

    send.process_webhook_event({"type": "email.bounced", "data": {"email_id": "pm-1"}})
    with send_db() as s:
        assert s.get(Email, eid).send_status == "bounced"


@pytest.mark.asyncio
async def test_complaint_webhook_suppresses_and_blocks_future_sends(send_db, network):
    eid = _seed_email(
        send_db, provider_message_id="pm-2", recipient_email="angry@example.com"
    )

    applied = send.process_webhook_event(
        {"type": "email.complained", "data": {"email_id": "pm-2", "to": ["angry@example.com"]}}
    )
    assert any("unsubscribed" in a for a in applied["applied"])

    with send_db() as s:
        assert (
            s.scalars(select(Unsubscribe).where(Unsubscribe.email == "angry@example.com")).first()
            is not None
        )

    # The complaint must make future sends to that address impossible.
    with pytest.raises(send.SendRefused) as exc:
        await send.send_email(eid, "angry@example.com")
    assert exc.value.check == "suppressed"
    assert network.calls == []


# --- B1: hard bounces suppress, soft bounces do not ---------------------------


@pytest.mark.asyncio
async def test_hard_bounce_suppresses_and_blocks_future_sends(send_db, network):
    eid = _seed_email(send_db, provider_message_id="pm-hb", recipient_email="gone@example.com")

    applied = send.process_webhook_event(
        {
            "type": "email.bounced",
            "data": {"email_id": "pm-hb", "to": ["gone@example.com"], "bounce": {"type": "Permanent"}},
        }
    )
    assert any("hard bounce" in a for a in applied["applied"])

    with send_db() as s:
        assert s.get(Email, eid).send_status == "bounced"
        row = s.scalars(select(Unsubscribe).where(Unsubscribe.email == "gone@example.com")).first()
        assert row is not None and row.source == "bounce"

    # A hard-bounced address can never be a send target again (any row, any mode).
    other = _seed_email(send_db, recipient_email=None)
    with pytest.raises(send.SendRefused) as exc:
        await send.send_email(other, "gone@example.com")
    assert exc.value.check == "suppressed"
    # And the bounced row itself is refused as already-sent (not re-sendable).
    with pytest.raises(send.SendRefused) as exc2:
        await send.send_email(eid, "someone-else@example.com")
    assert exc2.value.check == "already_sent"
    assert network.calls == []


def test_soft_bounce_marks_row_but_does_not_suppress(send_db):
    eid = _seed_email(send_db, provider_message_id="pm-sb", recipient_email="busy@example.com")

    applied = send.process_webhook_event(
        {
            "type": "email.bounced",
            "data": {"email_id": "pm-sb", "to": ["busy@example.com"], "bounce": {"type": "Transient"}},
        }
    )
    assert not any("unsubscribed" in a for a in applied["applied"])

    with send_db() as s:
        assert s.get(Email, eid).send_status == "bounced"
        assert (
            s.scalars(select(Unsubscribe).where(Unsubscribe.email == "busy@example.com")).first()
            is None  # transient bounce leaves the address sendable
        )
