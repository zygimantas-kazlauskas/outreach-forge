"""Researcher agent: extracts concrete signals and candidate hooks for a target."""

from __future__ import annotations

from typing import Any

from llm import llm_call

RESEARCHER_SYSTEM_PROMPT = """You are a specialized research agent in a B2B outreach pipeline. Your job is to extract concrete, observable signals about a target company that downstream agents will use to write a personalized cold email.

YOU DO NOT WRITE EMAILS. You do not propose what to pitch. You only observe and structure.

Input you will receive:
- Target company name
- Target company URL (if available)
- Contact person name and role (if available)
- Notes the human provided about this target

Your job, in this order:
1. Read the input carefully.
2. Identify CONCRETE, OBSERVABLE signals about the company. Concrete means: anchored in evidence from the input, not invented. Observable means: a person looking at the same input would see the same thing.
3. From those signals, identify 2-3 CANDIDATE HOOKS. A hook is a specific angle that ties a signal to a possible pain point or opportunity.
4. Output structured JSON via the provided tool.

What counts as a signal:
- Stated business size cues ("4-chair practice", "family-owned", "2 vets")
- Explicit operational details ("hours end at 5pm", "appointment-only", "walk-ins welcome")
- Geographic or market positioning ("suburban", "downtown", "rural")
- Self-positioning language they use ("family-focused", "premium", "budget-friendly")
- Specific services they list
- Anything in the notes the human provided

What does NOT count as a signal:
- Generic industry observations ("dentists need patients")
- Assumptions you invent ("they probably struggle with X")
- Vague flattery ("they seem professional")
- Anything you cannot point to in the input

What counts as a hook:
- A specific signal tied to a specific potential pain or opportunity
- Example: signal = "site explicitly says we don't answer phones after 5pm" -> hook = "after-hours call coverage is a pain they're already aware of and have publicly acknowledged"
- Example: signal = "4-chair family practice in suburban location" -> hook = "small operations team means every missed call has visible impact on monthly revenue"

What does NOT count as a hook:
- "They might want more customers" (every business wants this)
- "They could improve efficiency" (vague)
- "They probably struggle with [generic problem]" (assumed, not evidenced)

CRITICAL: It is better to return 2 strong hooks than 3 with one weak one. If the input is thin, return fewer hooks and a shorter summary. Do not pad.

If the input is too thin to produce any reasonable signal or hook, return an empty signals list and empty candidate_hooks list, and set summary to "Insufficient input to extract signals."

Output via the structured tool. Do not output prose."""

RESEARCHER_TOOL: dict[str, Any] = {
    "name": "submit_research",
    "description": "Submit structured research findings for the target company.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "One-sentence factual summary of the company based on input. Max 150 chars.",
            },
            "signals": {
                "type": "array",
                "description": "List of concrete observable signals about the company.",
                "items": {
                    "type": "object",
                    "properties": {
                        "observation": {
                            "type": "string",
                            "description": "What you observed, as a fact.",
                        },
                        "evidence": {
                            "type": "string",
                            "description": "Where in the input this comes from.",
                        },
                    },
                    "required": ["observation", "evidence"],
                },
            },
            "candidate_hooks": {
                "type": "array",
                "description": "2-3 specific hooks tying signals to potential pains/opportunities. Empty array if signals are too thin.",
                "items": {
                    "type": "object",
                    "properties": {
                        "angle": {
                            "type": "string",
                            "description": "The hook angle, one sentence.",
                        },
                        "tied_to_signal": {
                            "type": "string",
                            "description": "Which signal this hook is grounded in.",
                        },
                        "strength": {
                            "type": "string",
                            "enum": ["strong", "moderate", "weak"],
                            "description": "Self-assessed strength of this hook.",
                        },
                    },
                    "required": ["angle", "tied_to_signal", "strength"],
                },
            },
        },
        "required": ["summary", "signals", "candidate_hooks"],
    },
}


def _format_target(target: dict[str, Any]) -> str:
    return (
        f"Target company name: {target.get('company_name', 'unknown')}\n"
        f"Target company URL: {target.get('url', 'not provided')}\n"
        f"Contact person name: {target.get('contact_name', 'not provided')}\n"
        f"Contact role: {target.get('contact_role', 'not provided')}\n"
        f"Notes from human:\n{target.get('notes', 'no additional notes')}"
    )


async def run_researcher(target: dict[str, Any]) -> dict[str, Any]:
    """Run the Researcher agent over one target. Returns parsed tool input."""
    return await llm_call(
        system_prompt=RESEARCHER_SYSTEM_PROMPT,
        user_message=_format_target(target),
        response_schema=RESEARCHER_TOOL,
    )
