"""Ordered registry of every circuit."""

from __future__ import annotations

from .base import TrackDefinition
from .library import ALL

ALL_TRACKS: list[TrackDefinition] = list(ALL)
TRACK_IDS: list[str] = [t.id for t in ALL_TRACKS]
_BY_ID = {t.id: t for t in ALL_TRACKS}

assert len(ALL_TRACKS) == 10, "Marco Racing ships with exactly 10 circuits"
assert len(_BY_ID) == 10, "duplicate track id in the library"


def get_track(track_id: str) -> TrackDefinition:
    """Return the definition for ``track_id`` (falls back to the first circuit)."""
    return _BY_ID.get(track_id, ALL_TRACKS[0])


def track_index(track_id: str) -> int:
    try:
        return TRACK_IDS.index(track_id)
    except ValueError:
        return 0


def first_track_id() -> str:
    return TRACK_IDS[0]


def next_track_id(track_id: str) -> str | None:
    i = track_index(track_id)
    return TRACK_IDS[i + 1] if i + 1 < len(TRACK_IDS) else None
