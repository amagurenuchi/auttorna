"""Immutable note schedule operations shared by controller and simulator."""

from dataclasses import dataclass

from bot.model import NoteEvent


@dataclass(frozen=True)
class Schedule:
    events: tuple[NoteEvent, ...]

    def scaled(self, rate: float) -> "Schedule":
        if rate <= 0:
            raise ValueError("rate must be positive")
        return Schedule(tuple(NoteEvent(e.t / rate, e.col, e.kind) for e in self.events))
