"""Outreach Forge API.

POST /runs kicks off the orchestrator as a background task in this same
process; GET /runs/{id}/events streams its live progress over SSE via the
in-process event bus (late subscribers get a history replay first).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import orchestrator
from db import Email, Run, SessionLocal, Target
from events import TERMINAL_EVENT, bus

app = FastAPI(title="Outreach Forge API", version="0.4.0")

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


def _email_exists(email_id: int) -> bool:
    with SessionLocal() as session:
        return session.get(Email, email_id) is not None


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
async def send_email(email_id: int) -> None:
    """Stub until Resend integration lands in Block 6."""
    if not await asyncio.to_thread(_email_exists, email_id):
        raise HTTPException(404, f"Email {email_id} not found")
    raise HTTPException(501, "Email sending ships in Block 6 (Resend); this endpoint is a stub.")
