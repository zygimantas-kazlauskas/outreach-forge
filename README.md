# Outreach Forge

A multi-agent personalized B2B outreach engine. The engine itself is generic; the repo ships with one fully-developed example service (AI voice agents for small service businesses) so the end-to-end behavior is demonstrable on a realistic use case rather than abstract toy data.

## Status

**Block 6 complete — Resend sending behind a layered safety model.** `POST /emails/{id}/send` now sends through Resend, but a real email needs *every* safety layer to pass at once: `SEND_MODE` must be exactly `live` (it defaults to dry_run — no network call ever, the row is marked `dry_run` with a fake provider id), the recipient must be on `RECIPIENT_ALLOWLIST` when one is set, the address must not be on the unsubscribe list (enforced in every mode), and the run must be under `SEND_DAILY_LIMIT` (DB-counted, UTC). Sending is decoupled from generation — the orchestrator never sends. A plain-text opt-out footer is appended to every outbound body, and `POST /webhooks/resend` ingests delivered/opened/bounced/complained events (Svix signature verified) with a complaint auto-suppressing the address. The full model and go-live steps are in [docs/sending-safety.md](docs/sending-safety.md). Everything is tested without Resend credentials by mocking the one network seam.

Earlier blocks: the orchestrator (Block 3) runs targets concurrently through the Researcher → Writer → Critic chain with SQLite persistence and per-target error isolation; the REST API + live SSE (Block 4) expose runs and drafts; the Next.js frontend (Block 5) provides target intake, a live run view, and a results grid.

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

The following block is planned but **not yet implemented**:

- **Block 7** — Deploy (Vercel for frontend, Fly.io or Render for backend) + polish, including the real one-click unsubscribe link the footer points at.

---

Built by Žygimantas Kazlauskas · [LinkedIn](https://linkedin.com/in/kazlauskas-zygimantas)
