"""Resend send service with a layered safety model.

Client choice: we call the Resend REST API directly over httpx instead of
the `resend` pip package. The send is a single POST to /emails; httpx is
already in the venv (test transport), and the SDK configures a module-global
api key, which fights both our read-config-at-call-time safety model and
test isolation. One fewer dependency, trivially mockable (_post_resend).

SAFETY MODEL — every layer must hold for a real email to leave the machine:
1. SEND_MODE env var. Unset, "dry_run", or ANY value other than the exact
   string "live" means no network call ever: the would-be send is logged and
   the row is marked send_status='dry_run' with a fake provider id. Unknown
   values fail safe to dry_run.
2. Sends happen only through this module via an explicit per-email API call.
   The orchestrator never imports it — generation and sending stay decoupled.
3. RECIPIENT_ALLOWLIST env var (comma-separated). When set, live sends to
   addresses not on it are refused. Keep it pinned to your own addresses
   while testing.
4. SEND_DAILY_LIMIT env var (default 20). Refuse once today's (UTC) count of
   REAL sends reaches the cap, counted from the DB (sent_at), not memory.
   The check and the send are not atomic, so two perfectly simultaneous
   requests could overshoot by one — acceptable: the cap enforces warmup
   discipline, it is not a security boundary.

Every attempt — refused, dry_run, or sent — is appended to
backend/logs/send_log.jsonl (gitignored) as an audit trail.

DB access follows the db.py concurrency contract: sync helpers, one
short-lived Session each, always called via asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from dotenv import load_dotenv
from sqlalchemy import select

from db import Email, SessionLocal, Target, Unsubscribe, init_db

load_dotenv(Path(__file__).resolve().parent / ".env")

logger = logging.getLogger("outreach_forge.send")

RESEND_ENDPOINT = "https://api.resend.com/emails"
SEND_LOG_PATH = Path(__file__).resolve().parent / "logs" / "send_log.jsonl"
DEFAULT_DAILY_LIMIT = 20

# Appended to every OUTBOUND body (the stored draft stays clean). Plain text,
# reply-to-opt-out: a real one-click unsubscribe link needs the deployed URL
# from Block 7 (https://<app>/unsubscribe?...); until then replies are
# recorded manually via POST /unsubscribes.
UNSUBSCRIBE_FOOTER = (
    "\n\n--\n"
    'Don\'t want emails like this? Reply "unsubscribe" and I\'ll remove you '
    "immediately."
)


class SendRefused(Exception):
    """A safety layer refused the send. `check` names the layer;
    `http_status` maps the refusal at the API edge."""

    def __init__(self, check: str, reason: str, http_status: int) -> None:
        super().__init__(reason)
        self.check = check
        self.reason = reason
        self.http_status = http_status


# --- config, read at call time so env changes (and tests) apply immediately ---


def send_mode() -> str:
    """Only the exact value "live" arms real sends; everything else,
    including typos, is dry_run."""
    mode = os.environ.get("SEND_MODE", "").strip().lower()
    return "live" if mode == "live" else "dry_run"


def recipient_allowlist() -> set[str]:
    raw = os.environ.get("RECIPIENT_ALLOWLIST", "")
    return {normalize_email(a) for a in raw.split(",") if a.strip()}


def daily_limit() -> int:
    raw = os.environ.get("SEND_DAILY_LIMIT", "").strip()
    try:
        return int(raw) if raw else DEFAULT_DAILY_LIMIT
    except ValueError:
        # A typo'd limit still caps at the default rather than disabling it.
        logger.warning("SEND_DAILY_LIMIT=%r is not an integer; using %d", raw, DEFAULT_DAILY_LIMIT)
        return DEFAULT_DAILY_LIMIT


def normalize_email(address: str) -> str:
    return address.strip().lower()


# --- suppression list ----------------------------------------------------------


def _is_suppressed(session, address: str) -> bool:
    return (
        session.scalars(select(Unsubscribe).where(Unsubscribe.email == normalize_email(address))).first()
        is not None
    )


def _add_unsubscribe(session, address: str, source: str) -> bool:
    """Idempotent insert into the suppression list. Returns True if a new
    row was created. Caller commits."""
    address = normalize_email(address)
    if not address:
        return False
    if session.scalars(select(Unsubscribe).where(Unsubscribe.email == address)).first() is not None:
        return False
    session.add(Unsubscribe(email=address, source=source))
    return True


def record_unsubscribe(address: str, source: str = "manual") -> bool:
    """Sync entry point for the API; call via asyncio.to_thread."""
    init_db()
    with SessionLocal() as session:
        created = _add_unsubscribe(session, address, source)
        session.commit()
    return created


# --- sync DB helpers, called via asyncio.to_thread ----------------------------


def _real_sends_today(session) -> int:
    """Count of real sends in the current UTC calendar day. Webhooks may
    later flip send_status to delivered/bounced, so count by sent_at, which
    only real sends populate. Date comparison happens in Python: SQLite
    date() over the stored ISO strings is fragile with tz offsets, and the
    row count here is tiny."""
    today = datetime.now(timezone.utc).date()
    sent_ats = session.scalars(select(Email.sent_at).where(Email.sent_at.is_not(None))).all()
    return sum(1 for ts in sent_ats if ts.date() == today)


def _resolve_recipient(session, email: Email, override: Optional[str]) -> str:
    candidate = (override or "").strip()
    if not candidate:
        # The target row's raw_notes holds the original intake dict as JSON;
        # an "email" key there is the other allowed recipient source.
        target = session.get(Target, email.target_id)
        if target is not None:
            try:
                candidate = str(json.loads(target.raw_notes).get("email") or "").strip()
            except (json.JSONDecodeError, TypeError):
                candidate = ""
    if not candidate:
        raise SendRefused(
            "recipient",
            "No recipient_email: none in the request body and the target row has none",
            400,
        )
    candidate = normalize_email(candidate)
    # Deliberately minimal shape check — Resend validates for real; this only
    # catches obvious mistakes without pulling in an email-validator dep.
    if "@" not in candidate or "." not in candidate.rsplit("@", 1)[-1]:
        raise SendRefused("recipient", f"{candidate!r} does not look like an email address", 400)
    return candidate


def _prepare(email_id: int, recipient_override: Optional[str]) -> dict[str, Any]:
    """Run every safety check and return the send plan. Raises SendRefused
    the moment any layer fails; nothing is written here."""
    checks: list[dict[str, str]] = []
    mode = send_mode()
    with SessionLocal() as session:
        email = session.get(Email, email_id)
        if email is None:
            raise SendRefused("exists", f"Email {email_id} not found", 404)
        if email.send_status in ("sent", "delivered"):
            raise SendRefused(
                "already_sent",
                f"Email {email_id} was already sent (status {email.send_status!r}); refusing a duplicate send",
                409,
            )
        checks.append({"check": "already_sent", "result": "passed"})

        recipient = _resolve_recipient(session, email, recipient_override)
        checks.append({"check": "recipient", "result": recipient})

        # Suppression is enforced in EVERY mode, dry_run included — an
        # unsubscribed address must never be a send target, even hypothetically.
        if _is_suppressed(session, recipient):
            raise SendRefused(
                "suppressed",
                f"{recipient!r} is on the unsubscribe list; refusing the send in every mode",
                403,
            )
        checks.append({"check": "suppressed", "result": "passed (not on the unsubscribe list)"})

        plan: dict[str, Any] = {
            "mode": mode,
            "recipient": recipient,
            "subject": email.subject,
            # The stored draft stays clean; the opt-out footer is added only to
            # the body that actually goes out (and to the dry_run audit record).
            "outbound_body": email.body + UNSUBSCRIBE_FOOTER,
            "checks": checks,
        }

        if mode != "live":
            checks.append({"check": "mode", "result": "dry_run — no network call is made in this mode"})
            checks.append({"check": "allowlist", "result": "skipped (dry_run)"})
            checks.append({"check": "daily_cap", "result": "skipped (dry_run)"})
            return plan

        checks.append({"check": "mode", "result": "live — real send permitted if every check passes"})

        allowlist = recipient_allowlist()
        if allowlist:
            if recipient not in allowlist:
                raise SendRefused(
                    "allowlist",
                    f"Live send to {recipient!r} refused: address is not on RECIPIENT_ALLOWLIST",
                    403,
                )
            checks.append({"check": "allowlist", "result": f"passed ({len(allowlist)} allowed address(es))"})
        else:
            checks.append({"check": "allowlist", "result": "RECIPIENT_ALLOWLIST not set — all recipients allowed"})

        limit = daily_limit()
        sent_today = _real_sends_today(session)
        if sent_today >= limit:
            raise SendRefused(
                "daily_cap",
                f"Daily send cap reached ({sent_today}/{limit} real sends today, UTC). "
                "Raise SEND_DAILY_LIMIT deliberately if this is intended.",
                429,
            )
        checks.append({"check": "daily_cap", "result": f"passed ({sent_today}/{limit} today)"})

        api_key = os.environ.get("RESEND_API_KEY", "").strip()
        if not api_key:
            raise SendRefused("config", "SEND_MODE=live but RESEND_API_KEY is not set", 503)
        sender = os.environ.get("SEND_FROM", "").strip()
        if not sender:
            raise SendRefused(
                "config",
                'SEND_MODE=live but SEND_FROM is not set (verified sender, e.g. "Name <you@yourdomain.com>")',
                503,
            )
        plan["api_key"] = api_key
        plan["sender"] = sender
        return plan


def _mark_send_result(
    email_id: int,
    status: str,
    provider_id: str,
    recipient: str,
    sent_at: Optional[datetime],
) -> None:
    with SessionLocal() as session:
        email = session.get(Email, email_id)
        email.send_status = status
        email.provider_message_id = provider_id
        email.recipient_email = recipient
        if sent_at is not None:
            email.sent_at = sent_at
        session.commit()


def _audit(record: dict[str, Any]) -> None:
    record = {"ts": datetime.now(timezone.utc).isoformat(), **record}
    SEND_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SEND_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# --- network ------------------------------------------------------------------


async def _post_resend(api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    """The ONLY network call in this module. Tests monkeypatch it to assert
    dry_run and refusals never reach the wire."""
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            RESEND_ENDPOINT,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
    if response.status_code >= 400:
        raise SendRefused("provider", f"Resend returned {response.status_code}: {response.text[:300]}", 502)
    return response.json()


# --- entry point ----------------------------------------------------------------


async def send_email(email_id: int, recipient_override: Optional[str] = None) -> dict[str, Any]:
    """Send (or dry-run) one drafted email through every safety layer.

    Returns a result dict reporting the mode and each check applied.
    Raises SendRefused when any layer fails; the refusal is audited too.
    """
    await asyncio.to_thread(init_db)
    try:
        plan = await asyncio.to_thread(_prepare, email_id, recipient_override)
    except SendRefused as refusal:
        _audit({"event": "refused", "email_id": email_id, "check": refusal.check, "reason": refusal.reason})
        raise

    if plan["mode"] != "live":
        provider_id = f"dry-run-{uuid.uuid4().hex[:12]}"
        await asyncio.to_thread(
            _mark_send_result, email_id, "dry_run", provider_id, plan["recipient"], None
        )
        logger.info("DRY RUN send of email %s to %s (no network call)", email_id, plan["recipient"])
        _audit(
            {
                "event": "dry_run",
                "email_id": email_id,
                "recipient": plan["recipient"],
                "subject": plan["subject"],
                "body": plan["outbound_body"],
                "provider_message_id": provider_id,
            }
        )
        return {
            "email_id": email_id,
            "mode": "dry_run",
            "send_status": "dry_run",
            "recipient_email": plan["recipient"],
            "provider_message_id": provider_id,
            "checks": plan["checks"],
        }

    payload = {
        "from": plan["sender"],
        "to": [plan["recipient"]],
        "subject": plan["subject"],
        "text": plan["outbound_body"],
    }
    try:
        data = await _post_resend(plan["api_key"], payload)
    except SendRefused as refusal:
        _audit({"event": "provider_error", "email_id": email_id, "reason": refusal.reason})
        raise
    provider_id = str(data.get("id", ""))
    await asyncio.to_thread(
        _mark_send_result, email_id, "sent", provider_id, plan["recipient"], datetime.now(timezone.utc)
    )
    logger.info("LIVE send of email %s to %s (provider id %s)", email_id, plan["recipient"], provider_id)
    _audit(
        {
            "event": "sent",
            "email_id": email_id,
            "recipient": plan["recipient"],
            "subject": plan["subject"],
            "provider_message_id": provider_id,
        }
    )
    return {
        "email_id": email_id,
        "mode": "live",
        "send_status": "sent",
        "recipient_email": plan["recipient"],
        "provider_message_id": provider_id,
        "checks": plan["checks"],
    }
