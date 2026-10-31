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
        self._wake = threading.Event()
        self._events_lock = threading.Lock()
        self._revision = 0
        self._thread: threading.Thread | None = None

    def replace(self, events: Iterable[NoteEvent]) -> None:
        replacement = sorted(events, key=lambda event: event.t)
        with self._events_lock:
            self.events = replacement
            self._revision += 1
        self._wake.set()
        logger.info("input schedule loaded: %d events", len(replacement))

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._wake.clear()
        self._thread = threading.Thread(target=self._run, name="input-scheduler", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        logger.info("input scheduler started")
        index = 0
        revision = -1
        while not self._stop.is_set():
            if self._stop.is_set():
                break
            with self._events_lock:
                current_revision = self._revision
                events = self.events[:]
            if current_revision != revision:
                revision = current_revision
                index = 0
                continue
            if index >= len(events):
                break
            first = events[index]
            index += 1
            group = [first]
            while index < len(events) and events[index].t == first.t:
                group.append(events[index])
                index += 1
            playable = [event for event in group if event.kind != "mine"]
            if not playable:
                continue
            target = self.song_to_wall(first.t) - self.latency_s
            while not self._stop.is_set():
                with self._events_lock:
                    replaced = self._revision != revision
                if replaced:
                    break
                remaining = target - time.perf_counter()
                if remaining <= 0:
                    break
                if remaining > 0.002:
                    self._wake.wait(min(remaining - 0.001, 0.05))
                    self._wake.clear()
            with self._events_lock:
                if self._revision != revision:
                    continue
            if self._stop.is_set():
                break
            logger.debug("input chord due: song_t=%.6f events=%d", first.t, len(playable))
            # Press every lane in the chord before releasing any tap. This
            # preserves simultaneous notes even when the emitter is sequential.
            for event in playable:
                if event.kind in {"tap", "hold_start", "roll_start"}:
                    self.emit(event.col, True)
            for event in playable:
                if event.kind == "tap" or event.kind in {"hold_end", "roll_end"}:
                    self.emit(event.col, False)
        self._release_all()
        logger.info("input scheduler finished")

    def _release_all(self) -> None:
        for col in range(16):
            self.emit(col, False)

    def stop(self) -> None:
        logger.info("input scheduler stopping")
        self._stop.set()
        self._wake.set()
        with self._events_lock:
            self.events.clear()
            self._revision += 1
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)
        self._release_all()
