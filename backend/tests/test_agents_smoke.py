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

from agents.critic import run_critic
from agents.researcher import run_researcher
from agents.sanitize import has_banned_dashes
from agents.writer import run_writer

BACKEND_DIR = Path(__file__).resolve().parent.parent
SEED_PATH = BACKEND_DIR / "seed" / "demo_targets.json"
SERVICE_PATH = BACKEND_DIR / "services" / "ai_voice_agents.json"


def _load_demo_target(target_id: str) -> dict:
    targets = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    return next(t for t in targets if t["id"] == target_id)


def _load_service() -> dict:
    return json.loads(SERVICE_PATH.read_text(encoding="utf-8"))


# Canned Researcher output for demo-001. Hand-shaped from a real Researcher
# run so downstream agent tests can run in isolation without re-calling the
# Researcher every time.
_RESEARCH_DEMO_001: dict = {
    "summary": "4-chair suburban family dental practice with 2 dentists, explicitly limited to business-hours phone coverage.",
    "signals": [
        {
            "observation": "Office hours end at 5pm and calls are not answered after that hour.",
            "evidence": "Website explicitly states office hours end at 5pm and they don't answer calls after that.",
        },
        {
            "observation": "Evening and Saturday emergency line resolves only to a next-business-day callback.",
            "evidence": "Notes: 'Lists evening and Saturday emergency line as we will call back next business day'.",
        },
        {
            "observation": "Practice is staffed by two named dentists, indicating a small clinical team.",
            "evidence": "Two named dentists on staff page.",
        },
        {
            "observation": "Practice operates 4 chairs in a suburban location with family-focused positioning.",
            "evidence": "Notes: '4-chair family dental practice in a suburban location' and 'family-focused positioning'.",
        },
    ],
    "candidate_hooks": [
        {
            "angle": "The practice has publicly acknowledged it cannot respond to after-hours or weekend calls, meaning prospective patients who call outside business hours are confirmed unrecovered leads.",
            "tied_to_signal": "Website explicitly states no call answering after 5pm and next-business-day callback for evening/Saturday emergencies.",
            "strength": "strong",
        },
        {
            "angle": "A dental emergency that gets a next-business-day callback is a high-friction moment for a family-focused brand; patients in urgency are likely to call a competitor who answers.",
            "tied_to_signal": "Family-focused positioning combined with next-business-day emergency callback policy.",
            "strength": "strong",
        },
        {
            "angle": "With only two dentists running a 4-chair practice, neither clinician can personally handle inbound call volume, making missed calls a structural problem.",
            "tied_to_signal": "Two named dentists on staff, 4-chair practice size.",
            "strength": "moderate",
        },
    ],
}


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


@pytest.mark.asyncio
async def test_writer_on_demo_001() -> None:
    service = _load_service()
    result = await run_writer(
        research=_RESEARCH_DEMO_001,
        service=service,
        tone="direct",
    )

    print("\n=== Writer output (demo-001) ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    for key in ("subject", "body", "chosen_hook", "reasoning"):
        assert key in result, f"Missing key: {key}"

    word_count = len(result["body"].split())
    assert 90 <= word_count <= 150, f"Body word count {word_count} outside 90-150"

    valid_hooks = {h["angle"] for h in _RESEARCH_DEMO_001["candidate_hooks"]}
    assert result["chosen_hook"] in valid_hooks, (
        f"chosen_hook does not match any candidate hook angle.\n"
        f"got: {result['chosen_hook']!r}\nvalid: {valid_hooks}"
    )

    assert len(result["subject"]) <= 80, "Subject line over 80 chars"
    assert not has_banned_dashes(result["subject"]), "Subject contains an em/en dash"
    assert not has_banned_dashes(result["body"]), "Body contains an em/en dash"


# Canned Writer draft for demo-001. The body deliberately contains an
# em-dash so we can confirm the Critic flags it.
_DRAFT_DEMO_001: dict = {
    "subject": "Your after-hours emergency line sends patients to voicemail",
    "body": (
        "Your website lists an evening and Saturday emergency line — but the fine "
        "print says you'll call back next business day. For a family in a dental "
        "emergency at 7pm on a Friday, that's enough reason to call the next practice "
        "on Google Maps.\n\n"
        "An AI voice receptionist would answer that call immediately, collect the "
        "patient's details, book them into your next available slot, and flag a "
        "genuine emergency to you directly without adding anything to your front "
        "desk's plate.\n\n"
        "No voicemail. No lost new patient. No gap in your schedule you didn't know "
        "you had.\n\n"
        "Worth a 15-minute call this week to see how it would fit your setup?"
    ),
    "chosen_hook": (
        "A dental emergency that gets a next-business-day callback is a high-friction "
        "moment for a family-focused brand; patients in urgency are likely to call a "
        "competitor who answers."
    ),
    "reasoning": "Hook 2 is the most visceral; opener cites the practice's own policy.",
}


@pytest.mark.asyncio
async def test_critic_on_demo_001() -> None:
    service = _load_service()
    result = await run_critic(
        draft=_DRAFT_DEMO_001,
        service=service,
        research=_RESEARCH_DEMO_001,
    )

    print("\n=== Critic output (demo-001) ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    assert "critique" in result
    assert "final_subject" in result and isinstance(result["final_subject"], str)
    assert "final_body" in result and isinstance(result["final_body"], str)
    assert "changes_made" in result

    critique = result["critique"]
    for key in ("subject_line", "opener", "generic_phrases", "cta_strength", "spam_and_ai_tells"):
        assert key in critique, f"Missing critique key: {key}"

    for dim in ("subject_line", "opener", "cta_strength"):
        assert critique[dim]["score"] in {"pass", "weak", "fail"}
        assert "note" in critique[dim]

    assert isinstance(critique["generic_phrases"], list)
    assert isinstance(critique["spam_and_ai_tells"], list)

    # Deterministic guarantee: the returned copy is dash-free regardless of
    # whether the model's own spam_and_ai_tells scan caught the input em-dash.
    assert not has_banned_dashes(result["final_subject"]), "final_subject contains an em/en dash"
    assert not has_banned_dashes(result["final_body"]), "final_body contains an em/en dash"
