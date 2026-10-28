"""Stable data contracts shared by chart, vision, sync, and input layers."""

from dataclasses import dataclass
from typing import Literal

NoteKind = Literal["tap", "hold_start", "hold_end", "roll_start", "roll_end", "mine"]


@dataclass(frozen=True)
class NoteEvent:
    """A scheduled chart event on the song clock."""

    t: float
    col: int
    kind: NoteKind


@dataclass(frozen=True)
class Detection:
    """A detector output in the cropped ROI coordinate space."""

    t_frame: float
    col: int
    y: float
    cls: str
    conf: float
