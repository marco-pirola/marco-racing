"""Track definition data + visual themes.

No pygame surfaces are created here - only plain data and light geometry, so
this module is cheap to import and easy to test.

A circuit is fully described by:

  * ``control_points``  - the hand-authored racing line (Catmull-Rom smoothed)
  * four cross-section widths, from the centre line outwards:

        road_half  |  kerb_w  |  runoff_w  |
       -----------+---------+-----------+----------------
        asphalt   |  kerb   |  run-off   |  barrier (wall_half)

    ``wall_half = road_half + kerb_w + runoff_w`` is BOTH the visible barrier
    position and the collision boundary - there is only one number.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..utils import smooth_closed_loop


# --------------------------------------------------------------------------- #
#  Visual themes - one per circuit, each with its own identity
# --------------------------------------------------------------------------- #
#   ground / ground_dark : the far background
#   asphalt / asphalt_dark
#   kerb_a / kerb_b       : the two alternating kerb colours (corners only)
#   runoff               : the run-off band between kerb and barrier
#   runoff_kind          : "grass"|"gravel"|"sand"|"concrete"|"water" (dust fx)
#   barrier              : the solid wall colour (drawn at wall_half)
#   line                 : painted edge / centre line colour
#   ambient              : optional RGBA wash over the world (mood)
#   decor                : tuple of decoration kinds placed OUTSIDE the barrier
THEMES = {
    "city": {
        "ground": (78, 82, 92), "ground_dark": (68, 72, 82),
        "asphalt": (58, 60, 68), "asphalt_dark": (50, 52, 60),
        "kerb_a": (208, 58, 58), "kerb_b": (238, 238, 242),
        "runoff": (120, 124, 134), "runoff_kind": "concrete",
        "barrier": (176, 180, 190), "line": (226, 226, 230),
        "ambient": None, "decor": ("building", "building", "billboard", "light"),
    },
    "industrial": {
        "ground": (92, 88, 80), "ground_dark": (82, 78, 70),
        "asphalt": (62, 62, 66), "asphalt_dark": (54, 54, 58),
        "kerb_a": (226, 150, 40), "kerb_b": (40, 42, 48),
        "runoff": (110, 106, 98), "runoff_kind": "concrete",
        "barrier": (150, 146, 136), "line": (232, 210, 140),
        "ambient": (60, 50, 30, 14), "decor": ("warehouse", "container", "container", "tank"),
    },
    "coastal": {
        "ground": (66, 154, 196), "ground_dark": (56, 138, 180),
        "asphalt": (66, 68, 74), "asphalt_dark": (58, 60, 66),
        "kerb_a": (212, 72, 72), "kerb_b": (242, 242, 246),
        "runoff": (228, 212, 162), "runoff_kind": "sand",
        "barrier": (238, 240, 244), "line": (236, 236, 240),
        "ambient": (70, 170, 205, 16), "decor": ("water", "water", "rock", "palm"),
    },
    "mountain": {
        "ground": (72, 122, 66), "ground_dark": (60, 106, 56),
        "asphalt": (60, 60, 64), "asphalt_dark": (52, 52, 56),
        "kerb_a": (202, 60, 60), "kerb_b": (234, 234, 238),
        "runoff": (124, 114, 98), "runoff_kind": "gravel",
        "barrier": (120, 112, 100), "line": (226, 226, 230),
        "ambient": (40, 60, 40, 12), "decor": ("tree", "tree", "rock", "rock"),
    },
    "night": {
        "ground": (24, 26, 38), "ground_dark": (20, 22, 32),
        "asphalt": (40, 42, 52), "asphalt_dark": (34, 36, 46),
        "kerb_a": (0, 214, 200), "kerb_b": (244, 62, 152),
        "runoff": (46, 48, 62), "runoff_kind": "concrete",
        "barrier": (82, 86, 112), "line": (130, 244, 255),
        "ambient": (18, 18, 58, 66), "decor": ("building", "light", "light", "neon"),
    },
    "desert": {
        "ground": (224, 192, 132), "ground_dark": (210, 176, 118),
        "asphalt": (66, 64, 62), "asphalt_dark": (58, 56, 54),
        "kerb_a": (212, 82, 60), "kerb_b": (242, 234, 222),
        "runoff": (232, 202, 150), "runoff_kind": "sand",
        "barrier": (188, 158, 116), "line": (238, 226, 202),
        "ambient": (255, 200, 120, 18), "decor": ("dune", "dune", "rock", "rock"),
    },
    "tech": {
        "ground": (60, 130, 64), "ground_dark": (50, 114, 56),
        "asphalt": (56, 58, 66), "asphalt_dark": (48, 50, 58),
        "kerb_a": (60, 92, 232), "kerb_b": (242, 242, 246),
        "runoff": (150, 152, 160), "runoff_kind": "concrete",
        "barrier": (186, 188, 198), "line": (222, 226, 238),
        "ambient": None, "decor": ("stand", "stand", "billboard", "tree"),
    },
    "storm": {
        "ground": (42, 48, 58), "ground_dark": (34, 40, 50),
        "asphalt": (46, 46, 54), "asphalt_dark": (38, 38, 46),
        "kerb_a": (150, 44, 204), "kerb_b": (232, 232, 238),
        "runoff": (70, 66, 78), "runoff_kind": "gravel",
        "barrier": (104, 98, 118), "line": (204, 184, 244),
        "ambient": (28, 20, 52, 58), "decor": ("rock", "rock", "tree", "pylon"),
    },
    "grandprix": {
        "ground": (62, 134, 66), "ground_dark": (52, 118, 58),
        "asphalt": (60, 62, 70), "asphalt_dark": (52, 54, 62),
        "kerb_a": (212, 60, 60), "kerb_b": (240, 240, 244),
        "runoff": (150, 152, 160), "runoff_kind": "gravel",
        "barrier": (200, 202, 210), "line": (228, 228, 232),
        "ambient": None, "decor": ("stand", "stand", "tree", "billboard"),
    },
    "flagship": {
        "ground": (50, 122, 60), "ground_dark": (42, 106, 54),
        "asphalt": (58, 60, 70), "asphalt_dark": (48, 50, 60),
        "kerb_a": (255, 190, 64), "kerb_b": (36, 38, 48),
        "runoff": (150, 152, 162), "runoff_kind": "concrete",
        "barrier": (214, 216, 224), "line": (255, 214, 140),
        "ambient": (255, 200, 90, 10), "decor": ("stand", "light", "billboard", "stand"),
    },
}


def theme(name: str) -> dict:
    return THEMES.get(name, THEMES["city"])


# --------------------------------------------------------------------------- #
@dataclass
class TrackDefinition:
    id: str
    name: str
    difficulty: int                       # 1..5 (stars)
    control_points: list                  # list[(x, y)]  hand-authored
    road_half: float = 165.0
    kerb_w: float = 26.0                  # kerb band, just outside the asphalt
    runoff_w: float = 60.0               # run-off band, kerb -> barrier
    checkpoint_count: int = 6
    theme: str = "city"
    laps: int = 3
    smoothing: int = 18                  # spline samples per control segment
    ai_grip_bonus: float = 0.0
    recommended_ai: tuple = ("EASY", "NORMAL", "HARD")
    blurb: str = ""

    @property
    def wall_half(self) -> float:
        return self.road_half + self.kerb_w + self.runoff_w

    @property
    def stars(self) -> str:
        return "★" * self.difficulty + "☆" * (5 - self.difficulty)

    def centerline(self):
        return build_centerline(self)

    def approx_length(self) -> float:
        pts = self.centerline()
        return sum((pts[i] - pts[(i + 1) % len(pts)]).length() for i in range(len(pts)))


def build_centerline(definition: "TrackDefinition"):
    """The single source of truth for a circuit's smooth centre line."""
    return smooth_closed_loop(definition.control_points, definition.smoothing)
