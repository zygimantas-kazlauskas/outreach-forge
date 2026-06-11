"""In-process pub/sub for live run progress.

The orchestrator publishes events as it works; the SSE endpoint subscribes
and relays them to the browser. Single-process by design: run_batch executes
as a background task inside the same uvicorn process that serves the SSE
stream, so no broker is needed at this scale.

Late subscribers get a history replay first, then live events, so connecting
to a run's event stream mid-run (or after it finished) still yields the full
picture.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Any

# Known limitation: history is capped per run but never evicted across runs,
# so memory grows with run count; eviction/archival is deferred to Block 7.
HISTORY_LIMIT = 1000  # per run; a 3-target run emits ~25 events

TERMINAL_EVENT = "run_completed"


class EventBus:
    def __init__(self) -> None:
        self._queues: dict[int, list[asyncio.Queue]] = {}
        self._history: dict[int, deque] = {}

    def publish(self, run_id: int, event: dict[str, Any]) -> None:
        """Stamp and fan out an event. Safe to call only from the event loop."""
        event = {
            **event,
            "run_id": run_id,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self._history.setdefault(run_id, deque(maxlen=HISTORY_LIMIT)).append(event)
        for queue in self._queues.get(run_id, []):
            queue.put_nowait(event)

    def subscribe(self, run_id: int) -> tuple[list[dict[str, Any]], asyncio.Queue]:
        """Return (history so far, live queue for everything after it)."""
        queue: asyncio.Queue = asyncio.Queue()
        self._queues.setdefault(run_id, []).append(queue)
        return list(self._history.get(run_id, [])), queue

    def unsubscribe(self, run_id: int, queue: asyncio.Queue) -> None:
        subscribers = self._queues.get(run_id)
        if subscribers and queue in subscribers:
            subscribers.remove(queue)
        if subscribers == []:
            del self._queues[run_id]

    def reset(self) -> None:
        """Drop all history and subscribers. For tests."""
        self._queues.clear()
        self._history.clear()


bus = EventBus()
