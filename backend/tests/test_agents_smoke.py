"""Smoke tests for the three agents.

These hit the real Anthropic API. Run only when ANTHROPIC_API_KEY is set
and you're OK spending a small amount of credit.

Pass criteria is structural — agents return valid structured output that
matches their schema. Quality is judged by inspection of printed output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.researcher import run_researcher

BACKEND_DIR = Path(__file__).resolve().parent.parent
SEED_PATH = BACKEND_DIR / "seed" / "demo_targets.json"
SERVICE_PATH = BACKEND_DIR / "services" / "ai_voice_agents.json"


def _load_demo_target(target_id: str) -> dict:
    targets = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    return next(t for t in targets if t["id"] == target_id)


def _load_service() -> dict:
    return json.loads(SERVICE_PATH.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_researcher_on_demo_001() -> None:
    target = _load_demo_target("demo-001")
    result = await run_researcher(target)

    print("\n=== Researcher output (demo-001) ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    assert "summary" in result
    assert "signals" in result and isinstance(result["signals"], list)
    assert "candidate_hooks" in result and isinstance(result["candidate_hooks"], list)
    assert len(result["signals"]) >= 2, "Expected at least 2 signals from demo-001"
    assert len(result["candidate_hooks"]) >= 1, "Expected at least 1 candidate hook"

    for sig in result["signals"]:
        assert "observation" in sig and "evidence" in sig
    for hook in result["candidate_hooks"]:
        assert "angle" in hook and "tied_to_signal" in hook and "strength" in hook
        assert hook["strength"] in {"strong", "moderate", "weak"}
