"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { ApiError, getRun } from "@/lib/api";
import { boardCounts } from "@/lib/runBoard";
import { useRunEvents } from "@/lib/useRunEvents";
import type { RunSnapshot, RunStatus } from "@/lib/types";
import { EmailsGrid } from "@/components/EmailsGrid";
import { RunBoard } from "@/components/RunBoard";
import { ErrorBanner, Spinner } from "@/components/ui";

const STATUS_STYLES: Record<RunStatus, string> = {
  pending: "bg-neutral-100 text-neutral-600 dark:bg-neutral-900 dark:text-neutral-400",
  running: "animate-pulse bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  completed: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300",
  failed: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
};

const CONNECTION_LABELS = {
  connecting: "connecting to live feed…",
  open: "live",
  closed: "stream ended",
  error: "live feed unavailable",
} as const;

export default function RunPage() {
  const params = useParams<{ id: string }>();
  const runId = /^\d+$/.test(params.id) ? Number(params.id) : null;

  const [snapshot, setSnapshot] = useState<RunSnapshot | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const { board, connection } = useRunEvents(runId);

  useEffect(() => {
    if (runId === null) {
      setLoadError(`"${params.id}" is not a run id.`);
      return;
    }
    let cancelled = false;
    getRun(runId)
      .then((s) => !cancelled && setSnapshot(s))
      .catch((e) => {
        if (cancelled) return;
        setLoadError(e instanceof ApiError ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [runId, params.id]);

  if (loadError) {
    return (
      <main className="mx-auto max-w-4xl space-y-4 p-6">
        <ErrorBanner message={loadError} />
        <Link href="/" className="text-sm underline">
          ← back to new run
        </Link>
      </main>
    );
  }

  if (!snapshot) {
    return (
      <main className="mx-auto max-w-4xl p-6">
        <Spinner label="Loading run…" />
      </main>
    );
  }

  // The board is the live source once events flow; the snapshot covers the
  // time before run_started and runs whose history predates this process.
  const status: RunStatus =
    board.runStatus === "waiting" ? snapshot.status : board.runStatus;
  const live = boardCounts(board);
  const counts =
    Object.keys(board.targets).length > 0 || board.targetCount !== null
      ? { completed: live.completed, failed: live.failed, pending: live.pending + live.working }
      : snapshot.targets;

  return (
    <main className="mx-auto max-w-4xl space-y-6 p-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">Run #{snapshot.run_id}</h1>
          <span className={`rounded px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}>
            {status}
          </span>
          <span className="text-xs text-neutral-500">{CONNECTION_LABELS[connection]}</span>
        </div>
        <p className="text-sm text-neutral-500">
          {snapshot.service_id} · {snapshot.target_count} target
          {snapshot.target_count === 1 ? "" : "s"} · started{" "}
          {new Date(snapshot.created_at).toLocaleString()}
        </p>
        <p className="text-sm">
          <span className="text-green-700 dark:text-green-400">{counts.completed} completed</span>
          {" · "}
          <span className="text-red-700 dark:text-red-400">{counts.failed} failed</span>
          {" · "}
          <span className="text-neutral-500">{counts.pending} in progress</span>
        </p>
      </header>

      <section className="space-y-3">
        <h2 className="text-sm font-medium">Pipeline</h2>
        <RunBoard board={board} />
      </section>

      {(status === "completed" || status === "failed") && runId !== null && (
        <section className="space-y-3">
          <h2 className="text-sm font-medium">Final drafts</h2>
          <EmailsGrid runId={runId} />
        </section>
      )}

      <footer>
        <Link href="/" className="text-sm text-neutral-500 underline">
          ← new run
        </Link>
      </footer>
    </main>
  );
}
