/**
 * Reducer tests fed with event sequences recorded from the backend wiring
 * tests (tests/test_orchestrator_wiring.py + test_api_wiring.py): 2 targets,
 * researcher → writer → critic each, one optional failure at the writer.
 */

import { describe, expect, it } from "vitest";

import type { AgentName, RunEvent } from "./types";
import {
  applyEvents,
  boardCounts,
  initialBoard,
  reduceBoard,
} from "./runBoard";

const TS = "2026-06-11T20:00:00+00:00";

function agentPair(
  target_id: number,
  target_name: string,
  agent: AgentName,
  latency_ms: number,
): RunEvent[] {
  return [
    { type: "agent_started", run_id: 1, ts: TS, target_id, target_name, agent },
    { type: "agent_finished", run_id: 1, ts: TS, target_id, target_name, agent, latency_ms },
  ];
}

const HAPPY_SEQUENCE: RunEvent[] = [
  { type: "run_started", run_id: 1, ts: TS, target_count: 2 },
  ...agentPair(1, "Alpha Dental", "researcher", 10),
  ...agentPair(2, "Beta Salon", "researcher", 11),
  ...agentPair(1, "Alpha Dental", "writer", 12),
  ...agentPair(2, "Beta Salon", "writer", 13),
  ...agentPair(1, "Alpha Dental", "critic", 14),
  { type: "target_completed", run_id: 1, ts: TS, target_id: 1, target_name: "Alpha Dental" },
  ...agentPair(2, "Beta Salon", "critic", 15),
  { type: "target_completed", run_id: 1, ts: TS, target_id: 2, target_name: "Beta Salon" },
  { type: "run_completed", run_id: 1, ts: TS, status: "completed" },
];

const FAILURE_SEQUENCE: RunEvent[] = [
  { type: "run_started", run_id: 2, ts: TS, target_count: 2 },
  ...agentPair(1, "Alpha Dental", "researcher", 10),
  ...agentPair(2, "Beta Salon", "researcher", 11),
  ...agentPair(1, "Alpha Dental", "writer", 12),
  { type: "agent_started", run_id: 2, ts: TS, target_id: 2, target_name: "Beta Salon", agent: "writer" },
  { type: "target_failed", run_id: 2, ts: TS, target_id: 2, target_name: "Beta Salon", error: "RuntimeError: writer exploded" },
  ...agentPair(1, "Alpha Dental", "critic", 14),
  { type: "target_completed", run_id: 2, ts: TS, target_id: 1, target_name: "Alpha Dental" },
  { type: "run_completed", run_id: 2, ts: TS, status: "completed" },
];

describe("reduceBoard", () => {
  it("builds the full board from a happy sequence", () => {
    const board = applyEvents(initialBoard, HAPPY_SEQUENCE);

    expect(board.runStatus).toBe("completed");
    expect(board.targetCount).toBe(2);
    expect(Object.keys(board.targets)).toHaveLength(2);

    for (const card of Object.values(board.targets)) {
      expect(card.status).toBe("completed");
      expect(card.stages.researcher.phase).toBe("done");
      expect(card.stages.writer.phase).toBe("done");
      expect(card.stages.critic.phase).toBe("done");
    }
    expect(board.targets[1].stages.critic).toEqual({ phase: "done", latency_ms: 14 });
    expect(boardCounts(board)).toEqual({ completed: 2, failed: 0, working: 0, pending: 0 });
  });

  it("shows in-flight stages mid-run", () => {
    const midRun = applyEvents(initialBoard, HAPPY_SEQUENCE.slice(0, 4));
    // Alpha finished researcher; Beta's researcher is running.
    expect(midRun.runStatus).toBe("running");
    expect(midRun.targets[1].stages.researcher.phase).toBe("done");
    expect(midRun.targets[1].stages.writer.phase).toBe("idle");
    expect(midRun.targets[2].stages.researcher.phase).toBe("running");
    expect(boardCounts(midRun).working).toBe(2);
  });

  it("records a failed target with its error and keeps the run completed", () => {
    const board = applyEvents(initialBoard, FAILURE_SEQUENCE);

    expect(board.runStatus).toBe("completed"); // partial success
    expect(board.targets[2].status).toBe("failed");
    expect(board.targets[2].error).toContain("writer exploded");
    expect(board.targets[2].stages.writer.phase).toBe("running"); // died mid-stage
    expect(board.targets[1].status).toBe("completed");
    expect(boardCounts(board)).toEqual({ completed: 1, failed: 1, working: 0, pending: 0 });
  });

  it("is idempotent: replaying the same history yields the same board", () => {
    const once = applyEvents(initialBoard, HAPPY_SEQUENCE);
    const twice = applyEvents(once, HAPPY_SEQUENCE); // reconnect replay
    expect(twice).toEqual(once);

    const failedOnce = applyEvents(initialBoard, FAILURE_SEQUENCE);
    const failedTwice = applyEvents(failedOnce, FAILURE_SEQUENCE);
    expect(failedTwice).toEqual(failedOnce);
  });

  it("does not regress a done stage when a stale agent_started replays", () => {
    const board = applyEvents(initialBoard, HAPPY_SEQUENCE);
    const stale = reduceBoard(board, {
      type: "agent_started",
      run_id: 1,
      ts: TS,
      target_id: 1,
      target_name: "Alpha Dental",
      agent: "critic",
    });
    expect(stale.targets[1].stages.critic).toEqual({ phase: "done", latency_ms: 14 });
  });

  it("handles the synthetic terminal event (no ts) for finished runs", () => {
    const board = applyEvents(initialBoard, [
      { type: "run_completed", run_id: 3, status: "failed" },
    ]);
    expect(board.runStatus).toBe("failed");
  });

  it("counts unseen targets as pending", () => {
    const board = applyEvents(initialBoard, [
      { type: "run_started", run_id: 4, ts: TS, target_count: 3 },
      ...agentPair(1, "Alpha Dental", "researcher", 10),
    ]);
    expect(boardCounts(board)).toEqual({ completed: 0, failed: 0, working: 1, pending: 2 });
  });
});
