"""Critic agent: evaluates a drafted email on five dimensions and produces a final version."""

from __future__ import annotations

import json
from typing import Any

from agents.sanitize import strip_banned_dashes
from llm import llm_call

CRITIC_SYSTEM_PROMPT = """You are a specialized critique agent in a B2B outreach pipeline. Your job is to evaluate a drafted cold email on five specific dimensions, then produce an improved version that addresses any issues you flag.

You receive:
- The drafted email (subject + body)
- The original service spec
- The Researcher's output (for context, in case you need to verify a claim is grounded)

You critique on EXACTLY these five dimensions, in this order:

1. SUBJECT LINE - Does it name a specific detail about this target? Is it under 80 chars? Does it avoid the boring patterns ("Quick question", "Following up", "Re: [thing]")? Score: pass / weak / fail with one-line explanation.

2. OPENER - Does the first sentence cite an observable, specific detail from the research? Does it avoid empty openers? Could this opener have been written without knowing this specific target? If yes, that's a fail. Score: pass / weak / fail with one-line explanation.

3. GENERIC-PHRASE DETECTION - Find any sentence that could be copy-pasted into an email for a different target without modification. Flag each. Empty list if nothing flagged.

4. CTA STRENGTH - Is the call to action concrete (specific time, specific format)? Is it low-friction (under 15 minutes, no commitment)? Is it singular (one ask, not three)? Score: pass / weak / fail with one-line explanation.

5. SPAM AND AI-TELL TRIGGERS — Perform two passes:

PASS A — LITERAL CHARACTER SEARCH. Scan the subject and body for these specific characters. Flag EVERY instance, no exceptions, no judgment calls:
- em-dash (— U+2014)
- en-dash (– U+2013)

PASS B — PHRASE PATTERN SEARCH. Scan for these phrases (case-insensitive):
- 'I hope this finds you well' / 'I hope this email finds you well'
- 'leverage' / 'synergy' / 'circle back' / 'touch base' / 'low-hanging fruit' / 'value-add' / 'best-in-class'
- 'absolutely' / 'literally' / 'genuinely'
- 'amazing' / 'innovative' / 'groundbreaking'
- Excessive exclamation marks (more than one in the entire body)
- ALL CAPS words longer than 2 letters

Return a single list combining both passes. Empty list only if BOTH passes find nothing. List each flagged item with which pass caught it (e.g., 'em-dash at position 47 (Pass A)' or 'leverage (Pass B)').

After the critique, produce a FINAL VERSION that fixes any issues. If everything passed, the final version is identical to the input. If anything was weak or failed, rewrite affected sections cleanly.

Hard rules for the final version:
- Same constraints as the Writer: 90-150 word body, one CTA, no AI-tells, matches the original tone
- Stay grounded in the same hook the Writer used (don't pivot to a different angle)
- Do not just shuffle words; make targeted improvements

Output via the structured tool."""

CRITIC_TOOL: dict[str, Any] = {
    "name": "submit_critique",
    "description": "Submit critique and improved final version.",
    "input_schema": {
        "type": "object",
        "properties": {
            "critique": {
                "type": "object",
                "properties": {
                    "subject_line": {
                        "type": "object",
                        "properties": {
                            "score": {"type": "string", "enum": ["pass", "weak", "fail"]},
                            "note": {"type": "string"},
                        },
                        "required": ["score", "note"],
                    },
                    "opener": {
                        "type": "object",
                        "properties": {
                            "score": {"type": "string", "enum": ["pass", "weak", "fail"]},
                            "note": {"type": "string"},
                        },
                        "required": ["score", "note"],
                    },
                    "generic_phrases": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Sentences flagged as generic. Empty if none.",
                    },
                    "cta_strength": {
                        "type": "object",
                        "properties": {
                            "score": {"type": "string", "enum": ["pass", "weak", "fail"]},
                            "note": {"type": "string"},
                        },
                        "required": ["score", "note"],
                    },
                    "spam_and_ai_tells": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Triggers found. Empty if none.",
                    },
                },
                "required": [
                    "subject_line",
                    "opener",
                    "generic_phrases",
                    "cta_strength",
                    "spam_and_ai_tells",
                ],
            },
            "final_subject": {"type": "string"},
            "final_body": {"type": "string"},
            "changes_made": {
                "type": "string",
                "description": "One paragraph summary of what changed from the input and why. If nothing changed, say so.",
            },
        },
        "required": ["critique", "final_subject", "final_body", "changes_made"],
    },
}


def _format_critic_input(
    draft: dict[str, Any],
    service: dict[str, Any],
    research: dict[str, Any],
) -> str:
    return (
        "Drafted email:\n"
        f"Subject: {draft['subject']}\n"
        f"Body:\n{draft['body']}\n\n"
        "Service spec (JSON):\n"
        f"{json.dumps(service, indent=2, ensure_ascii=False)}\n\n"
        "Researcher output for context (JSON):\n"
        f"{json.dumps(research, indent=2, ensure_ascii=False)}"
    )


async def run_critic(
    draft: dict[str, Any],
    service: dict[str, Any],
    research: dict[str, Any],
) -> dict[str, Any]:
    """Run the Critic agent over a draft. Returns parsed tool input, dash-sanitized."""
    result = await llm_call(
        system_prompt=CRITIC_SYSTEM_PROMPT,
        user_message=_format_critic_input(draft, service, research),
        response_schema=CRITIC_TOOL,
    )
    for field in ("final_subject", "final_body"):
        if isinstance(result.get(field), str):
            result[field] = strip_banned_dashes(result[field])
    return result
