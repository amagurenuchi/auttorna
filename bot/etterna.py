"""Best-effort integration with Etterna's root-level now-playing metadata."""

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class EtternaSelection:
    title: str
    artist: str
    group: str
    rate: float
    chart_path: Path | None
    source: Path


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeError):
        return ""


def _tag(text: str, name: str) -> str:
    match = re.search(rf"#{name}\s*:\s*(.*?);", text, re.I | re.S)
    return match.group(1).strip() if match else ""


def _chart_metadata(path: Path) -> tuple[str, str, str]:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return "", "", ""
    return _tag(text, "TITLE"), _tag(text, "ARTIST"), _tag(text, "SONG" if path.suffix.lower() == ".ssc" else "GROUP")


def _rate(root: Path, combined: str) -> float:
    value = _read(_find_file(root, "nowplaying_rate")) or _read(_find_file(root, "nowplaying_rate.txt"))
    matches = re.findall(r"(?:rate\s*[:=]\s*)?([0-9]+(?:\.[0-9]+)?)", value or combined, re.I)
    try:
        return float(matches[-1]) if matches else 1.0
    except ValueError:
        return 1.0


def find_selection(etterna_root: str | Path, *, chart_root: str | Path | None = None) -> EtternaSelection | None:
    """Read Etterna root-level now-playing files and match the song to a chart.

    Etterna exposes ``nowplaying.txt`` at its installation root. Optional
    separate ``nowplaying_title``, ``nowplaying_artist``, ``nowplaying_group``
    and ``nowplaying_rate`` files are read from that same root.
    """
    root = Path(etterna_root).expanduser()
    assets = root
    combined_path = _find_file(root, "nowplaying.txt")
    combined = _read(combined_path)
    title = _read(_find_file(assets, "nowplaying_title"))
    artist = _read(_find_file(assets, "nowplaying_artist"))
    group = _read(_find_file(assets, "nowplaying_group"))
    if combined and not (title and artist):
        # The documented combined format is theme-defined; use pipe, tab, or
        # common comma-separated layouts without making it a hard dependency.
        fields = [part.strip() for part in re.split(r"\||\t|\s+-\s+", combined) if part.strip()]
        title = title or (fields[0] if fields else "")
        artist = artist or (fields[1] if len(fields) > 1 else "")
        group = group or (fields[2] if len(fields) > 2 else "")
    if not title:
        return None
    search_root = Path(chart_root).expanduser() if chart_root else root / "Songs"
    chart_path = _find_chart(search_root, title, artist, group)
    return EtternaSelection(title, artist, group, _rate(assets, combined), chart_path, combined_path)


def _find_file(directory: Path, name: str) -> Path:
    exact = directory / name
    if exact.is_file():
        return exact
    wanted = name.casefold()
    try:
        return next((item for item in directory.iterdir() if item.name.casefold() == wanted), exact)
    except OSError:
        return exact


def _find_chart(root: Path, title: str, artist: str, group: str) -> Path | None:
    if not root.is_dir():
        return None
    wanted = {value.casefold().strip() for value in (title, artist) if value}
    for path in root.rglob("*"):
        if path.suffix.lower() not in {".sm", ".ssc"}:
            continue
        chart_title, chart_artist, _ = _chart_metadata(path)
        values = {value.casefold().strip() for value in (chart_title, chart_artist) if value}
        if title.casefold().strip() == chart_title.casefold().strip() and (not artist or artist.casefold().strip() == chart_artist.casefold().strip()):
            return path
        if wanted and wanted.issubset(values):
            return path
    return None


class EtternaWatcher:
    def __init__(self, root: str | Path, chart_root: str | Path | None = None) -> None:
        self.root, self.chart_root = root, chart_root
        self.last_source_mtime = 0.0
        self.last: EtternaSelection | None = None

    def poll(self) -> EtternaSelection | None:
        assets = Path(self.root)
        sources = [_find_file(assets, name) for name in ("nowplaying.txt", "nowplaying_title", "nowplaying_artist", "nowplaying_group", "nowplaying_rate")]
        try:
            mtime = max((source.stat().st_mtime for source in sources if source.exists()), default=0.0)
        except OSError:
            return self.last
        if mtime != self.last_source_mtime:
            self.last_source_mtime = mtime
            self.last = find_selection(self.root, chart_root=self.chart_root)
        return self.last
