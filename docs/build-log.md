# Build log

One entry per evening session. Dates are real — no backdating, no future-dating.

## Block 1 — scaffold (2026-05-27)

Project initialized. Created the monorepo layout (`frontend/`, `backend/`, `docs/`), `.gitignore`, MIT license, and the design-contract documents.

- **Frontend:** scaffolded with `create-next-app@14` (App Router, TypeScript strict, Tailwind v3, no `src/`, no ESLint scaffold). Replaced the default template page with a minimal placeholder showing the project name and a one-line description. Updated `<head>` metadata. `next build` passes; `npm run dev` serves on `http://localhost:3000`.
- **Backend:** created a Python 3.12 venv at `backend/.venv`. `requirements.txt` pins `fastapi`, `uvicorn[standard]`, `pydantic` only — SQLAlchemy, Anthropic SDK, and Resend are intentionally deferred to the blocks that actually use them. `main.py` exposes a single `GET /health` returning `{"status": "ok"}`. Verified locally with `uvicorn main:app` + `curl`.
- **Docs:** wrote `architecture.md` covering the three-agent design (Researcher / Writer / Critic), the orchestrator's hand-rolled async stance, the `llm_call` LLM-provider abstraction, the SQLite schema sketch, the SSE frontend pattern, and the worked-example service. Wrote this build log.
- **Not done:** no agent code, no LLM wrapper, no database, no API endpoints beyond `/health`, no UI beyond the placeholder. All of that is later blocks.

One commit closes the block: `Block 1: scaffold (Next.js frontend + FastAPI backend running locally)`.

## Block 2 — LLM wrapper + three agents (2026-05-28)

Built the LLM provider abstraction and all three agents. Three sub-commits land the work in progression:

- **2a — LLM wrapper + Researcher.** `backend/llm.py` is the single `async llm_call(system_prompt, user_message, response_schema, ...)` entry point. Uses Anthropic's tool-use with a forced `tool_choice` to enforce structured output (more reliable than prompting for JSON; the SDK validates input against the schema before returning the `tool_use` block). One retry on a missing tool_use block; all calls logged to `backend/logs/llm_calls.jsonl` (gitignored). Default model is `claude-sonnet-4-6`. Researcher agent shipped with its full system prompt and `submit_research` tool. Added the AI-voice-agents service spec and three demo targets (Westshore Dental, Sunset Cuts, Allister Plumbing).
- **2b — Writer.** `backend/agents/writer.py` with the full system prompt and `submit_draft` tool. Picks exactly one hook, drafts a 90-150 word body with a specific subject. Tone options: formal, casual, direct.
- **2c — Critic.** `backend/agents/critic.py` with the full system prompt and `submit_critique` tool. Scores five dimensions (subject_line, opener, generic_phrases, cta_strength, spam_and_ai_tells) and produces a fixed final version.

Each agent has a smoke test in `backend/tests/test_agents_smoke.py`. Tests hit the real Anthropic API and pass on structural validity (schema fields present, word counts in range, hooks matching). Quality of the prose is judged by inspection — and the inspection turned up two real things worth recording: the Writer occasionally emits em-dashes despite the explicit ban, and the Critic missed an em-dash on its first run against a draft that contained one. Both are prompt-tuning candidates, not code bugs. Left as-is for now.

Bumped the Anthropic SDK pin from 0.39.0 to 0.104.1 because 0.39 is incompatible with httpx 0.28 (the `proxies` kwarg was removed upstream). Added `pytest`, `pytest-asyncio`, and `python-dotenv` to requirements.

Not done in this block: orchestrator, persistence, FastAPI agent routes, SSE, frontend, Resend.

Closing commits: `2a`, `2b`, `2c`, plus a docs commit for this entry + README "What's next" update.
