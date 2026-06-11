"use client";

/**
 * React hook binding the SSE subscription to the board reducer.
 *
 * Reconnect semantics: the backend replays full history on every
 * (re)connection, so on reconnect we reset the board and let the replay
 * rebuild it. The reducer is also idempotent, so even without the reset a
 * replay would not corrupt state — belt and suspenders.
 */

import { useEffect, useReducer, useState } from "react";

import { subscribeToRunEvents, type SseConnectionState } from "./api";
import { initialBoard, reduceBoard, type BoardState } from "./runBoard";
import type { RunEvent } from "./types";

type BoardAction = { kind: "event"; event: RunEvent } | { kind: "reset" };

function boardReducer(state: BoardState, action: BoardAction): BoardState {
  return action.kind === "reset" ? initialBoard : reduceBoard(state, action.event);
}

export function useRunEvents(runId: number | null) {
  const [board, dispatch] = useReducer(boardReducer, initialBoard);
  const [connection, setConnection] = useState<SseConnectionState>("connecting");

  useEffect(() => {
    if (runId === null) return;
    dispatch({ kind: "reset" });
    const subscription = subscribeToRunEvents(runId, {
      onEvent: (event) => dispatch({ kind: "event", event }),
      onStateChange: setConnection,
      onReconnect: () => dispatch({ kind: "reset" }),
    });
    return () => subscription.close();
  }, [runId]);

  return { board, connection };
}
