"""Prompt-tuning batch runner. MAKES REAL API CALLS (~$0.50 per run).

Runs the full pipeline on the 3 demo targets against a throwaway DB (the
dev DB is untouched) and writes every agent output plus the final emails
to docs/tuning/<label>.md for side-by-side comparison across prompt
iterations.

Usage:
    LLM_LOG_FULL=1 .venv/Scripts/python.exe tuning_runner.py <label>
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import orchestrator
from db import AgentOutput, Base, Email, Run, Target

BACKEND_DIR = Path(__file__).resolve().parent
SEED_PATH = BACKEND_DIR / "seed" / "demo_targets.json"
TUNING_DIR = BACKEND_DIR.parent / "docs" / "tuning"


def _word_count(text: str) -> int:
    return len(text.split())


def _fence(obj) -> str:
    return "```json\n" + json.dumps(obj, indent=2, ensure_ascii=False) + "\n```"


async def main(label: str) -> None:
    db_path = BACKEND_DIR / "logs" / f"tuning_{label}.db"
    db_path.unlink(missing_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    orchestrator.SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    orchestrator.init_db = lambda: None

    targets = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    service = orchestrator.load_service_spec()

    run_id = await orchestrator.run_batch(targets, service, concurrency=3)

    lines = [f"# Tuning run: {label}", ""]
    with orchestrator.SessionLocal() as s:
        run = s.get(Run, run_id)
        lines.append(f"Run status: **{run.status}**  |  notes: {run.notes!r}")
        for t in s.scalars(select(Target).order_by(Target.id)).all():
            lines += ["", "---", "", f"## {t.name} ({t.demo_id}) — {t.status}"]
            outputs = {
                o.agent: o
                for o in s.scalars(
                    select(AgentOutput).where(AgentOutput.target_id == t.id)
                ).all()
            }
            for agent in ("researcher", "writer", "critic"):
                o = outputs.get(agent)
                if o is None:
                    lines += ["", f"### {agent}: MISSING"]
                    continue
                parsed = json.loads(o.output_json)
                lines += ["", f"### {agent} ({o.latency_ms} ms)", _fence(parsed)]
                if agent == "writer":
                    lines.append(f"Draft body word count: {_word_count(parsed['body'])}")
                if agent == "critic":
                    lines.append(
                        f"Final body word count: {_word_count(parsed['final_body'])}"
                    )
            email = s.scalars(select(Email).where(Email.target_id == t.id)).first()
            if email:
                lines += [
                    "",
                    "### final email",
                    f"**Subject:** {email.subject}",
                    "",
                    email.body,
                    "",
                    f"_chosen_hook:_ {email.chosen_hook}",
                ]

    TUNING_DIR.mkdir(parents=True, exist_ok=True)
    out_path = TUNING_DIR / f"{label}.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "untitled"))
