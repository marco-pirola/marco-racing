"""The 10 Marco Racing circuits.

Every circuit is *designed*, not hand-plotted: it is written as a sequence of
straights and constant-radius corners and turned into a smooth, self-closing
racing line by :func:`src.tracks._geometry.build`.  This keeps each layout
readable, guarantees clean geometry (no pinched edges, no impossible kinks) and
lets the shapes be tuned by feel.

    S(n)          straight, n world units
    Sfree         straight whose length the builder solves so the loop closes
    L(a, r)       left corner  of a degrees, radius r
    R(a, r)       right corner of a degrees, radius r      (a is scaled so the
                  whole lap turns exactly 360 degrees)
"""

from __future__ import annotations

from ._geometry import build
from .base import TrackDefinition

S = lambda n: ("s", n)          # noqa: E731
Sfree = ("s", None)
L = lambda a, r: ("c", abs(a), r)      # noqa: E731  (left = positive)
R = lambda a, r: ("c", -abs(a), r)     # noqa: E731  (right = negative)


def _cp(start, heading, pieces, length=None):
    return build(start, heading, pieces, step=140.0, target_length=length)


# --------------------------------------------------------------------------- #
CITY_LOOP = TrackDefinition(
    id="city_loop", name="CITY LOOP", difficulty=1, theme="city",
    road_half=168.0, kerb_w=24.0, runoff_w=80.0, checkpoint_count=6,
    recommended_ai=("EASY", "EASY", "NORMAL"), ai_grip_bonus=0.15,
    blurb="A wide downtown loop: one enormous main straight, a long sweeping "
          "right, a lazy S through the centre and a fast curve back to the line.",
    control_points=_cp((900, 2820), 0, [
        Sfree, R(88, 660), S(560), R(70, 580), S(440),
        L(52, 520), S(280), R(52, 520), S(560), R(92, 660),
        Sfree, R(100, 600),
    ]),
)

INDUSTRIAL = TrackDefinition(
    id="industrial", name="INDUSTRIAL", difficulty=2, theme="industrial",
    road_half=150.0, kerb_w=22.0, runoff_w=52.0, checkpoint_count=7,
    recommended_ai=("EASY", "NORMAL", "NORMAL"),
    blurb="Boxy and angular: a long straight past the sheds, a run of near-square "
          "corners, a shallow chicane on the back straight and a tight last turn.",
    control_points=_cp((950, 640), 0, [
        Sfree, R(90, 320), S(1300), R(90, 320), S(560),
        L(52, 360), S(260), R(52, 360), S(560), R(90, 320),
        Sfree, R(90, 320),
    ]),
)

COASTAL = TrackDefinition(
    id="coastal", name="COASTAL", difficulty=2, theme="coastal",
    road_half=176.0, kerb_w=24.0, runoff_w=72.0, checkpoint_count=5,
    recommended_ai=("EASY", "NORMAL", "HARD"),
    blurb="Flowing seafront curves taken almost flat out, one enormous sweeper "
          "around the bay and a single hard corner back onto the promenade.",
    control_points=_cp((1500, 1150), 0, [
        Sfree, R(58, 920), S(560), R(56, 820), S(640),
        R(58, 920), S(560), R(56, 880), S(720), R(56, 720),
        Sfree, R(70, 560),
    ]),
)

MOUNTAIN = TrackDefinition(
    id="mountain", name="MOUNTAIN", difficulty=3, theme="mountain",
    road_half=136.0, kerb_w=18.0, runoff_w=46.0, checkpoint_count=8, smoothing=20,
    recommended_ai=("NORMAL", "NORMAL", "HARD"),
    blurb="A narrow mountain road: a climbing S linking a run of tight hairpin-"
          "grade corners with almost no run-off. Relentless rhythm changes.",
    control_points=_cp((1100, 2820), 0, [
        Sfree, R(46, 420), S(240), R(50, 360), S(220), R(64, 300),
        Sfree, L(48, 340), S(220), R(58, 320), S(240),
        R(64, 300), S(200), L(50, 320), S(200), R(64, 300), S(220),
        R(46, 380), S(200), R(48, 360),
    ], length=9600),
)

NIGHT_DISTRICT = TrackDefinition(
    id="night_district", name="NIGHT DISTRICT", difficulty=3, theme="night",
    road_half=138.0, kerb_w=20.0, runoff_w=44.0, checkpoint_count=7, smoothing=20,
    recommended_ai=("NORMAL", "NORMAL", "HARD"),
    blurb="Tight neon backstreets: short straights between close-packed corners "
          "and one 90-degree elbow that always arrives too soon.",
    control_points=_cp((1000, 1650), 0, [
        Sfree, R(84, 280), S(340), L(56, 270), S(280), R(70, 270), S(380),
        L(60, 290), S(260), R(74, 280), S(380), R(118, 240), S(320),
        L(56, 290), S(340), R(90, 270), Sfree, R(92, 290),
    ]),
)

DESERT_RUN = TrackDefinition(
    id="desert_run", name="DESERT RUN", difficulty=3, theme="desert",
    road_half=182.0, kerb_w=26.0, runoff_w=112.0, checkpoint_count=5,
    recommended_ai=("NORMAL", "HARD", "HARD"),
    blurb="A wide-open desert highway: colossal straights, two flat-out sweepers "
          "and a single hard corner that snaps the rhythm.",
    control_points=_cp((1500, 2860), 0, [
        Sfree, R(72, 880), S(1100), R(64, 760), S(560),
        L(52, 640), S(260), R(52, 640), S(1100), R(90, 860),
        Sfree, R(100, 800),
    ]),
)

TECH_CIRCUIT = TrackDefinition(
    id="tech_circuit", name="TECH CIRCUIT", difficulty=4, theme="tech",
    road_half=138.0, kerb_w=20.0, runoff_w=48.0, checkpoint_count=8, smoothing=20,
    recommended_ai=("NORMAL", "HARD", "HARD"),
    blurb="A driving-school special: a real chicane, a double direction change, "
          "an esse and a hard stop before the pit straight.",
    control_points=_cp((1500, 1300), 0, [
        Sfree, L(56, 300), S(140), R(56, 300), S(140), L(54, 300),
        R(80, 300), S(160), R(80, 280),
        Sfree, R(40, 340), S(160), L(46, 320), S(150), R(56, 300), S(160),
        L(50, 320), S(140), R(58, 320), S(160),
        R(64, 300), S(180), R(58, 320),
    ], length=9200),
)

GRAND_PRIX = TrackDefinition(
    id="grand_prix", name="GRAND PRIX", difficulty=4, theme="grandprix",
    road_half=158.0, kerb_w=24.0, runoff_w=56.0, checkpoint_count=8, smoothing=20,
    recommended_ai=("NORMAL", "HARD", "ELITE"),
    blurb="A full grand-prix lap: a long pit straight into a fast Turn 1 complex, "
          "a slow hairpin, a technical middle sector and a flat kink onto the line.",
    control_points=_cp((1600, 2820), 0, [
        Sfree, R(78, 560), S(240), R(40, 560), R(52, 480),
        Sfree, R(38, 480), S(200), L(44, 460), S(180), R(44, 460),
        R(78, 320), S(160), R(78, 320),
        L(44, 460), S(220), R(44, 460), S(200), R(56, 500),
    ], length=12800),
)

STORM = TrackDefinition(
    id="storm", name="STORM", difficulty=5, theme="storm",
    road_half=134.0, kerb_w=18.0, runoff_w=40.0, checkpoint_count=9, smoothing=20,
    recommended_ai=("HARD", "HARD", "ELITE"),
    blurb="Brutal. Flat-out bursts wired straight into hard corners - blind "
          "entries, jagged rhythm, zero margin.",
    control_points=_cp((1600, 1500), 0, [
        Sfree, R(46, 280), S(180), L(52, 260), S(180), R(66, 240),
        R(40, 280), S(160), L(48, 250), S(160), R(66, 240), S(160),
        Sfree, L(46, 250), S(160), R(66, 240), S(160), L(50, 250), S(160), R(64, 240),
        S(160), R(46, 300),
    ], length=12400),
)

MARCO_GP = TrackDefinition(
    id="marco_gp", name="MARCO GP", difficulty=5, theme="flagship",
    road_half=158.0, kerb_w=26.0, runoff_w=58.0, checkpoint_count=9, smoothing=20,
    recommended_ai=("HARD", "ELITE", "ELITE"),
    blurb="The flagship. A spectacular main straight, a huge high-speed Turn 1, "
          "a technical middle sector, a slow hairpin and a flowing final sector "
          "that decides the race.",
    control_points=_cp((1700, 2900), 0, [
        Sfree, R(58, 520), S(180), R(34, 480), R(42, 460),
        Sfree, R(32, 460), S(180), L(46, 440), S(150), R(46, 440),
        R(74, 320), S(150), R(74, 320),
        L(44, 440), S(200), R(50, 420), S(170), L(44, 420), S(150), R(54, 460),
    ], length=13600),
)


ALL = [
    CITY_LOOP, INDUSTRIAL, COASTAL, MOUNTAIN, NIGHT_DISTRICT,
    DESERT_RUN, TECH_CIRCUIT, GRAND_PRIX, STORM, MARCO_GP,
]
