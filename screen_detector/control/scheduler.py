from __future__ import annotations

import heapq
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .input_sendinput import InputBackend


@dataclass(order=True, frozen=True)
class ScheduledAction:
    target_ns: int
    sequence: int
    lane: int = field(compare=False)
    action: str | int | None = field(compare=False, default=None)
    kind: str = field(compare=False, default="press")
    note_id: int | None = field(compare=False, default=None)


@dataclass
class SchedulerStats:
    scheduled: int = 0
    issued: int = 0
    cancelled: int = 0
    stale_disarms: int = 0
    timing_errors_ns: list[int] = field(default_factory=list)

    def percentile_error_ms(self, percentile: float = 0.99) -> float:
        if not self.timing_errors_ns:
            return 0.0
        values = sorted(abs(value) for value in self.timing_errors_ns)
        index = min(len(values) - 1, int((len(values) - 1) * percentile))
        return values[index] / 1_000_000


class Scheduler:
    """Bounded-latency priority scheduler for tap events."""

    def __init__(self, backend: InputBackend, stale_timeout_ms: int = 250, spin_window_us: int = 800, now_ns: Callable[[], int] = time.perf_counter_ns) -> None:
        self.backend = backend
        self.stale_timeout_ns = stale_timeout_ms * 1_000_000
        self.spin_window_ns = spin_window_us * 1_000
        self.now_ns = now_ns
        self.stats = SchedulerStats()
        self._queue: list[ScheduledAction] = []
        self._sequence = 0
        self._condition = threading.Condition()
        self._armed = False
        self._running = False
        self._last_frame_ns: int | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        with self._condition:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run, name="auttorna-scheduler", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._condition:
            self._running = False
            self._armed = False
            self._queue.clear()
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self.backend.release_all()

    def arm(self) -> None:
        with self._condition:
            self._armed = True
            self._condition.notify_all()

    def disarm(self) -> None:
        with self._condition:
            self._armed = False
            self.stats.cancelled += len(self._queue)
            self._queue.clear()
            self._condition.notify_all()
        self.backend.release_all()

    def kill_switch(self) -> None:
        self.disarm()

    def mark_frame(self, captured_at_ns: int | None = None) -> None:
        with self._condition:
            self._last_frame_ns = self.now_ns() if captured_at_ns is None else captured_at_ns
            self._condition.notify_all()

    def schedule(self, target_ns: int, lane: int, action: str | int | None = None, kind: str = "press", note_id: int | None = None) -> int:
        if kind not in {"press", "release"}:
            raise ValueError("kind must be press or release")
        with self._condition:
            self._sequence += 1
            heapq.heappush(self._queue, ScheduledAction(target_ns, self._sequence, lane, action, kind, note_id))
            self.stats.scheduled += 1
            self._condition.notify_all()
            return self._sequence

    def _run(self) -> None:
        while True:
            with self._condition:
                if not self._running:
                    return
                if not self._armed or not self._queue:
                    self._condition.wait(timeout=0.05)
                    continue
                if self._last_frame_ns is not None and self.now_ns() - self._last_frame_ns > self.stale_timeout_ns:
                    self.stats.stale_disarms += 1
                    self._armed = False
                    self._queue.clear()
                    self.backend.release_all()
                    continue
                action = self._queue[0]
                wait_ns = action.target_ns - self.now_ns()
                if wait_ns > self.spin_window_ns:
                    self._condition.wait(timeout=(wait_ns - self.spin_window_ns) / 1_000_000_000)
                    continue
                heapq.heappop(self._queue)
            if action.target_ns > self.now_ns():
                while self.now_ns() < action.target_ns:
                    pass
            batch = [action]
            with self._condition:
                while self._queue and self._queue[0].target_ns == action.target_ns:
                    batch.append(heapq.heappop(self._queue))
            issued_ns = self.now_ns()
            send_actions = getattr(self.backend, "send_actions", None)
            if callable(send_actions) and len(batch) > 1:
                send_actions([(item.lane, item.action, item.kind) for item in batch])
            else:
                for item in batch:
                    if item.kind == "press":
                        self.backend.press(item.lane, item.action)
                    else:
                        self.backend.release(item.lane, item.action)
            self.stats.issued += len(batch)
            self.stats.timing_errors_ns.extend(issued_ns - item.target_ns for item in batch)
