/**
 * Per-target pipeline board: one card per target, three stage chips each
 * (researcher → writer → critic), error shown inline on failure.
 */

import { AGENTS, boardCounts, type BoardState, type StageState, type TargetCard } from "@/lib/runBoard";
import { cardClass } from "@/components/ui";

function StageChip({ agent, stage }: { agent: string; stage: StageState }) {
  const base = "rounded px-2 py-0.5 text-xs font-medium";
  if (stage.phase === "done") {
    return (
      <span className={`${base} bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300`}>
        {agent} ✓ {(stage.latency_ms / 1000).toFixed(1)}s
      </span>
    );
  }
  if (stage.phase === "running") {
    return (
      <span className={`${base} animate-pulse bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300`}>
        {agent}…
      </span>
    );
  }
  return (
    <span className={`${base} bg-neutral-100 text-neutral-400 dark:bg-neutral-900 dark:text-neutral-600`}>
      {agent}
    </span>
  );
}

function TargetCardView({ card }: { card: TargetCard }) {
  const border =
    card.status === "completed"
      ? "border-green-300 dark:border-green-900"
      : card.status === "failed"
        ? "border-red-300 dark:border-red-900"
        : "";
  return (
    <div className={`${cardClass} ${border} space-y-2`}>
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm font-medium">{card.target_name}</span>
        <span className="shrink-0 text-xs text-neutral-500">
          {card.status === "completed" ? "done" : card.status === "failed" ? "failed" : "working"}
        </span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {AGENTS.map((agent) => (
          <StageChip key={agent} agent={agent} stage={card.stages[agent]} />
        ))}
      </div>
      {card.status === "failed" && card.error && (
        <p className="break-words text-xs text-red-700 dark:text-red-400">{card.error}</p>
      )}
    </div>
  );
}

export function RunBoard({ board }: { board: BoardState }) {
  const cards = Object.values(board.targets).sort((a, b) => a.target_id - b.target_id);
  const { pending } = boardCounts(board);

  if (cards.length === 0 && pending === 0) {
    return (
      <p className="text-sm text-neutral-500">
        {board.runStatus === "waiting"
          ? "Waiting for the run to start…"
          : "No target activity recorded for this run."}
      </p>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {cards.map((card) => (
        <TargetCardView key={card.target_id} card={card} />
      ))}
      {Array.from({ length: pending }, (_, i) => (
        <div key={`pending-${i}`} className={`${cardClass} opacity-60`}>
          <span className="text-sm text-neutral-500">Queued target…</span>
        </div>
      ))}
    </div>
  );
}
