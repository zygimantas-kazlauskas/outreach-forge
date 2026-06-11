/**
 * TypeScript mirror of the backend API contract. The backend is the source
 * of truth: backend/main.py (request/response models, status codes) and
 * backend/orchestrator.py (SSE event publishes). Do not add fields here that
 * the backend does not send.
 */

// --- POST /runs request (main.py TargetIn / RunCreate) ----------------------

export interface TargetIn {
  /** Backend defaults to "" (maps to targets.demo_id). */
  id?: string;
  /** Required, min length 1 — empty string is a 422. */
  company_name: string;
  url?: string | null;
  contact_name?: string | null;
  contact_role?: string | null;
  /** Backend defaults to "". */
  notes?: string;
}

export interface RunCreate {
  service_id: string;
  /** Min 1 target — empty list is a 422. */
  targets: TargetIn[];
  /** 1-10; backend defaults to 3. */
  concurrency?: number;
}

/** POST /runs 202 response. 404 on unknown service_id, 422 on validation. */
export interface RunCreated {
  run_id: number;
  status: "running";
  target_count: number;
}

// --- GET /runs/{id} (main.py _run_snapshot) ----------------------------------

export type RunStatus = "pending" | "running" | "completed" | "failed";

export interface RunSnapshot {
  run_id: number;
  status: RunStatus;
  service_id: string;
  created_at: string;
  notes: string | null;
  target_count: number;
  targets: { pending: number; completed: number; failed: number };
  emails: number;
}

// --- GET /runs/{id}/emails (main.py _emails_for_run) -------------------------

export interface RunEmail {
  email_id: number;
  target_id: number;
  target_name: string | null;
  subject: string;
  body: string;
  chosen_hook: string | null;
  source: string;
  send_status: string;
  created_at: string;
}

// --- GET /runs/{id}/events SSE union (orchestrator.py publishes) -------------
// Every event carries run_id; all carry ts EXCEPT the synthetic run_completed
// the server emits when replaying a finished run with no bus history (after a
// process restart) — so ts is optional on RunCompletedEvent only.
// Keepalives arrive as SSE comment lines (": keepalive") which EventSource
// ignores natively. The stream closes after run_completed.

export type AgentName = "researcher" | "writer" | "critic";

export interface RunStartedEvent {
  type: "run_started";
  run_id: number;
  ts: string;
  target_count: number;
}

export interface AgentStartedEvent {
  type: "agent_started";
  run_id: number;
  ts: string;
  target_id: number;
  target_name: string;
  agent: AgentName;
}

export interface AgentFinishedEvent {
  type: "agent_finished";
  run_id: number;
  ts: string;
  target_id: number;
  target_name: string;
  agent: AgentName;
  latency_ms: number;
}

export interface TargetCompletedEvent {
  type: "target_completed";
  run_id: number;
  ts: string;
  target_id: number;
  target_name: string;
}

export interface TargetFailedEvent {
  type: "target_failed";
  run_id: number;
  ts: string;
  target_id: number;
  target_name: string;
  error: string;
}

export interface RunCompletedEvent {
  type: "run_completed";
  run_id: number;
  /** Absent on the synthetic terminal event for finished runs without bus history. */
  ts?: string;
  status: "completed" | "failed";
}

export type RunEvent =
  | RunStartedEvent
  | AgentStartedEvent
  | AgentFinishedEvent
  | TargetCompletedEvent
  | TargetFailedEvent
  | RunCompletedEvent;
