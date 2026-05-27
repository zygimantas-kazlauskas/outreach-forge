# Outreach Forge

A multi-agent personalized B2B outreach engine. The engine itself is generic; the repo ships with one fully-developed example service (AI voice agents for small service businesses) so the end-to-end behavior is demonstrable on a realistic use case rather than abstract toy data.

## Status

**Block 1 (scaffold).** Both frontend and backend run locally. No agent logic, no LLM calls, no database, no email sending yet. Those come in subsequent blocks.

## Architecture

Three cooperating agents per outreach target:

1. **Researcher** — gathers and structures signals about the target.
2. **Writer** — picks one hook and drafts a grounded email.
3. **Critic** — critiques on five dimensions and produces an improved version.

The orchestrator is a plain hand-rolled async Python function that chains the three agents. No LangGraph, no CrewAI, no agent framework. See [docs/architecture.md](docs/architecture.md) for the full design contract, including the LLM-provider abstraction, persistence schema sketch, and the worked-example service.

## Stack

- **Frontend:** Next.js 14 (App Router), TypeScript (strict), Tailwind CSS v3. shadcn/ui and Recharts added later, only when components are actually needed.
- **Backend:** Python 3.11+, FastAPI, uvicorn. SQLite + SQLAlchemy wired in Block 4. Anthropic Python SDK wired in Block 2. Resend wired in Block 7.
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

- **Block 2** — LLM provider wrapper + Researcher agent (Anthropic SDK).
- **Block 3** — Writer agent + Critic agent.
- **Block 4** — Orchestrator and SQLite persistence (runs, targets, agent_outputs, emails).
- **Block 5** — FastAPI endpoints + SSE stream for live agent activity.
- **Block 6** — Frontend UI: target intake, run view with live agent feed, results table.
- **Block 7** — Resend integration for outbound email (dry-run by default).
- **Block 8** — Deploy (Vercel for frontend, Fly.io or Render for backend) + polish.

---

Built by Žygimantas Kazlauskas · [LinkedIn](https://linkedin.com/in/kazlauskas-zygimantas)
