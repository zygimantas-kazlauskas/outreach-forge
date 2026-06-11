"""Deterministic tests for the dash sanitizer and its wiring into the agents.

These make NO API calls — the agent tests mock `llm_call` to return copy
that deliberately contains em/en dashes, then assert the agent's returned
copy is clean. This is the guarantee the prompt edits alone could not give.
"""

from __future__ import annotations

import pytest

from agents import critic, writer
from agents.sanitize import EM_DASH, EN_DASH, has_banned_dashes, strip_banned_dashes


def test_em_dash_spaced_becomes_comma() -> None:
    assert strip_banned_dashes(f"emergency line {EM_DASH} but the fine print") == (
        "emergency line, but the fine print"
    )


def test_em_dash_unspaced_becomes_comma() -> None:
    assert strip_banned_dashes(f"directly{EM_DASH}without delay") == "directly, without delay"


def test_en_dash_as_punctuation_becomes_comma() -> None:
    assert strip_banned_dashes(f"answered {EN_DASH} every time") == "answered, every time"


def test_en_dash_between_digits_becomes_hyphen() -> None:
    assert strip_banned_dashes(f"open 9{EN_DASH}5 daily") == "open 9-5 daily"
    assert strip_banned_dashes(f"open 9 {EN_DASH} 5 daily") == "open 9-5 daily"


def test_clean_text_is_unchanged() -> None:
    s = "No dashes here, just commas and periods. Hyphenated-word is fine."
    assert strip_banned_dashes(s) == s


def test_has_banned_dashes() -> None:
    assert has_banned_dashes(f"a{EM_DASH}b")
    assert has_banned_dashes(f"a{EN_DASH}b")
    assert not has_banned_dashes("a-b")  # plain hyphen U+002D is allowed


@pytest.mark.asyncio
async def test_writer_strips_dashes_from_output(monkeypatch) -> None:
    async def fake_llm_call(*args, **kwargs):
        return {
            "subject": f"Your line {EM_DASH} voicemail",
            "body": f"Body text {EM_DASH} with a dash. Open 9{EN_DASH}5.",
            "chosen_hook": f"capacity gap {EM_DASH} already visible in reviews",
            "reasoning": "reason",
        }

    monkeypatch.setattr("agents.writer.llm_call", fake_llm_call)
    out = await writer.run_writer(research={}, service={}, tone="direct")

    assert not has_banned_dashes(out["subject"])
    assert not has_banned_dashes(out["body"])
    assert not has_banned_dashes(out["chosen_hook"])
    assert out["subject"] == "Your line, voicemail"
    assert out["body"] == "Body text, with a dash. Open 9-5."
    assert out["chosen_hook"] == "capacity gap, already visible in reviews"


@pytest.mark.asyncio
async def test_critic_strips_dashes_from_final(monkeypatch) -> None:
    async def fake_llm_call(*args, **kwargs):
        return {
            "critique": {
                "subject_line": {"score": "pass", "note": "ok"},
                "opener": {"score": "pass", "note": "ok"},
                "generic_phrases": [],
                "cta_strength": {"score": "pass", "note": "ok"},
                "spam_and_ai_tells": [],
            },
            "final_subject": f"Subject {EM_DASH} here",
            "final_body": f"Body {EM_DASH} text. Hours 9{EN_DASH}5.",
            "changes_made": "none",
        }

    monkeypatch.setattr("agents.critic.llm_call", fake_llm_call)
    out = await critic.run_critic(
        draft={"subject": "s", "body": "b"},
        service={},
        research={},
    )

    assert not has_banned_dashes(out["final_subject"])
    assert not has_banned_dashes(out["final_body"])
    assert out["final_subject"] == "Subject, here"
    assert out["final_body"] == "Body, text. Hours 9-5."
