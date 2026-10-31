"""Match falling tracked notes to chart events for clock observations."""

from dataclasses import dataclass

from bot.model import Detection, NoteEvent


@dataclass(frozen=True)
class ClockSample:
    wall_t: float
    song_t: float
    residual: float
    event: NoteEvent


@dataclass(frozen=True)
class ArrowObservation:
    """A visual lane crossing, before assigning it a chart timestamp."""

    wall_t: float
    col: int


@dataclass(frozen=True)
class SequenceAlignment:
    offset: float
    observations: tuple[ArrowObservation, ...]
    events: tuple[NoteEvent, ...]
    residual: float


def align_observations(observations: list[ArrowObservation], events: list[NoteEvent], *,
                       tolerance_s: float = 0.08, minimum: int = 4) -> SequenceAlignment | None:
    """Find the chart subsequence matching lane crossings at one global offset.

    This deliberately does not use the current clock.  Every possible chart
    event matching the first observed lane proposes an offset, and the best
    monotonic sequence wins.  Thus a bad provisional timestamp cannot feed
    back into its own correction.
    """
    if len(observations) < minimum or not events:
        return None
    observations = sorted(observations, key=lambda item: item.wall_t)
    best: SequenceAlignment | None = None
    for first_index, first_event in enumerate(events):
        if first_event.col != observations[0].col:
            continue
        offset = observations[0].wall_t - first_event.t
        matched_events = [first_event]
        matched_observations = [observations[0]]
        event_index = first_index
        for observation in observations[1:]:
            candidates = [
                (index, event) for index, event in enumerate(events[event_index + 1:], event_index + 1)
                if event.col == observation.col
                and abs((observation.wall_t - event.t) - offset) <= tolerance_s
            ]
            if not candidates:
                continue
            event_index, event = min(candidates, key=lambda item: abs((observation.wall_t - item[1].t) - offset))
            matched_events.append(event)
            matched_observations.append(observation)
        if len(matched_events) < minimum:
            continue
        residual = sum(abs((observation.wall_t - event.t) - offset)
                       for observation, event in zip(matched_observations, matched_events)) / len(matched_events)
        candidate = SequenceAlignment(offset, tuple(matched_observations), tuple(matched_events), residual)
        if best is None or (len(candidate.events), -candidate.residual) > (len(best.events), -best.residual):
            best = candidate
    return best


def match_detection(detection: Detection, events: list[NoteEvent], receptor_y: float,
                    speed_px_s: float, *, window_s: float = 0.1,
                    wall_to_song=None, arrival_t: float | None = None,
                    used_events: set[tuple[float, int, str]] | None = None,
                    min_song_t: float = float("-inf")) -> ClockSample | None:
    if speed_px_s <= 0:
        return None
    # The chart owns the exact song timestamp.  Vision only estimates the
    # wall-clock crossing time; callers may provide a multi-frame trajectory
    # estimate instead of relying on one noisy detection.
    arrival = arrival_t if arrival_t is not None else detection.t_frame + (receptor_y - detection.y) / speed_px_s
    predicted_song = wall_to_song(arrival) if wall_to_song is not None else arrival
    candidates = [event for event in events
                  if event.col == detection.col
                  and event.t >= min_song_t
                  and (used_events is None or (event.t, event.col, event.kind) not in used_events)
                  and abs(event.t - predicted_song) <= window_s]
    if not candidates:
        return None
    event = min(candidates, key=lambda item: abs(item.t - predicted_song))
    return ClockSample(arrival, event.t, arrival - event.t, event)
