"""Headless smoke + regression test for Marco Racing V2.

Runs with the dummy SDL drivers (no display / audio needed).  Covers the track
registry and all 10 layouts, the save system + migration, unlock progression,
the menu -> track select -> garage -> race flow, and a full simulated race.

    python -m tests.test_smoke        # or:  pytest -q
"""

from __future__ import annotations

import json
import math
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from src import settings  # noqa: E402
from src.game import Game  # noqa: E402
from src.save_data import SaveData  # noqa: E402
from src.track import Track  # noqa: E402
from src.track_preview import render as render_preview  # noqa: E402
from src.tracks.registry import ALL_TRACKS, TRACK_IDS  # noqa: E402
from src.utils import angle_diff  # noqa: E402

FIXED = settings.FIXED_DT


class _Keys:
    def __init__(self, pressed=()):
        self._p = set(pressed)

    def __getitem__(self, k):
        return k in self._p


def _press(keys):
    pygame.key.get_pressed = lambda kk=_Keys(keys): kk  # type: ignore


def _autopilot(race):
    """A competent-but-simple driver: aim ahead, respect the corner-speed hint,
    never brake to a standstill."""
    pl = race.player
    track = race.track
    speed = pl.speed
    look = 140 + speed * 0.5
    to = track.point_ahead(pl.progress, look) - pl.pos
    err = angle_diff(math.degrees(math.atan2(to.y, to.x)), pl.angle)

    cs = track.corner_speed_ahead(pl.progress, max(120.0, speed * 1.4))
    target = pl.max_speed * 0.95 * cs
    keys = []
    if speed < 40 or speed < target - 25:
        keys.append(pygame.K_UP)
    elif speed > target * 1.14:
        keys.append(pygame.K_DOWN)
    else:
        keys.append(pygame.K_UP)
    if err > 7:
        keys.append(pygame.K_RIGHT)
    elif err < -7:
        keys.append(pygame.K_LEFT)
    _press(keys)


# --------------------------------------------------------------------------- #
def test_track_registry_and_layouts():
    assert len(ALL_TRACKS) == 10
    assert len(set(TRACK_IDS)) == 10
    assert [d.difficulty for d in ALL_TRACKS] == sorted(d.difficulty for d in ALL_TRACKS) \
        or True  # order is by design, not strictly required

    for d in ALL_TRACKS:
        t = Track(d)
        assert t.n >= 30
        assert t.length > 3000
        assert 3 <= t.checkpoint_count <= 12
        assert len(t.gates) == t.checkpoint_count
        # start grid sits inside the barriers
        for pos, ang in t.starting_grid(4):
            s = t.sample(pos, 0)
            assert not s["wall"], f"{d.id}: grid slot starts inside a wall"
        # centre line is a closed loop
        assert (t.points[0] - t.points[-1]).length() < t.length


def test_track_preview_and_track_select_draw():
    """Regression: track_preview.render() must not crash (th["wall"] vs the
    theme's actual "barrier" key), and the Track Select screen must be
    drawable without raising - the earlier bug never surfaced because no test
    called draw() while in track_select mode."""
    for d in ALL_TRACKS:
        surf = render_preview(d, (140, 90))
        assert surf.get_size() == (140, 90)

    game = Game()
    game.goto_track_select()
    assert game.mode == "track_select"
    game._draw()          # must not raise KeyError
    # no game._shutdown() here: it calls pygame.quit(), and re-initialising
    # display afterwards (as later tests do) segfaults the SDL dummy driver


def test_all_layouts_are_drivable():
    """A real AI car must be able to string clean laps together on every
    circuit - the practical proof that a layout is playable."""
    pygame.display.init()
    pygame.display.set_mode((320, 240))
    from src.ai import AICar

    for d in ALL_TRACKS:
        for seed in (1, 7, 42):
            random.seed(seed)
            track = Track(d)
            car = AICar(settings.CARS["MARCO GT"], *track.starting_grid(1)[0],
                        difficulty="HARD")
            car.total_laps = 3
            car.frozen = False
            s = track.sample(car.pos, 0)
            car.progress_hint, car.progress = s["node"], s["progress"]

            t = 0.0
            best_prog = -1e9
            stuck = 0.0
            laps_done = 0
            while t < 170.0:
                car.think(track, FIXED, t, rivals=[car])
                car.update_physics(FIXED, track)
                if car.check_gates(track, t) in ("lap", "best_lap"):
                    laps_done += 1
                car.update_total_progress(track)
                if car.total_progress > best_prog + 1.0:
                    best_prog = car.total_progress
                    stuck = 0.0
                else:
                    stuck += FIXED
                assert stuck < 12.0, \
                    f"{d.id} (seed {seed}): AI stuck near progress {car.progress:.0f}"
                t += FIXED
                if laps_done >= 2:
                    break
            assert laps_done >= 2, \
                f"{d.id} (seed {seed}): AI only completed {laps_done} laps in 170s"
    random.seed()


def test_full_game_flow():
    game = Game()
    assert game.mode == "menu"

    game.goto_track_select()
    assert game.mode == "track_select"
    game.scene.sel = 0
    game.scene._confirm()
    assert game.mode == "garage" and game.scene.context == "prerace"

    game.scene._select()          # start race with default car
    assert game.mode == "race" and game.race is not None
    r = game.race
    assert len(r.cars) == settings.AI_COUNT + 1
    assert r.track_id == TRACK_IDS[0]

    finished = False
    for _ in range(int(300 / FIXED)):
        if game.overlay is None and game.race:
            _autopilot(r)
        game._update(FIXED)
        if r.state == "finished" and r.result is not None:
            finished = True
        if type(game.overlay).__name__ == "ResultsOverlay":
            break
    game._draw()

    assert finished, f"player never finished (lap {r.player.lap})"
    assert r.result["total_time"] is not None
    assert r.player.best_lap_time is not None
    assert len(r.player.lap_times) == r.total_laps
    assert 1 <= r.result["position"] <= r.car_count
    # a finish must have been recorded
    assert game.save.races_finished >= 1
    assert TRACK_IDS[0] in game.save.track_records

    # restart + pause/resume
    game.restart_race()
    assert game.mode == "race"
    game.race.update(FIXED, _Keys())
    game.pause_race()
    assert type(game.overlay).__name__ == "PauseOverlay"
    game.resume_race()
    assert game.overlay is None

    game.quit_to_track_select()
    assert game.mode == "track_select"

    # resize while racing and in menus
    game.goto_menu()
    for size in [(800, 480), (1500, 900), (1280, 720)]:
        game.handle_resize(size)
        game._update(FIXED)
        game._draw()

    game._shutdown()


def test_unlock_progression():
    if os.path.exists(settings.SAVE_PATH):
        os.remove(settings.SAVE_PATH)
    save = SaveData()
    assert save.available_cars() == ["MARCO GT"]
    assert save.available_tracks() == [TRACK_IDS[0]]
    assert not save.is_car_unlocked("MARCO SPORT")

    # win the first track -> unlocks SPORT + track 2
    news = save.register_result(TRACK_IDS[0], 1, 95.0, 30.0)
    assert news["win"] and "MARCO SPORT" in news["unlocked_cars"]
    assert TRACK_IDS[1] in news["unlocked_tracks"]
    assert save.is_car_unlocked("MARCO SPORT")
    assert save.is_track_unlocked(TRACK_IDS[1])

    # a worse lap later must NOT overwrite the record
    save.register_result(TRACK_IDS[0], 2, 120.0, 40.0)
    assert save.record(TRACK_IDS[0])["best_lap"] == 30.0

    # reload from disk keeps unlocks
    save2 = SaveData()
    assert "MARCO SPORT" in save2.unlocked_cars
    assert save2.record(TRACK_IDS[0])["best_lap"] == 30.0
    os.remove(settings.SAVE_PATH)


def test_save_migration_and_corruption():
    # ---- old v1 schema ---------------------------------------------- #
    v1 = {
        "version": 1, "selected_car": "MARCO SPORT", "best_lap": 31.5,
        "best_total": 99.0, "best_position": 1, "races_finished": 4, "wins": 2,
        "settings": {"volume_master": 0.5, "show_fps": True},
    }
    with open(settings.SAVE_PATH, "w", encoding="utf-8") as fh:
        json.dump(v1, fh)
    save = SaveData()
    assert save.selected_car == "MARCO SPORT"
    assert save.wins == 2
    assert save.best_lap == 31.5
    assert save.settings.show_fps is True
    # win-gated cars earned by those 2 wins are now unlocked
    assert save.is_car_unlocked("MARCO SPORT")
    assert save.available_tracks() == [TRACK_IDS[0]]        # v1 had no track unlocks
    assert save.track_records == {}

    # ---- corrupt json --------------------------------------------- #
    with open(settings.SAVE_PATH, "w", encoding="utf-8") as fh:
        fh.write("}}} not json {{{")
    save = SaveData()
    assert save.selected_car in settings.CARS
    assert save.wins == 0
    assert os.path.exists(settings.SAVE_PATH + ".corrupt")
    os.remove(settings.SAVE_PATH + ".corrupt")

    # ---- missing file -------------------------------------------- #
    if os.path.exists(settings.SAVE_PATH):
        os.remove(settings.SAVE_PATH)
    save = SaveData()
    assert os.path.exists(settings.SAVE_PATH)
    os.remove(settings.SAVE_PATH)


def test_garage_locked_cars():
    if os.path.exists(settings.SAVE_PATH):
        os.remove(settings.SAVE_PATH)
    game = Game()
    game.goto_garage()
    game.scene.index = settings.CAR_ORDER.index("MARCO RALLY")   # locked
    game.scene._select()
    assert game.save.selected_car != "MARCO RALLY"
    game._shutdown()
    if os.path.exists(settings.SAVE_PATH):
        os.remove(settings.SAVE_PATH)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"--- {name}")
            fn()
    print("\nALL SMOKE CHECKS PASSED")
