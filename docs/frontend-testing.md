# Frontend manual test script

Click-through paths for the Block 5 UI. Automated coverage lives in
`frontend/lib/runBoard.test.ts` (SSE board reducer, `npm test`); everything
here is manual. Paths marked **[PAID]** make real Anthropic API calls —
everything else is free.

## Setup

Two terminals:

```bash
# backend
cd backend && .venv/Scripts/python.exe -m uvicorn main:app --reload   # :8000

# frontend
cd frontend && npm run dev                                            # :3000
```

`NEXT_PUBLIC_API_URL` overrides the API base (default `http://localhost:8000`).

## 1. Intake validation (free)

- Open `http://localhost:3000`. One service is preselected; one empty target row.
- Click **Start run** with an empty company name → inline "Company name is
  required", no network request.
- Set concurrency to `0` or `11` → inline "Whole number, 1 to 10."
- **Remove** is disabled while only one row exists; **Add target** appends rows.

## 2. API-down behavior (free)

- Stop the backend, submit a valid form → readable banner ("Cannot reach the
  API at … Is the backend running?"), button returns to **Start run**.
- Visit `/runs/1` with the backend down → same readable banner + back link.

## 3. Bad run routes (free, backend up)

- `/runs/999999` → "Run 999999 not found" banner + back link.
- `/runs/abc` → '"abc" is not a run id.' banner + back link.

## 4. Live run + results [PAID — explicit go only, ~$0.50 for 3 targets]

- Compose a run with the 3 demo targets from `backend/seed/demo_targets.json`
  (copy notes into the Notes fields), concurrency 3 → **Start run**.
- Expect: redirect to `/runs/{id}`; status chip `running` + "live"; three
  cards appear as researcher events arrive; chips progress
  researcher… → ✓ → writer… → ✓ → critic… → ✓ with latencies; card borders
  flip green on completion; header counts update live.
- On the terminal event: status `completed`, feed shows "stream ended",
  **Final drafts** section loads 3 emails (target name, subject, body, hook).
- **Copy subject + body** → paste somewhere and verify contents.
- **Send** is disabled with a Block 6 tooltip.

## 5. Replay of a finished run (free once a run exists)

- Re-open `/runs/{id}` of the finished run (or hard-refresh): the SSE history
  replay reconstructs the full board (all chips ✓) and drafts render.
- Restart the backend, then re-open the same run: board shows no per-target
  activity (history was in-process) but status/counts come from the snapshot,
  the stream closes cleanly via the synthetic terminal event, and drafts
  still render (they come from SQLite).

## 6. Dark mode (free)

- Toggle the OS color scheme; both routes should remain readable (the UI
  uses `prefers-color-scheme` via the scaffold's CSS variables).
