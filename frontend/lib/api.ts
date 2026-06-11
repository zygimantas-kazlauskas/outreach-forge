/**
 * Typed client for the backend API plus an EventSource wrapper for the
 * per-run SSE stream. All shapes come from lib/types.ts (mirrored from the
 * backend — the source of truth).
 */

import { API_BASE } from "./config";
import type {
  RunCreate,
  RunCreated,
  RunEvent,
  RunEmail,
  RunSnapshot,
} from "./types";

export class ApiError extends Error {
  constructor(
    /** HTTP status; 0 means the API was unreachable. */
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(
      0,
      `Cannot reach the API at ${API_BASE}. Is the backend running?`,
    );
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body && body.detail) {
        detail =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail);
      }
    } catch {
      // non-JSON error body; keep the status line
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export function createRun(payload: RunCreate): Promise<RunCreated> {
  return request<RunCreated>("/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getRun(runId: number): Promise<RunSnapshot> {
  return request<RunSnapshot>(`/runs/${runId}`);
}

export function getRunEmails(runId: number): Promise<RunEmail[]> {
  return request<RunEmail[]>(`/runs/${runId}/emails`);
}

/** Stub until Block 6 — the backend answers 501, surfaced as an ApiError. */
export function sendEmail(emailId: number): Promise<never> {
  return request<never>(`/emails/${emailId}/send`, { method: "POST" });
}

// --- SSE subscription ---------------------------------------------------------

export type SseConnectionState = "connecting" | "open" | "closed" | "error";

export interface RunEventHandlers {
  onEvent: (event: RunEvent) => void;
  onStateChange?: (state: SseConnectionState) => void;
  /**
   * Fired when EventSource re-opens after a dropped connection. The backend
   * replays the full history on every (re)connection, so consumers must
   * reset any accumulated state here or apply events idempotently.
   */
  onReconnect?: () => void;
}

export interface RunEventSubscription {
  close: () => void;
}

/**
 * Subscribe to a run's live event stream. Closes itself when the terminal
 * run_completed event arrives. Keepalive comments are ignored by
 * EventSource; transient drops auto-reconnect (see onReconnect).
 */
export function subscribeToRunEvents(
  runId: number,
  handlers: RunEventHandlers,
): RunEventSubscription {
  const source = new EventSource(`${API_BASE}/runs/${runId}/events`);
  let everOpened = false;

  handlers.onStateChange?.("connecting");

  source.onopen = () => {
    if (everOpened) handlers.onReconnect?.();
    everOpened = true;
    handlers.onStateChange?.("open");
  };

  source.onmessage = (message) => {
    let event: RunEvent;
    try {
      event = JSON.parse(message.data) as RunEvent;
    } catch {
      return; // malformed frame; skip rather than kill the stream
    }
    handlers.onEvent(event);
    if (event.type === "run_completed") {
      source.close();
      handlers.onStateChange?.("closed");
    }
  };

  source.onerror = () => {
    if (source.readyState === EventSource.CLOSED) {
      handlers.onStateChange?.("error");
    } else {
      handlers.onStateChange?.("connecting"); // auto-reconnect in flight
    }
  };

  return {
    close: () => {
      source.close();
      handlers.onStateChange?.("closed");
    },
  };
}
