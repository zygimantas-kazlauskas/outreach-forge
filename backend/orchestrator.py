"""Async orchestrator: researcher → writer → critic per target, persisted to SQLite.

Concurrency model: pipelines run concurrently ACROSS targets under an
asyncio.Semaphore; WITHIN a target the three agents run sequentially, each
feeding the next. The DB engine is sync, so every persistence point runs in
asyncio.to_thread with its own short-lived Session (see the concurrency
contract in db.py).

Error isolation: a failing target is marked 'failed' and the error is
appended to the run's notes for inspection; the per-target pipeline never
raises, so one bad target cannot kill the batch.

targets.raw_notes stores the full input dict serialized as JSON. That is
exactly what the Researcher receives; the pipeline deserializes it back
into the dict shape run_researcher expects.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Awaitable

from agents.critic import run_critic
from agents.researcher import run_researcher
from agents.writer import run_writer
from db import AgentOutput, Email, Run, SessionLocal, Target, init_db
from llm import DEFAULT_MODEL

SERVICE_SPEC_PATH = Path(__file__).resolve().parent / "services" / "ai_voice_agents.json"

logger = logging.getLogger(__name__)


def load_service_spec(path: Path | None = None) -> dict[str, Any]:
    """Read a service spec JSON file (defaults to the AI voice agents spec)."""
    return json.loads((path or SERVICE_SPEC_PATH).read_text(encoding="utf-8"))


# --- sync DB helpers, always called via asyncio.to_thread -------------------


def _create_run_and_targets(
    targets: list[dict[str, Any]], service_spec: dict[str, Any]
) -> tuple[int, list[tuple[int, str]]]:
    with SessionLocal() as session:
        run = Run(
            status="running",
            service_id=service_spec["id"],
            target_count=len(targets),
        )
        session.add(run)
        session.flush()
        rows: list[tuple[int, str]] = []
        for t in targets:
            row = Target(
                run_id=run.id,
                demo_id=t.get("id", ""),
                name=t.get("company_name", "unknown"),
                url=t.get("url"),
                raw_notes=json.dumps(t, ensure_ascii=False),
                status="pending",
            )
            session.add(row)
            session.flush()
            rows.append((row.id, row.raw_notes))
        session.commit()
        return run.id, rows


def _save_agent_output(
    run_id: int,
    target_id: int,
    agent: str,
    output: dict[str, Any],
    latency_ms: int | None,
) -> None:
    with SessionLocal() as session:
        session.add(
            AgentOutput(
                run_id=run_id,
                target_id=target_id,
                agent=agent,
                output_json=json.dumps(output, ensure_ascii=False),
                model=DEFAULT_MODEL,
                latency_ms=latency_ms,
            )
        )
        session.commit()


def _save_email_and_complete(
    run_id: int, target_id: int, critique: dict[str, Any], draft: dict[str, Any]
) -> None:
    with SessionLocal() as session:
        session.add(
            Email(
                run_id=run_id,
                target_id=target_id,
                subject=critique["final_subject"],
                body=critique["final_body"],
                chosen_hook=draft.get("chosen_hook"),
                source="critic",
                send_status="draft",
            )
        )
        target = session.get(Target, target_id)
        if target is not None:
            target.status = "completed"
        session.commit()


def _record_target_failure(run_id: int, target_id: int, error: str) -> None:
    with SessionLocal() as session:
        target = session.get(Target, target_id)
        if target is not None:
            target.status = "failed"
        run = session.get(Run, run_id)
        if run is not None:
            line = f"target {target_id} failed: {error}"
            run.notes = line if not run.notes else f"{run.notes}\n{line}"
        session.commit()


def _finalize_run(run_id: int) -> str:
    with SessionLocal() as session:
        run = session.get(Run, run_id)
        statuses = [t.status for t in run.targets]
        all_failed = bool(statuses) and all(s == "failed" for s in statuses)
        run.status = "failed" if all_failed else "completed"
        session.commit()
        return run.status


# --- async pipeline ----------------------------------------------------------


async def _timed(coro: Awaitable[dict[str, Any]]) -> tuple[dict[str, Any], int]:
    start = time.perf_counter()
    result = await coro
    return result, int((time.perf_counter() - start) * 1000)


async def run_pipeline_for_target(
    run_id: int,
    target_row_id: int,
    raw_notes: str,
    service_spec: dict[str, Any],
) -> None:
    """Run one target through researcher → writer → critic and persist each step.

    Never raises: any failure marks the target 'failed' and records the error
    on the run's notes.
    """
    try:
        try:
            target_input = json.loads(raw_notes)
            if not isinstance(target_input, dict):
                raise ValueError("raw_notes JSON is not an object")
        except (json.JSONDecodeError, ValueError):
            # Plain-text notes (e.g. rows created outside run_batch).
            target_input = {"notes": raw_notes}

        research, latency_ms = await _timed(run_researcher(target_input))
        await asyncio.to_thread(
            _save_agent_output, run_id, target_row_id, "researcher", research, latency_ms
        )

        tone = service_spec.get("tone_default", "direct")
        draft, latency_ms = await _timed(run_writer(research, service_spec, tone))
        await asyncio.to_thread(
            _save_agent_output, run_id, target_row_id, "writer", draft, latency_ms
        )

        critique, latency_ms = await _timed(run_critic(draft, service_spec, research))
        await asyncio.to_thread(
            _save_agent_output, run_id, target_row_id, "critic", critique, latency_ms
        )

        await asyncio.to_thread(
            _save_email_and_complete, run_id, target_row_id, critique, draft
        )
    except Exception as e:
        logger.exception("Pipeline failed for target row %s", target_row_id)
        error = f"{type(e).__name__}: {e}"
        try:
            await asyncio.to_thread(_record_target_failure, run_id, target_row_id, error)
        except Exception:
            logger.exception("Could not record failure for target row %s", target_row_id)


async def run_batch(
    targets: list[dict[str, Any]],
    service_spec: dict[str, Any],
    concurrency: int = 3,
) -> int:
    """Run every target through the pipeline concurrently. Returns the run id.

    Run status ends 'completed' unless EVERY target failed (partial success
    still counts as 'completed'; per-target statuses carry the detail).
    """
    await asyncio.to_thread(init_db)
    run_id, rows = await asyncio.to_thread(_create_run_and_targets, targets, service_spec)

    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded(target_row_id: int, raw_notes: str) -> None:
        async with semaphore:
            await run_pipeline_for_target(run_id, target_row_id, raw_notes, service_spec)

    await asyncio.gather(*(_bounded(row_id, notes) for row_id, notes in rows))
    await asyncio.to_thread(_finalize_run, run_id)
    return run_id
