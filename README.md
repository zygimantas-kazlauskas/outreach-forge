# Outreach Forge

A multi-agent personalized B2B outreach engine. The engine itself is generic; the repo ships with one fully-developed example service (AI voice agents for small service businesses) so the end-to-end behavior is demonstrable on a realistic use case rather than abstract toy data.

## Status

**Block 4 complete — REST API + live SSE on top of the pipeline.** `POST /runs` kicks off a batch as a background task and returns the run id immediately; `GET /runs/{id}/events` streams live agent activity over SSE (with history replay for late subscribers); `GET /runs/{id}` and `GET /runs/{id}/emails` expose status and final drafts. The orchestrator (Block 3) runs targets concurrently through the Researcher → Writer → Critic chain with SQLite persistence and per-target error isolation, verified end-to-end against the real API. Prompts have been through a measured tuning pass (see `docs/tuning/`). No frontend yet, no email sending (`POST /emails/{id}/send` returns 501 until Resend lands in Block 6).

## Architecture

Three cooperating agents per outreach target:

1. **Researcher** — gathers and structures signals about the target.
2. **Writer** — picks one hook and drafts a grounded email.
3. **Critic** — critiques on five dimensions and produces an improved version.

The orchestrator is a plain hand-rolled async Python function that chains the three agents. No LangGraph, no CrewAI, no agent framework. See [docs/architecture.md](docs/architecture.md) for the full design contract, including the LLM-provider abstraction, persistence schema sketch, and the worked-example service.

## Stack

- **Frontend:** Next.js 14 (App Router), TypeScript (strict), Tailwind CSS v3. shadcn/ui and Recharts added later, only when components are actually needed.
- **Backend:** Python 3.11+, FastAPI, uvicorn, Anthropic Python SDK (wired in Block 2). SQLite + SQLAlchemy wired in Block 3. Resend wired in Block 6.
- **Layout:** Plain monorepo (`frontend/` and `backend/`). No Docker, no Turborepo, no Nx.
- **Backend env:** `venv` (no Poetry / pipenv).

## Local setup

Clone, then run frontend and backend in two terminals.

**Frontend** (Node 18+ recommended):

```bash
cd frontend
npm install
npm run dev
# http://localhost:3000
```

**Backend** (Python 3.11+):

```bash
cd backend
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
# http://localhost:8000/health -> {"status":"ok"}
```

## Build approach

This project is being built across multiple focused evening sessions, not in a single sprint. Each commit corresponds to one logical block of work, dated as it happens. The build log lives in [docs/build-log.md](docs/build-log.md). No compression, no backdating — if it takes five evenings, the history shows five evenings.

## What's next

The following blocks are planned but **not yet implemented**:

- **Block 5** — Frontend UI: target intake, run view with live agent feed, results table.
- **Block 6** — Resend integration for outbound email (dry-run by default).
- **Block 7** — Deploy (Vercel for frontend, Fly.io or Render for backend) + polish.

---

Built by Žygimantas Kazlauskas · [LinkedIn](https://linkedin.com/in/kazlauskas-zygimantas)
