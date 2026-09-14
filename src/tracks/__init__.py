"""Track data system for Marco Racing V2.

A :class:`~src.tracks.base.TrackDefinition` is pure data (control points, widths,
theme, difficulty ...).  :class:`src.track.Track` turns one into a fully built,
collidable, drawable circuit.  The registry exposes the 10 circuits in order.
"""

from .base import TrackDefinition, THEMES, build_centerline
from .registry import ALL_TRACKS, TRACK_IDS, get_track, track_index, first_track_id

__all__ = [
    "TrackDefinition", "THEMES", "build_centerline",
    "ALL_TRACKS", "TRACK_IDS", "get_track", "track_index", "first_track_id",
]
