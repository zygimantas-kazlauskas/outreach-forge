# Outreach Forge — architecture

This document is the design contract for the project. Components below are documented in full even when they are not yet implemented; the implementation block for each is noted in parentheses.

## Three-agent design

Each outreach target is processed by three agents in sequence: Researcher → Writer → Critic. Every agent calls the LLM through the same `llm_call` wrapper (see below) and returns a structured JSON object validated against a Pydantic schema.

### Researcher (Block 2 — implemented)

- **Input:** target company name, URL, contact name and role, free-text user notes.
- **Output:**
  ```json
  {
    "summary": "short paragraph framing the company",
    "signals": ["concrete observation 1", "concrete observation 2", "..."],
    "candidate_hooks": [
      { "hook": "...", "tied_to_signal": "..." },
      "... 2-3 total"
    ]
  }
  ```
- **System-prompt focus:** gather and structure. Explicitly forbidden from writing email copy or sales language. Signals must be concrete observations, not generic claims.

### Writer (Block 2 — implemented)

- **Input:** Researcher output + service spec + tone preference (`formal` | `casual` | `direct`).
- **Output:**
  ```json
  {
    "subject": "...",
    "body": "90-150 words, grounded in chosen_hook",
    "chosen_hook": "exact hook string from candidate_hooks",
    "reasoning": "why this hook over the others"
  }
  ```
- **System-prompt focus:** pick exactly one hook, write a complete email body, stay 90-150 words. Must reference the chosen signal concretely.

### Critic (Block 2 — implemented)

- **Input:** Writer output + service spec.
- **Output:**
  ```json
  {
    "critique": {
      "subject": "...",
      "opener": "...",
      "generic_phrases": ["list of phrases that read as templated"],
      "cta": "...",
      "spam_triggers": ["list of words/phrases likely to hurt deliverability"]
    },
    "final_subject": "...",
    "final_body": "improved version, still 90-150 words"
  }
  ```
- **System-prompt focus:** targeted critique on the five named dimensions, then produce an improved version. Not a free-form rewrite.

## Orchestrator (Block 3)

A plain async Python function that, given a target, calls Researcher → Writer → Critic and persists each agent's output as it returns. No LangGraph, no CrewAI, no agent framework.

**Why hand-rolled:** the flow is a fixed linear pipeline of three steps. A framework would add an external dependency, a DSL to learn, and abstractions over what is genuinely a 30-line `async def`. The cost (vendor lock-in, debuggability, mental overhead) exceeds the benefit at this scale. If the topology becomes a dynamic graph later, this decision will be revisited — explicitly, in build-log.md, not silently.

Concurrency across targets uses `asyncio.gather` with a small semaphore to cap concurrent LLM calls.

## LLM provider abstraction (Block 2 — implemented)

All agent code calls a single wrapper:

```python
async def llm_call(
    system_prompt: str,
    user_message: str,
    response_schema: dict,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 2000,
) -> dict: ...
```

This wrapper owns: the Anthropic SDK call (using forced `tool_choice` for structured output), one retry on a missing `tool_use` block, and append-only JSONL logging at `backend/logs/llm_calls.jsonl` (timestamp, model, prompt hash, message preview, response size, latency, status). Token counts will be added to the log alongside agent_outputs persistence in Block 3.

**Why an abstraction:** centralizes logging in one place, makes provider substitution mechanical, keeps agent files focused on prompts and schemas.

## Persistence (Block 3)

SQLite via SQLAlchemy. Schema sketch:

- **runs** — `id`, `service_id`, `tone`, `created_at`, `status`.
- **targets** — `id`, `run_id`, `company`, `url`, `contact_name`, `contact_role`, `notes`.
- **agent_outputs** — `id`, `target_id`, `agent` (`researcher` | `writer` | `critic`), `input_json`, `output_json`, `latency_ms`, `tokens_in`, `tokens_out`, `created_at`.
- **emails** — `id`, `target_id`, `subject`, `body`, `status` (`draft` | `sent` | `failed`), `resend_id`, `sent_at`.

SQLite is sufficient for the single-user, single-machine demo profile. If multi-user/multi-instance ever matters, swap to Postgres — the SQLAlchemy layer makes that a connection-string change plus a migration.

## Frontend pattern (Block 4/5)

- Target intake form on `/`.
- Run view on `/runs/[id]` with a live activity feed driven by a server-sent-events stream from the backend. Each agent output appended as it arrives.
- Results table with subject, final body, per-agent timing, and a "view trace" drawer that shows the full Researcher/Writer/Critic chain for the row.

SSE rather than websockets because the traffic is one-way (server → client) and SSE works through corporate proxies without extra configuration.

## Worked example service

The repo ships one fully-developed service config:

- **Service:** AI voice agents for small service businesses.
- **Buyer profile:** owner-operators of small service businesses — dental practices, salons, home-services contractors, small clinics. Typically too small for a dedicated receptionist, losing calls after hours and during peak appointments.
- **Value prop:** AI-powered receptionist that answers calls 24/7, books appointments into the existing scheduling tool, and escalates real emergencies to a human on-call line.

The service config lives at `backend/services/ai_voice_agents.json` (Block 2). Demo targets — currently 3 fictional small service businesses, scaling to ~8 in a later block — live at `backend/seed/demo_targets.json` (Block 2).

The engine itself is service-agnostic; the example exists to make the demo concrete instead of abstract.
