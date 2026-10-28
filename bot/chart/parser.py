"""Small dependency-free parser for the note data used by StepMania charts."""

from pathlib import Path
import re
import logging

from bot.model import NoteEvent
from bot.chart.schedule import Schedule
from bot.chart.timing import TimingMap

logger = logging.getLogger(__name__)


def _tags(text: str) -> dict[str, str]:
    return {key.upper(): value.strip() for key, value in re.findall(r"#([^:;]+):([^;]*);", text, re.S)}


def _blocks(text: str, key: str) -> list[str]:
    return re.findall(rf"#{key}\s*:(.*?)(?=\n#|\Z)", text, re.I | re.S)


def _selected_notes(text: str, step_type: str | None, difficulty: str | None) -> str:
    positions = list(re.finditer(r"#NOTES\s*:", text, re.I))
    for position in positions:
        start = position.end()
        end_match = re.search(r";", text[start:])
        if not end_match:
            continue
        block = text[start:start + end_match.start()]
        fields = _tags(block)
        sm_fields = block.split(":", 5)
        if len(sm_fields) >= 6:
            fields = {"STEPSTYPE": sm_fields[0].strip(), "DIFFICULTY": sm_fields[2].strip()}
        if "STEPSTYPE" not in fields:
            metadata_start = text.rfind("#NOTEDATA", 0, position.start())
            metadata = text[metadata_start:position.start()] if metadata_start >= 0 else text[:position.start()]
            fields = {**_tags(metadata), **fields}
        if step_type and fields.get("STEPSTYPE", "").lower() != step_type.lower():
            continue
        if difficulty and fields.get("DIFFICULTY", "").lower() != difficulty.lower():
            continue
        return block
    raise ValueError("no chart matched the requested step type and difficulty")


def _notes_data(block: str) -> str:
    parts = block.split(":", 5)
    return parts[5] if len(parts) >= 6 else block


def _measure_rows(data: str) -> list[tuple[float, str]]:
    rows: list[tuple[float, str]] = []
    for measure_index, measure in enumerate(data.strip().split(",")):
        lines = [line.strip() for line in measure.splitlines() if line.strip()]
        count = len(lines)
        if not count:
            continue
        for index, line in enumerate(lines):
            rows.append((measure_index * 4.0 + index * 4.0 / count, line))
    return rows


def parse_chart(path: str | Path, *, step_type: str | None = None, difficulty: str | None = None) -> Schedule:
    """Parse taps, holds, rolls, and mines from a selected .sm/.ssc chart."""
    suffix = Path(path).suffix.lower()
    if suffix not in {".sm", ".ssc"}:
        raise ValueError(f"unsupported chart format: {suffix or '<none>'}")
    text = Path(path).read_text(encoding="utf-8-sig")
    global_tags = _tags(text)
    block = _selected_notes(text, step_type, difficulty)
    fields = _tags(block)
    data = _notes_data(block).split(";")[-1]
    timing = TimingMap.from_tags(global_tags.get("BPMS", ""), offset=float(global_tags.get("OFFSET", "0") or 0),
                                 stops=global_tags.get("STOPS", ""), delays=global_tags.get("DELAYS", ""),
                                 warps=global_tags.get("WARPS", ""))
    del fields
    events: list[NoteEvent] = []
    active: dict[int, tuple[float, str]] = {}
    for beat, row in _measure_rows(data):
        if timing.is_warped(beat):
            continue
        for col, note in enumerate(row):
            if note in {"1", "M", "m"}:
                kind = "mine" if note.lower() == "m" else "tap"
                events.append(NoteEvent(timing.beat_to_seconds(beat), col, kind))
            elif note in {"2", "4"}:
                active[col] = (beat, "roll_start" if note == "4" else "hold_start")
                events.append(NoteEvent(timing.beat_to_seconds(beat), col, active[col][1]))
            elif note == "3" and col in active:
                events.append(NoteEvent(timing.beat_to_seconds(beat), col, "roll_end" if active[col][1] == "roll_start" else "hold_end"))
                del active[col]
    schedule = Schedule(tuple(sorted(events, key=lambda event: (event.t, event.col, event.kind))))
    logger.info("parsed chart=%s step_type=%s difficulty=%s events=%d duration=%.3fs", path, step_type or "any", difficulty or "any", len(schedule.events), schedule.events[-1].t if schedule.events else 0.0)
    for event in schedule.events:
        logger.debug("note t=%.6f col=%d kind=%s", event.t, event.col, event.kind)
    return schedule
