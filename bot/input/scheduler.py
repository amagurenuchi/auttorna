"""Threaded, injectable input scheduler with hybrid waiting."""

from collections.abc import Callable, Iterable
import heapq
import logging
import threading
import time

from bot.model import NoteEvent

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, song_to_wall: Callable[[float], float], emit: Callable[[int, bool], None] | None = None,
                 latency_s: float = 0.0) -> None:
        self.song_to_wall = song_to_wall
        self.emit = emit or (lambda col, down: None)
        self.latency_s = latency_s
        self.events: list[NoteEvent] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def replace(self, events: Iterable[NoteEvent]) -> None:
        self.events = sorted(events, key=lambda event: event.t)
        logger.info("input schedule loaded: %d events", len(self.events))

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="input-scheduler", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        logger.info("input scheduler started")
        for event in self.events:
            if self._stop.is_set() or event.kind == "mine":
                continue
            target = self.song_to_wall(event.t) - self.latency_s
            while not self._stop.is_set():
                remaining = target - time.perf_counter()
                if remaining <= 0:
                    break
                if remaining > 0.002:
                    time.sleep(remaining - 0.001)
            if self._stop.is_set():
                break
            logger.debug("input event due: song_t=%.6f col=%d kind=%s", event.t, event.col, event.kind)
            if event.kind in {"tap", "hold_start", "roll_start"}:
                self.emit(event.col, True)
            if event.kind == "tap":
                self.emit(event.col, False)
            elif event.kind in {"hold_end", "roll_end"}:
                self.emit(event.col, False)
        self._release_all()
        logger.info("input scheduler finished")

    def _release_all(self) -> None:
        for col in range(16):
            self.emit(col, False)

    def stop(self) -> None:
        logger.info("input scheduler stopping")
        self._stop.set()
        self.events.clear()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)
        self._release_all()
