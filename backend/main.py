"""Outreach Forge API.

POST /runs kicks off the orchestrator as a background task in this same
process; GET /runs/{id}/events streams its live progress over SSE via the
in-process event bus (late subscribers get a history replay first).
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import orchestrator
import send
from db import Run, SessionLocal, Target, init_db
from events import TERMINAL_EVENT, bus


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create the SQLite schema (and apply additive migrations) exactly once at
    # startup, so every request — including a read on a fresh DB — sees a ready
    # schema and a missing run is a clean 404, not a 500. Replaces the
    # per-request init_db() calls the entry points used to make. init_db is
    # idempotent.
    await asyncio.to_thread(init_db)
    yield


app = FastAPI(title="Outreach Forge API", version="0.6.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SERVICES_DIR = Path(__file__).resolve().parent / "services"
SSE_KEEPALIVE_SECONDS = 15

# Strong references so background run tasks aren't garbage-collected mid-run.
_run_tasks: set[asyncio.Task] = set()


class TargetIn(BaseModel):
    id: str = ""
    company_name: str = Field(min_length=1)
    url: Optional[str] = None
    contact_name: Optional[str] = None
    contact_role: Optional[str] = None
    notes: str = ""


class RunCreate(BaseModel):
    service_id: str
    targets: list[TargetIn] = Field(min_length=1)
    concurrency: int = Field(default=3, ge=1, le=10)


class SendIn(BaseModel):
    # Optional override; when omitted the recipient is resolved from the
    # target row. The send is refused if neither yields an address.
    recipient_email: Optional[str] = None


class UnsubscribeIn(BaseModel):
    email: str = Field(min_length=1)
    source: str = "manual"


def _load_service_by_id(service_id: str) -> dict[str, Any] | None:
    for path in SERVICES_DIR.glob("*.json"):
        spec = json.loads(path.read_text(encoding="utf-8"))
        if spec.get("id") == service_id:
            return spec
    return None


# --- sync DB reads, called via asyncio.to_thread -----------------------------


def _run_snapshot(run_id: int) -> dict[str, Any] | None:
    with SessionLocal() as session:
        run = session.get(Run, run_id)
        if run is None:
            return None
        statuses = [t.status for t in run.targets]
        return {
            "run_id": run.id,
            "status": run.status,
            "service_id": run.service_id,
            "created_at": run.created_at.isoformat(),
            "notes": run.notes,
            "target_count": run.target_count,
            "targets": {
                "pending": statuses.count("pending"),
                "completed": statuses.count("completed"),
                "failed": statuses.count("failed"),
            },
            "emails": len(run.emails),
        }


def _emails_for_run(run_id: int) -> list[dict[str, Any]] | None:
    with SessionLocal() as session:
        run = session.get(Run, run_id)
        if run is None:
            return None
        names = {t.id: t.name for t in run.targets}
        return [
            {
                "email_id": e.id,
                "target_id": e.target_id,
                "target_name": names.get(e.target_id),
                "subject": e.subject,
                "body": e.body,
                "chosen_hook": e.chosen_hook,
                "source": e.source,
                "send_status": e.send_status,
                "created_at": e.created_at.isoformat(),
            }
            for e in run.emails
        ]


# --- routes -------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/runs", status_code=202)
async def create_run(payload: RunCreate) -> dict[str, Any]:
    """Create a run and start it in the background. Returns immediately."""
    spec = _load_service_by_id(payload.service_id)
    if spec is None:
        raise HTTPException(404, f"Unknown service_id {payload.service_id!r}")

    targets = [t.model_dump() for t in payload.targets]
    run_id, rows = await orchestrator.create_run(targets, spec)

    task = asyncio.create_task(
        orchestrator.execute_run(run_id, rows, spec, payload.concurrency)
    )
    _run_tasks.add(task)
    task.add_done_callback(_run_tasks.discard)

    return {"run_id": run_id, "status": "running", "target_count": len(rows)}


@app.get("/runs/{run_id}")
async def get_run(run_id: int) -> dict[str, Any]:
    snapshot = await asyncio.to_thread(_run_snapshot, run_id)
    if snapshot is None:
        raise HTTPException(404, f"Run {run_id} not found")
    return snapshot


@app.get("/runs/{run_id}/events")
async def run_events(run_id: int) -> StreamingResponse:
    """SSE stream of live agent activity: history replay, then live events,
    closing after the terminal run_completed event."""
    snapshot = await asyncio.to_thread(_run_snapshot, run_id)
    if snapshot is None:
        raise HTTPException(404, f"Run {run_id} not found")

    async def stream() -> AsyncIterator[str]:
        history, queue = bus.subscribe(run_id)
        try:
            terminal_seen = False
            for event in history:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                terminal_seen = terminal_seen or event["type"] == TERMINAL_EVENT
            if terminal_seen:
                return
            if snapshot["status"] in ("completed", "failed"):
                # Run finished but the bus has no terminal event for it (e.g.
                # the process restarted since). Synthesize one so clients close.
                synthetic = {
                    "type": TERMINAL_EVENT,
                    "run_id": run_id,
                    "status": snapshot["status"],
                }
                yield f"data: {json.dumps(synthetic)}\n\n"
                return
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=SSE_KEEPALIVE_SECONDS
                    )
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event["type"] == TERMINAL_EVENT:
                    return
        finally:
            bus.unsubscribe(run_id, queue)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/runs/{run_id}/emails")
async def get_run_emails(run_id: int) -> list[dict[str, Any]]:
    emails = await asyncio.to_thread(_emails_for_run, run_id)
    if emails is None:
        raise HTTPException(404, f"Run {run_id} not found")
    return emails


@app.post("/emails/{email_id}/send")
async def send_email(email_id: int, payload: SendIn | None = None) -> dict[str, Any]:
    """Send one drafted email through every safety layer in send.py.

    Defaults to dry_run (SEND_MODE unset) — no network call, the row is marked
    send_status='dry_run' with a fake provider id. A real send needs every
    safety layer to pass simultaneously (see docs/sending-safety.md). The
    response reports the mode and each check that was applied. A refusal maps
    to the layer's HTTP status with the failing check named.
    """
    recipient_override = payload.recipient_email if payload else None
    try:
        return await send.send_email(email_id, recipient_override)
    except send.SendRefused as refusal:
        raise HTTPException(
            refusal.http_status,
            {"check": refusal.check, "reason": refusal.reason},
        )


@app.post("/unsubscribes", status_code=201)
async def add_unsubscribe(payload: UnsubscribeIn) -> dict[str, Any]:
    """Manually add an address to the suppression list. Idempotent: re-adding
    an existing address is a no-op (created=false)."""
    created = await asyncio.to_thread(
        send.record_unsubscribe, payload.email, payload.source
    )
    return {"email": send.normalize_email(payload.email), "created": created}


@app.post("/webhooks/resend")
async def resend_webhook(request: Request) -> dict[str, Any]:
    """Receive Resend delivery events. The signature is verified against
    RESEND_WEBHOOK_SECRET before anything is applied; an unverifiable request
    is rejected. A 'complained' event auto-suppresses the address; a bounce
    marks the row bounced; delivered/opened update the row's status/opened_at.
    """
    body = (await request.body()).decode("utf-8")
    secret = os.environ.get("RESEND_WEBHOOK_SECRET", "").strip()
    if not secret:
        # Fail closed: without a secret we cannot trust any payload.
        raise HTTPException(503, "RESEND_WEBHOOK_SECRET is not configured; cannot verify webhooks")
    verified = send.verify_webhook_signature(
        secret,
        request.headers.get("svix-id", ""),
        request.headers.get("svix-timestamp", ""),
        body,
        request.headers.get("svix-signature", ""),
    )
    if not verified:
        raise HTTPException(400, "Invalid webhook signature")
    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "Webhook body is not valid JSON")
    return await asyncio.to_thread(send.process_webhook_event, event)
