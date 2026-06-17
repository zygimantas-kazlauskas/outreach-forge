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

### 2d — prompt tuning + deterministic dash guard (2026-05-29)

Followed up on the two em-dash issues flagged above. First tried prompt-only fixes: strengthened the Writer's ban into a dedicated top-of-list rule plus a final self-check, and rewrote the Critic's dimension 5 into an explicit two-pass (literal character search, then phrase search). Re-ran the Critic against the canned draft that contains a real U+2014. It still missed it — the model narrated a "scan" but checked the wrong sentence and even reintroduced an em-dash in its rewrite, calling it "a stylistic choice." Confirmed programmatically that the draft does contain one em-dash at index 58.

Conclusion: a prompt cannot reliably make the model do a literal character search; that distinction (U+2014 vs U+002D) gets blurred at the token level. Added a deterministic guard (`backend/agents/sanitize.py`) that the Writer and Critic apply to their output copy fields before returning — em/en dashes become commas (or hyphens inside numeric ranges). The prompt edits stay as the belt; the sanitizer is the suspenders. Proven by 8 API-free tests, including wiring tests that mock `llm_call` to return dash-laden copy and assert the agent's returned copy is clean.

## Block 3 — async orchestrator + SQLite persistence (2026-06-10 → 2026-06-11)

Two evenings. Block 3 complete — full pipeline operational (orchestrator + SQLite persistence + e2e tested).

- **3a.** Cleaned up the Critic's `spam_and_ai_tells` prompt: the field now returns only concrete tells quoting the offending text (empty array if none), no scan narration — the deterministic sanitizer already owns the dash guarantee, so the prompt no longer asks the model to narrate a character search. Added full request/response logging to `llm.py` gated behind `LLM_LOG_FULL=1` (default behavior unchanged).
- **3b (+fix).** `backend/db.py`: sync SQLAlchemy 2.0 typed models — `runs`, `targets`, `agent_outputs`, `emails` — with run-level cascade delete and nullable email-tracking columns as headroom for later Resend integration. Sync on purpose: async SQLite buys locking complexity, not throughput, at this scale. The fix commit made the DB path absolute (CWD-independent) and documented the concurrency contract: one short-lived session per persistence point, every DB call from async code wrapped in `asyncio.to_thread`.
- **3c.** `backend/orchestrator.py`: `run_batch` creates the run + target rows, then runs per-target pipelines concurrently under `asyncio.Semaphore(3)`; each target runs Researcher → Writer → Critic sequentially, persisting an `agent_outputs` row after each step and the final draft email after the Critic. One target failing is marked `failed` with the error recorded on the run's notes and never kills the batch; the run only ends `failed` if every target failed. Proven by 3 API-free wiring tests with mocked agents on a throwaway DB.
- **3d.** End-to-end test (`RUN_E2E=1` gated): all 3 demo targets through the real API at concurrency 3. One run `completed`, 9 agent outputs, 3 draft emails — each opening with a target-specific observation and a single CTA. ~38s wall clock for the batch.
- **Close-out.** Extended the dash guard to `chosen_hook` (in the Writer and at the orchestrator's persistence path — no dash reaches the `emails` table in any column), gated the Block 2 smoke tests behind `RUN_SMOKE=1` after a bare `pytest tests/` accidentally spent ~$0.15 hitting the API, and updated docs. A flagless `pytest tests/` now runs 11 free tests and skips all 4 paid ones in ~1.3s.

Not done in this block: FastAPI agent routes, SSE, frontend, Resend.

## Prompt tuning + Block 4 — API + SSE (2026-06-11, second sitting)

Same evening as the Block 3 close-out, after publishing the repo to GitHub.

**Prompt-tuning pass ($2.00 of a $3.00 budget, 4 runs, log in docs/tuning/log.md).**
Baseline run surfaced three high-leverage weaknesses; one measured iteration
each, all kept on first try: (1) writer template convergence broken at the
product-pivot paragraph and CTA while explicitly preserving the working
opener formula (their own words → consequence); (2) critic banned from
introducing ungrounded factual claims in rewrites — observed firing on a
real case ("Setup takes a few days," cut with the rule quoted back);
(3) critic's spam/AI-tell scan scoped to the drafted subject and body so
research context can't bleed into findings. Stopped on plateau.

**Block 4.** In-process event bus (`backend/events.py`) with per-run history
replay; orchestrator split into `create_run` / `execute_run` (with
`run_batch` kept as the composition) and instrumented to publish per-target
agent start/finish, target completed/failed, and run lifecycle events.
FastAPI surface: `POST /runs` (202, background task, returns run_id
immediately), `GET /runs/{id}` (status + counts), `GET /runs/{id}/events`
(SSE: replay, then live, closes on run_completed, keepalives), `GET
/runs/{id}/emails`, and `POST /emails/{id}/send` returning 501 until Resend
in Block 6. All proven free: 11 wiring tests (5 orchestrator/events + 6 API
over httpx ASGI transport) with mocked agents on throwaway DBs.

Not done in this block: frontend, Resend, deploy.

## Block 5 — frontend (see docs/frontend-testing.md)

The Next.js UI (target intake, live run view with the SSE board, results grid)
was built across its own evening sessions; its testing notes live in
[frontend-testing.md](frontend-testing.md) rather than being duplicated here.

## Block 6 — Resend sending behind a layered safety model (2026-06-12 → 2026-06-17)

Spanned two sittings — 6a landed on the 12th, then a session hit its usage
limit mid-block and the rest (6b–6d) was finished on the 17th, picking up from
the committed state and the uncommitted 6b work in the tree. The design center
of the whole block was the inverse of "make sending work": **make an accidental
real send impossible.** Generating and sending are fully decoupled (the
orchestrator never imports `send.py`), and a real send is gated behind several
independent layers that must all pass at once. Everything is testable without
Resend credentials — the one network seam, `send._post_resend`, is mocked, so
dry-run and every refusal are *proven* to never reach the wire.

- **6a.** `backend/send.py` over the Resend REST API via httpx (not the `resend`
  pip package — it sets a module-global key that fights both the
  read-config-at-call-time safety model and test isolation; the comment in the
  file justifies the choice). Layers: `SEND_MODE` (dry_run default and on any
  value other than exactly `live`, so typos fail safe; dry_run logs the
  would-be send and marks the row `dry_run` with a fake provider id),
  `RECIPIENT_ALLOWLIST`, and a DB-counted `SEND_DAILY_LIMIT` (default 20,
  counted by `sent_at` so a dry_run never consumes quota). Every attempt is
  appended to a gitignored `send_log.jsonl` audit trail. All config documented
  in `.env.example`.
- **6b.** Suppression + the real send endpoint. `unsubscribes` table; an address
  on it is refused **in every mode, dry_run included**. A plain-text opt-out
  footer is appended to every outbound body (the stored draft stays clean; a
  real one-click link waits on the Block 7 deployed URL). `POST /emails/{id}/send`
  promoted from the 501 stub to the real endpoint honoring all layers and
  reporting which checks applied; the recipient comes from the request body or
  the target row, and a missing one is refused. `POST /unsubscribes` for manual
  additions. Extended the additive migration to cover
  `provider_message_id`/`opened_at`/`replied_at`.
- **6c.** `POST /webhooks/resend`. The Svix signature is verified against
  `RESEND_WEBHOOK_SECRET` before anything is applied, and the endpoint fails
  closed (503 with no secret, 400 on a bad signature). Verified events update
  the row: delivered → `delivered`, opened → `opened_at`, bounced → `bounced`,
  and a complaint auto-adds the address to `unsubscribes`. Signature
  verification is a few lines of stdlib `hmac` rather than the `svix` dep.
- **6d.** Tests + docs. `tests/test_send.py` covers every layer with the network
  seam mocked and asserted against (dry_run never touches the wire, suppression
  refusal even in dry_run, allowlist/daily-cap/config refusals, recipient
  resolution, already-sent guard, a full live happy-path with the footer on the
  wire, webhook signature round-trip, and the complaint→suppressed→future-send-
  refused flow); API-level webhook tests (missing-secret 503, bad-signature 400,
  valid complaint suppresses) live in `test_api_wiring.py`. New
  [docs/sending-safety.md](sending-safety.md) documents the model and the
  go-live steps; README status updated. A flagless `pytest tests/` now runs 35
  free tests and skips the 4 paid ones.

HARD GATES respected throughout: no real email was ever sent (the suite runs in
dry_run with the network mocked), and `backend/.env` was never touched — only
`.env.example`. Arming a live send remains a deliberate, multi-step act.

Not done in this block: deploy, the real one-click unsubscribe link (both Block 7).
