/**
 * Pure reducer turning the SSE event stream into per-target board state.
 *
 * IDEMPOTENT BY DESIGN: EventSource auto-reconnects after a drop and the
 * backend replays the full history on every connection, so the same event
 * may be applied more than once. Nothing here increments counters or
 * toggles — every transition sets absolute state, and replaying a prefix
 * of already-applied events leaves the board unchanged. (The run-view hook
 * also resets the board on reconnect; either mechanism alone is enough.)
 */

import type { AgentName, RunEvent } from "./types";

export const AGENTS: AgentName[] = ["researcher", "writer", "critic"];

export type StageState =
  | { phase: "idle" }
  | { phase: "running" }
  | { phase: "done"; latency_ms: number };

export interface TargetCard {
  target_id: number;
  target_name: string;
  stages: Record<AgentName, StageState>;
  status: "working" | "completed" | "failed";
  error?: string;
}

export interface BoardState {
  /** "waiting" until run_started arrives (or for a pre-execution run). */
  runStatus: "waiting" | "running" | "completed" | "failed";
  /** From run_started; null until then. */
  targetCount: number | null;
  /** Keyed by target_id; cards appear as their first agent event arrives. */
  targets: Record<number, TargetCard>;
}

export const initialBoard: BoardState = {
  runStatus: "waiting",
  targetCount: null,
  targets: {},
};

function freshCard(target_id: number, target_name: string): TargetCard {
  return {
    target_id,
    target_name,
    stages: {
      researcher: { phase: "idle" },
      writer: { phase: "idle" },
      critic: { phase: "idle" },
    },
    status: "working",
  };
}

function withCard(
  state: BoardState,
  target_id: number,
  target_name: string,
  update: (card: TargetCard) => TargetCard,
): BoardState {
  const card = state.targets[target_id] ?? freshCard(target_id, target_name);
  return {
    ...state,
    targets: { ...state.targets, [target_id]: update(card) },
  };
}

export function reduceBoard(state: BoardState, event: RunEvent): BoardState {
  switch (event.type) {
    case "run_started":
      return { ...state, runStatus: "running", targetCount: event.target_count };

    case "agent_started":
      return withCard(state, event.target_id, event.target_name, (card) => {
        // Don't regress a finished stage to running on a stale duplicate.
        if (card.stages[event.agent].phase === "done") return card;
        return {
          ...card,
          stages: { ...card.stages, [event.agent]: { phase: "running" } },
        };
      });

    case "agent_finished":
      return withCard(state, event.target_id, event.target_name, (card) => ({
        ...card,
        stages: {
          ...card.stages,
          [event.agent]: { phase: "done", latency_ms: event.latency_ms },
        },
      }));

    case "target_completed":
      return withCard(state, event.target_id, event.target_name, (card) => ({
        ...card,
        status: "completed",
      }));

    case "target_failed":
      return withCard(state, event.target_id, event.target_name, (card) => ({
        ...card,
        status: "failed",
        error: event.error,
      }));

    case "run_completed":
      return { ...state, runStatus: event.status };

    default:
      return state;
  }
}

export function applyEvents(state: BoardState, events: RunEvent[]): BoardState {
  return events.reduce(reduceBoard, state);
}

/** Live counts derived from the board (never incremented — see header note). */
export function boardCounts(state: BoardState) {
  const cards = Object.values(state.targets);
  const completed = cards.filter((c) => c.status === "completed").length;
  const failed = cards.filter((c) => c.status === "failed").length;
  const known = cards.length;
  const pending =
    state.targetCount !== null ? Math.max(0, state.targetCount - known) : 0;
  return { completed, failed, working: known - completed - failed, pending };
}
