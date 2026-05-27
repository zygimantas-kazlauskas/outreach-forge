# Build log

One entry per evening session. Dates are real — no backdating, no future-dating.

## Block 1 — scaffold (2026-05-27)

Project initialized. Created the monorepo layout (`frontend/`, `backend/`, `docs/`), `.gitignore`, MIT license, and the design-contract documents.

- **Frontend:** scaffolded with `create-next-app@14` (App Router, TypeScript strict, Tailwind v3, no `src/`, no ESLint scaffold). Replaced the default template page with a minimal placeholder showing the project name and a one-line description. Updated `<head>` metadata. `next build` passes; `npm run dev` serves on `http://localhost:3000`.
- **Backend:** created a Python 3.12 venv at `backend/.venv`. `requirements.txt` pins `fastapi`, `uvicorn[standard]`, `pydantic` only — SQLAlchemy, Anthropic SDK, and Resend are intentionally deferred to the blocks that actually use them. `main.py` exposes a single `GET /health` returning `{"status": "ok"}`. Verified locally with `uvicorn main:app` + `curl`.
- **Docs:** wrote `architecture.md` covering the three-agent design (Researcher / Writer / Critic), the orchestrator's hand-rolled async stance, the `llm_call` LLM-provider abstraction, the SQLite schema sketch, the SSE frontend pattern, and the worked-example service. Wrote this build log.
- **Not done:** no agent code, no LLM wrapper, no database, no API endpoints beyond `/health`, no UI beyond the placeholder. All of that is later blocks.

One commit closes the block: `Block 1: scaffold (Next.js frontend + FastAPI backend running locally)`.
