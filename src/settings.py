"""Global configuration: constants, colour palette and car definitions.

Nothing in here touches pygame so it is safe to import from anywhere.
User-tweakable options live in :class:`save_data.Settings`; this module only
holds values that are fixed for a given build of the game.
"""

from __future__ import annotations

import os

# --------------------------------------------------------------------------- #
#  Paths
# --------------------------------------------------------------------------- #
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
IMAGES_DIR = os.path.join(ASSETS_DIR, "images")
SOUNDS_DIR = os.path.join(ASSETS_DIR, "sounds")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
DATA_DIR = os.path.join(ROOT_DIR, "data")
SAVE_PATH = os.path.join(DATA_DIR, "save.json")

# --------------------------------------------------------------------------- #
#  Display
# --------------------------------------------------------------------------- #
GAME_TITLE = "Marco Racing"
BASE_WIDTH = 1280
BASE_HEIGHT = 720
MIN_WIDTH = 800
MIN_HEIGHT = 480
TARGET_FPS = 120          # simulation is frame-rate independent; this just caps it
FIXED_DT = 1.0 / 120.0    # physics sub-step size
MAX_FRAME_TIME = 0.25     # clamp huge stalls (alt-tab, breakpoints, ...)

# --------------------------------------------------------------------------- #
#  Race rules
# --------------------------------------------------------------------------- #
TOTAL_LAPS = 3
AI_COUNT = 3
COUNTDOWN_TIME = 3.0      # seconds of "3 - 2 - 1"
GO_TIME = 0.9            # seconds the "GO!" banner stays up

# Multiply an internal world-units/second speed by this to get the HUD km/h.
KMH_FACTOR = 0.33

# --------------------------------------------------------------------------- #
#  Colour palette  (kept deliberately small and consistent)
# --------------------------------------------------------------------------- #
COL_GRASS = (56, 122, 60)
COL_GRASS_DARK = (46, 104, 52)
COL_GRASS_EDGE = (38, 88, 44)
COL_ASPHALT = (60, 62, 70)
COL_ASPHALT_DARK = (52, 54, 62)
COL_ASPHALT_LINE = (222, 222, 226)
COL_CURB_A = (206, 58, 58)
COL_CURB_B = (238, 238, 240)
COL_START = (245, 245, 245)

COL_BG = (16, 18, 26)
COL_BG_2 = (24, 27, 38)
COL_PANEL = (32, 36, 50)
COL_PANEL_LIGHT = (44, 49, 66)
COL_ACCENT = (255, 190, 64)      # amber
COL_ACCENT_2 = (90, 205, 255)    # cyan
COL_GOOD = (110, 220, 130)
COL_BAD = (240, 96, 96)
COL_TEXT = (236, 239, 246)
COL_TEXT_DIM = (150, 158, 176)
COL_SHADOW = (0, 0, 0)

COL_NITRO = (95, 205, 255)
COL_NITRO_EMPTY = (60, 66, 84)

# --------------------------------------------------------------------------- #
#  Cars
# --------------------------------------------------------------------------- #
# Physics fields are in world units and feed straight into physics.simulate.
# `stats` are 0..1 values used to draw the bars in the Garage screen.
#   nitro_mult : scales how strong the nitro boost is for this car
#   offroad    : lateral-grip multiplier off the tarmac (rally cars > 1)
#   silhouette : which procedural body shape to draw
#   unlock_wins: career wins required before the car is available
CARS: dict[str, dict] = {
    "MARCO GT": {
        "name": "MARCO GT",
        "category": "BALANCED",
        "tagline": "The all-rounder. Does everything well, nothing badly.",
        "color": (222, 66, 62),
        "accent": (255, 214, 120),
        "silhouette": "standard",
        "engine_power": 560.0, "max_speed": 640.0, "brake_power": 720.0,
        "reverse_speed": 210.0, "grip": 6.4, "drift_grip": 1.5,
        "drag": 0.00090, "steer_rate": 168.0,
        "nitro_mult": 1.0, "offroad": 1.0, "unlock_wins": 0,
        "stats": {"top_speed": 0.66, "acceleration": 0.64, "handling": 0.70,
                  "grip": 0.70, "nitro": 0.60},
    },
    "MARCO SPORT": {
        "name": "MARCO SPORT",
        "category": "HIGH SPEED",
        "tagline": "Serious top end, but it will bite if you are careless.",
        "color": (70, 120, 240),
        "accent": (150, 200, 255),
        "silhouette": "sport",
        "engine_power": 640.0, "max_speed": 730.0, "brake_power": 690.0,
        "reverse_speed": 220.0, "grip": 5.3, "drift_grip": 1.25,
        "drag": 0.00080, "steer_rate": 176.0,
        "nitro_mult": 1.1, "offroad": 0.9, "unlock_wins": 1,
        "stats": {"top_speed": 0.90, "acceleration": 0.80, "handling": 0.58,
                  "grip": 0.52, "nitro": 0.70},
    },
    "MARCO GRIP": {
        "name": "MARCO GRIP",
        "category": "HIGH HANDLING",
        "tagline": "Slower in a straight line, glued to the road everywhere else.",
        "color": (86, 196, 128),
        "accent": (190, 255, 210),
        "silhouette": "grip",
        "engine_power": 520.0, "max_speed": 590.0, "brake_power": 780.0,
        "reverse_speed": 200.0, "grip": 7.8, "drift_grip": 1.9,
        "drag": 0.00100, "steer_rate": 158.0,
        "nitro_mult": 0.9, "offroad": 1.05, "unlock_wins": 3,
        "stats": {"top_speed": 0.56, "acceleration": 0.58, "handling": 0.84,
                  "grip": 0.92, "nitro": 0.50},
    },
    "MARCO TURBO": {
        "name": "MARCO TURBO",
        "category": "BOOST",
        "tagline": "Vicious acceleration and a monster nitro. Handling is an afterthought.",
        "color": (255, 150, 40),
        "accent": (255, 226, 150),
        "silhouette": "turbo",
        "engine_power": 665.0, "max_speed": 720.0, "brake_power": 700.0,
        "reverse_speed": 220.0, "grip": 5.6, "drift_grip": 1.35,
        "drag": 0.00082, "steer_rate": 172.0,
        "nitro_mult": 1.45, "offroad": 0.9, "unlock_wins": 5,
        "stats": {"top_speed": 0.86, "acceleration": 0.94, "handling": 0.58,
                  "grip": 0.56, "nitro": 0.98},
    },
    "MARCO RALLY": {
        "name": "MARCO RALLY",
        "category": "ALL-SURFACE",
        "tagline": "Unshakeable. Keeps its grip on the grass and the gravel where others spin.",
        "color": (150, 92, 210),
        "accent": (216, 190, 250),
        "silhouette": "rally",
        "engine_power": 548.0, "max_speed": 606.0, "brake_power": 760.0,
        "reverse_speed": 210.0, "grip": 7.3, "drift_grip": 1.8,
        "drag": 0.00097, "steer_rate": 163.0,
        "nitro_mult": 1.0, "offroad": 1.65, "unlock_wins": 8,
        "stats": {"top_speed": 0.60, "acceleration": 0.66, "handling": 0.80,
                  "grip": 0.86, "nitro": 0.60},
    },
}
CAR_ORDER = ["MARCO GT", "MARCO SPORT", "MARCO GRIP", "MARCO TURBO", "MARCO RALLY"]
DEFAULT_CAR = "MARCO GT"

# career wins needed to unlock each car
CAR_UNLOCKS = {k: v["unlock_wins"] for k, v in CARS.items()}

# progression toggles (flip to True to open everything, e.g. for testing)
UNLOCK_ALL_CARS = False
UNLOCK_ALL_TRACKS = False

# AI opponent colours (distinct from every player car)
AI_COLORS = [
    (250, 176, 64),
    (180, 96, 220),
    (240, 240, 240),
    (96, 224, 224),
    (232, 104, 160),
]

AI_DIFFICULTIES = ["EASY", "NORMAL", "HARD", "ELITE"]

# --------------------------------------------------------------------------- #
#  Nitro
# --------------------------------------------------------------------------- #
NITRO_MAX = 100.0
NITRO_DRAIN = 42.0        # per second while held
NITRO_REGEN = 11.0       # per second while not held
NITRO_MIN_TO_USE = 6.0
NITRO_POWER_MULT = 1.75
NITRO_SPEED_MULT = 1.18
