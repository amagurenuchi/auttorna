"""Match falling tracked notes to chart events for clock observations."""

from dataclasses import dataclass

from bot.model import Detection, NoteEvent


@dataclass(frozen=True)
class ClockSample:
    wall_t: float
    song_t: float
    residual: float
    event: NoteEvent


def match_detection(detection: Detection, events: list[NoteEvent], receptor_y: float,
                    speed_px_s: float, *, window_s: float = 0.1,
                    wall_to_song=None) -> ClockSample | None:
    if speed_px_s <= 0:
        return None
    arrival = detection.t_frame + (receptor_y - detection.y) / speed_px_s
    predicted_song = wall_to_song(arrival) if wall_to_song is not None else arrival
    candidates = [event for event in events if event.col == detection.col and abs(event.t - predicted_song) <= window_s]
    if not candidates:
        return None
    event = min(candidates, key=lambda item: abs(item.t - arrival))
    return ClockSample(arrival, event.t, arrival - event.t, event)
