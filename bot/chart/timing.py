"""StepMania beat-to-song-time conversion, including stops and warps."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TimingPoint:
    beat: float
    seconds: float
    bpm: float


@dataclass(frozen=True)
class TimingSegment:
    start_beat: float
    end_beat: float
    start_seconds: float
    bpm: float


class TimingMap:
    """Piecewise BPM map with non-scoring stop/delay and warp events."""

    def __init__(self, points: tuple[TimingPoint, ...] = (), *, offset: float = 0.0,
                 stops: tuple[tuple[float, float], ...] = (),
                 delays: tuple[tuple[float, float], ...] = (),
                 warps: tuple[tuple[float, float], ...] = ()) -> None:
        self.points = points
        self.offset = offset
        self.stops = tuple(sorted(stops))
        self.delays = tuple(sorted(delays))
        self.warps = tuple(sorted(warps))

    @classmethod
    def from_tags(cls, bpms: str, *, offset: float = 0.0, stops: str = "",
                  delays: str = "", warps: str = "") -> "TimingMap":
        def pairs(value: str) -> tuple[tuple[float, float], ...]:
            result = []
            for item in value.split(","):
                if not item.strip() or "=" not in item:
                    continue
                beat, amount = item.split("=", 1)
                result.append((float(beat), float(amount)))
            return tuple(sorted(result))

        raw = pairs(bpms)
        if not raw or any(bpm <= 0 for _, bpm in raw):
            raise ValueError("chart must contain positive #BPMS")
        points: list[TimingPoint] = []
        seconds = 0.0
        previous_beat, previous_bpm = raw[0]
        points.append(TimingPoint(previous_beat, seconds, previous_bpm))
        for beat, bpm in raw[1:]:
            seconds += max(0.0, beat - previous_beat) * 60.0 / previous_bpm
            points.append(TimingPoint(beat, seconds, bpm))
            previous_beat, previous_bpm = beat, bpm
        return cls(tuple(points), offset=offset, stops=pairs(stops), delays=pairs(delays), warps=pairs(warps))

    def beat_to_seconds(self, beat: float) -> float:
        if not self.points:
            raise ValueError("timing map has no BPM points")
        point = self.points[0]
        for candidate in self.points:
            if candidate.beat <= beat:
                point = candidate
            else:
                break
        value = point.seconds + (beat - point.beat) * 60.0 / point.bpm - self.offset
        value += sum(amount for at, amount in self.stops + self.delays if at <= beat)
        return value

    def is_warped(self, beat: float) -> bool:
        return any(start <= beat < start + length for start, length in self.warps if length > 0)
