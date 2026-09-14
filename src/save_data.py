"""Persistent JSON save data + user settings  (schema v2).

Design goals:
  * never raise on load - missing file, corrupt JSON, wrong types or an old
    (v1) schema all fall back to sensible values so the game always starts;
  * old saves keep working - v1 fields are migrated, new fields get defaults;
  * writes are atomic (temp file + os.replace).
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import asdict, dataclass

from . import settings
from .tracks.registry import TRACK_IDS, first_track_id, next_track_id
from .utils import clamp

SCHEMA_VERSION = 2

DEFAULT_SETTINGS = {
    "volume_master": 0.8,
    "volume_sfx": 0.9,
    "fullscreen": False,
    "show_fps": False,
    "screen_shake": True,
}

DEFAULT_SAVE = {
    "version": SCHEMA_VERSION,
    "selected_car": settings.DEFAULT_CAR,
    "selected_track": first_track_id(),
    "unlocked_cars": [settings.DEFAULT_CAR],
    "unlocked_tracks": [first_track_id()],
    "track_records": {},          # id -> {best_lap, best_total, best_position}
    "best_lap": None,             # global bests (menu summary)
    "best_total": None,
    "best_position": None,
    "races_finished": 0,
    "wins": 0,
    "podiums": 0,
    "settings": DEFAULT_SETTINGS,
}


@dataclass
class Settings:
    volume_master: float = 0.8
    volume_sfx: float = 0.9
    fullscreen: bool = False
    show_fps: bool = False
    screen_shake: bool = True

    def clamp_values(self) -> "Settings":
        self.volume_master = clamp(float(self.volume_master), 0.0, 1.0)
        self.volume_sfx = clamp(float(self.volume_sfx), 0.0, 1.0)
        self.fullscreen = bool(self.fullscreen)
        self.show_fps = bool(self.show_fps)
        self.screen_shake = bool(self.screen_shake)
        return self


def _f(value):
    try:
        if value is None:
            return None
        v = float(value)
        return v if (v == v and v > 0) else None
    except (TypeError, ValueError):
        return None


def _i(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _record(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {
        "best_lap": _f(raw.get("best_lap")),
        "best_total": _f(raw.get("best_total")),
        "best_position": _i(raw.get("best_position")),
    }


class SaveData:
    def __init__(self, path: str | None = None):
        self.path = path or settings.SAVE_PATH
        data = self._load_raw()

        self.selected_car: str = data["selected_car"]
        self.selected_track: str = data["selected_track"]
        self.unlocked_cars: list[str] = data["unlocked_cars"]
        self.unlocked_tracks: list[str] = data["unlocked_tracks"]
        self.track_records: dict[str, dict] = data["track_records"]
        self.best_lap = data["best_lap"]
        self.best_total = data["best_total"]
        self.best_position = data["best_position"]
        self.races_finished: int = int(data["races_finished"])
        self.wins: int = int(data["wins"])
        self.podiums: int = int(data["podiums"])
        self.settings = Settings(**data["settings"]).clamp_values()

        self._sync_unlocks()

    # ================================================================ #
    def _load_raw(self) -> dict:
        merged = copy.deepcopy(DEFAULT_SAVE)
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if not isinstance(raw, dict):
                raise ValueError("save root is not an object")
            self._merge(merged, raw)
        except FileNotFoundError:
            self._write(merged)
        except (json.JSONDecodeError, ValueError, OSError, TypeError, KeyError):
            try:
                if os.path.exists(self.path):
                    os.replace(self.path, self.path + ".corrupt")
            except OSError:
                pass
            self._write(merged)
        return merged

    def _merge(self, merged: dict, raw: dict) -> None:
        """Best-effort merge of a possibly-old / partial save onto the defaults."""
        if isinstance(raw.get("selected_car"), str) and raw["selected_car"] in settings.CARS:
            merged["selected_car"] = raw["selected_car"]
        if isinstance(raw.get("selected_track"), str) and raw["selected_track"] in TRACK_IDS:
            merged["selected_track"] = raw["selected_track"]

        if isinstance(raw.get("unlocked_cars"), list):
            merged["unlocked_cars"] = [c for c in raw["unlocked_cars"] if c in settings.CARS]
        if settings.DEFAULT_CAR not in merged["unlocked_cars"]:
            merged["unlocked_cars"].insert(0, settings.DEFAULT_CAR)

        if isinstance(raw.get("unlocked_tracks"), list):
            merged["unlocked_tracks"] = [t for t in raw["unlocked_tracks"] if t in TRACK_IDS]
        if first_track_id() not in merged["unlocked_tracks"]:
            merged["unlocked_tracks"].insert(0, first_track_id())

        if isinstance(raw.get("track_records"), dict):
            merged["track_records"] = {tid: _record(rec)
                                       for tid, rec in raw["track_records"].items()
                                       if tid in TRACK_IDS}

        merged["best_lap"] = _f(raw.get("best_lap"))
        merged["best_total"] = _f(raw.get("best_total"))
        merged["best_position"] = _i(raw.get("best_position"))
        for key in ("races_finished", "wins", "podiums"):
            v = _i(raw.get(key))
            merged[key] = v if v is not None and v >= 0 else 0

        user_settings = raw.get("settings", {})
        if isinstance(user_settings, dict):
            for key in DEFAULT_SETTINGS:
                if isinstance(user_settings.get(key), (int, float, bool)):
                    merged["settings"][key] = user_settings[key]

    # ------------------------------------------------------------------ #
    def _sync_unlocks(self) -> None:
        """Make sure win-gated cars that have been earned are marked unlocked."""
        for car, need in settings.CAR_UNLOCKS.items():
            if self.wins >= need and car not in self.unlocked_cars:
                self.unlocked_cars.append(car)
        if self.selected_car not in self.available_cars():
            self.selected_car = settings.DEFAULT_CAR
        if self.selected_track not in self.available_tracks():
            self.selected_track = first_track_id()

    # ================================================================ #
    def _write(self, data: dict) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp, self.path)
        except OSError as exc:
            print(f"[save] could not write save file: {exc}")

    def to_dict(self) -> dict:
        return {
            "version": SCHEMA_VERSION,
            "selected_car": self.selected_car,
            "selected_track": self.selected_track,
            "unlocked_cars": list(dict.fromkeys(self.unlocked_cars)),
            "unlocked_tracks": list(dict.fromkeys(self.unlocked_tracks)),
            "track_records": self.track_records,
            "best_lap": self.best_lap,
            "best_total": self.best_total,
            "best_position": self.best_position,
            "races_finished": self.races_finished,
            "wins": self.wins,
            "podiums": self.podiums,
            "settings": asdict(self.settings),
        }

    def save(self) -> None:
        self._write(self.to_dict())

    # ================================================================ #
    #  Queries used by the UI
    # ================================================================ #
    def available_cars(self) -> list[str]:
        if settings.UNLOCK_ALL_CARS:
            return list(settings.CAR_ORDER)
        return [c for c in settings.CAR_ORDER if c in self.unlocked_cars]

    def is_car_unlocked(self, car: str) -> bool:
        return settings.UNLOCK_ALL_CARS or car in self.unlocked_cars

    def available_tracks(self) -> list[str]:
        if settings.UNLOCK_ALL_TRACKS:
            return list(TRACK_IDS)
        return [t for t in TRACK_IDS if t in self.unlocked_tracks]

    def is_track_unlocked(self, track_id: str) -> bool:
        return settings.UNLOCK_ALL_TRACKS or track_id in self.unlocked_tracks

    def record(self, track_id: str) -> dict:
        return self.track_records.get(track_id, {"best_lap": None, "best_total": None,
                                                 "best_position": None})

    def car_unlock_hint(self, car: str) -> str:
        need = settings.CAR_UNLOCKS.get(car, 0)
        if need <= 0 or self.is_car_unlocked(car):
            return ""
        return f"WIN {need} RACE{'S' if need != 1 else ''} TO UNLOCK  ({self.wins}/{need})"

    # ================================================================ #
    #  Result recording + unlocks
    # ================================================================ #
    def register_result(self, track_id: str, position: int,
                        total_time: float | None, best_lap: float | None) -> dict:
        news = {
            "best_lap": False, "best_total": False, "track_record": False,
            "best_position": False, "win": False,
            "unlocked_cars": [], "unlocked_tracks": [],
        }
        self.races_finished += 1
        if position == 1:
            self.wins += 1
            news["win"] = True
        if position <= 3:
            self.podiums += 1

        rec = dict(self.record(track_id))
        if best_lap is not None and (rec["best_lap"] is None or best_lap < rec["best_lap"]):
            rec["best_lap"] = float(best_lap)
            news["best_lap"] = True
            news["track_record"] = True
        if total_time is not None and (rec["best_total"] is None or total_time < rec["best_total"]):
            rec["best_total"] = float(total_time)
            news["best_total"] = True
        if rec["best_position"] is None or position < rec["best_position"]:
            rec["best_position"] = int(position)
        self.track_records[track_id] = rec

        # global bests (for the menu summary)
        if best_lap is not None and (self.best_lap is None or best_lap < self.best_lap):
            self.best_lap = float(best_lap)
        if total_time is not None and (self.best_total is None or total_time < self.best_total):
            self.best_total = float(total_time)
        if self.best_position is None or position < self.best_position:
            self.best_position = int(position)
            news["best_position"] = True

        # ---- unlocks --------------------------------------------------- #
        for car, need in settings.CAR_UNLOCKS.items():
            if self.wins >= need and car not in self.unlocked_cars:
                self.unlocked_cars.append(car)
                news["unlocked_cars"].append(car)
        nxt = next_track_id(track_id)
        if nxt and nxt not in self.unlocked_tracks:
            self.unlocked_tracks.append(nxt)
            news["unlocked_tracks"].append(nxt)

        self.save()
        return news
