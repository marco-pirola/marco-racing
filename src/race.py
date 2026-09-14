"""The race itself: world simulation, camera, effects and result tracking."""

from __future__ import annotations

import math
import random

import pygame

from . import settings
from .ai import AICar
from .camera import Camera
from .car import Car
from .particles import ParticleSystem
from .physics import resolve_car_overlap
from .player import Player
from .track import Track
from .tracks.registry import get_track
from .ui import HUD
from .utils import clamp, draw_text


class Race:
    def __init__(self, game, car_key: str, track_id: str, save):
        self.game = game
        self.save = save
        self.track_id = track_id
        definition = get_track(track_id)
        self.track = Track(definition)
        self.track_name = definition.name
        self.total_laps = self.track.laps

        self.particles = ParticleSystem()
        self.hud = HUD()
        self.camera = Camera(game.screen.get_size(), self.track.start_pos)
        self.camera.snap_to(self.track.start_pos)

        # ---- build the grid --------------------------------------- #
        grid = self.track.starting_grid(settings.AI_COUNT + 1)
        player_slot = min(2, len(grid) - 1)
        pos, ang = grid[player_slot]
        self.player = Player(settings.CARS[car_key], pos, ang)

        self.ai: list[AICar] = []
        ai_car_pool = [c for c in settings.CAR_ORDER if c != car_key] or settings.CAR_ORDER
        random.shuffle(ai_car_pool)
        difficulties = list(definition.recommended_ai)
        slot_i = 0
        for i in range(settings.AI_COUNT):
            if slot_i == player_slot:
                slot_i += 1
            gpos, gang = grid[slot_i]
            slot_i += 1
            spec = dict(settings.CARS[ai_car_pool[i % len(ai_car_pool)]])
            spec["color"] = settings.AI_COLORS[i % len(settings.AI_COLORS)]
            spec["accent"] = (255, 255, 255)
            diff = difficulties[i % len(difficulties)]
            self.ai.append(AICar(spec, gpos, gang, difficulty=diff,
                                 name=f"CPU {diff[0]}{i + 1}"))

        self.cars: list[Car] = [self.player] + self.ai
        for c in self.cars:
            c.total_laps = self.total_laps
            s = self.track.sample(c.pos, 0)
            c.progress_hint = s["node"]
            c.progress = s["progress"]

        self.car_count = len(self.cars)
        self.best_lap_ref = self.save.record(track_id)["best_lap"]

        # ---- state ------------------------------------------------- #
        self.state = "countdown"
        self.countdown = settings.COUNTDOWN_TIME + settings.GO_TIME
        self._last_count_shown = None
        self.race_time = 0.0
        self.standings = list(self.cars)
        self.result = None
        self.result_news = {}
        self._shake_cooldown = 0.0
        self._finish_delay = 0.0

        self.game.audio.start_engine()

    # ------------------------------------------------------------------ #
    def resize(self, size):
        self.camera.resize(size)

    # ================================================================ #
    def update(self, dt, keys):
        self.camera.enable_shake = self.save.settings.screen_shake
        self._shake_cooldown = max(0.0, self._shake_cooldown - dt)

        if self.state == "countdown":
            self._update_countdown(dt)
        elif self.state == "racing":
            self.race_time += dt
        elif self.state == "finished":
            self._finish_delay += dt

        # ---- controls ------------------------------------------------ #
        self.player.handle_input(keys, dt)
        for ai in self.ai:
            ai.think(self.track, dt, self.race_time, rivals=self.cars)

        # ---- physics ----------------------------------------------- #
        for c in self.cars:
            impact = c.update_physics(dt, self.track)
            if not impact:
                continue
            if c is self.player and impact > 110 and self._shake_cooldown <= 0:
                self.camera.add_shake(clamp(impact * 0.05, 3, 14))
                self.game.audio.play("hit", volume=clamp(impact / 400, 0.2, 1.0))
                self._shake_cooldown = 0.3
            elif c is not self.player and impact > 220:
                self.game.audio.play("hit", volume=0.18)

        # ---- car vs car ------------------------------------------- #
        for i in range(len(self.cars)):
            for j in range(i + 1, len(self.cars)):
                if resolve_car_overlap(self.cars[i], self.cars[j]):
                    if (self.cars[i] is self.player or self.cars[j] is self.player) \
                            and self._shake_cooldown <= 0:
                        self.camera.add_shake(2.5)
                        self._shake_cooldown = 0.25

        # ---- gates / laps ---------------------------------------- #
        if self.state in ("racing", "finished"):
            for c in self.cars:
                self._handle_event(c, c.check_gates(self.track, self.race_time))

        for c in self.cars:
            c.update_total_progress(self.track)
        self._update_standings()

        # ---- effects / camera / audio -------------------------- #
        self._update_effects(dt)
        self.particles.update(dt)
        self.hud.update(dt)

        self.camera.follow(self.player.pos, self.player.speed_frac,
                           look_ahead=self.player.velocity * 0.35)
        self.camera.update(dt)

        self.game.audio.update_engine(max(self.player.throttle, 0.0), self.player.speed_frac)
        tel = self.player.telemetry
        skidding = (not self.player.frozen and self.player.speed > 40 and
                    (tel.get("drifting") or (tel.get("braking") and tel.get("slip", 0) > 30)
                     or self.player.surface == "grass"))
        self.game.audio.set_skid(skidding, clamp(tel.get("slip", 0) / 160, 0.2, 1.0))

    # ------------------------------------------------------------------ #
    def _update_countdown(self, dt):
        self.countdown -= dt
        elapsed = settings.COUNTDOWN_TIME + settings.GO_TIME - self.countdown
        remaining = settings.COUNTDOWN_TIME - elapsed
        if remaining > 0:
            n = int(math.ceil(remaining))
            if n != self._last_count_shown:
                self._last_count_shown = n
                self.game.audio.play("beep")
        elif self._last_count_shown != 0:
            self._last_count_shown = 0
            self.hud.flash("GO!", duration=1.1, color=settings.COL_GOOD)
            self.game.audio.play("go")
            for c in self.cars:
                c.frozen = False
            self.state = "racing"
            self.race_time = 0.0

    # ------------------------------------------------------------------ #
    def _handle_event(self, car, event):
        if not event:
            return
        if car is not self.player:
            return
        if event == "best_lap":
            self.hud.flash("NEW BEST LAP!", 2.2, settings.COL_ACCENT)
            self.game.audio.play("finish", volume=0.5)
        elif event == "lap":
            lap_no = min(self.player.lap, self.total_laps)
            self.hud.flash(f"LAP {lap_no}/{self.total_laps}", 1.6, settings.COL_TEXT)
            self.game.audio.play("beep", volume=0.5)
        elif event == "finished":
            self._on_player_finish()

    def _on_player_finish(self):
        self.state = "finished"
        self.game.audio.stop_all_loops()
        self.game.audio.play("finish")
        self.player.throttle = 0.0
        self._update_standings()
        self.result = {
            "track_name": self.track_name,
            "track_id": self.track_id,
            "position": self.player.position,
            "total_time": self.player.finish_time,
            "best_lap": self.player.best_lap_time,
            "laps": list(self.player.lap_times),
        }
        try:
            self.result_news = self.save.register_result(
                self.track_id, self.player.position,
                self.player.finish_time, self.player.best_lap_time)
        except Exception as exc:
            print(f"[race] could not store result: {exc}")
            self.result_news = {}

    # ------------------------------------------------------------------ #
    def _update_standings(self):
        self.standings = sorted(self.cars, key=lambda c: c.total_progress, reverse=True)
        for i, c in enumerate(self.standings):
            c.position = i + 1

    # ------------------------------------------------------------------ #
    def _update_effects(self, dt):
        for c in self.cars:
            if c.frozen:
                continue
            tel = c.telemetry
            speed = c.speed
            fwd = c.forward_vec()
            side = pygame.Vector2(-fwd.y, fwd.x)
            back = c.pos - fwd * (c.LENGTH * 0.45)

            drifting = tel.get("drifting")
            braking = tel.get("braking") and tel.get("slip", 0) > 26
            if (drifting or braking or c.handbrake) and speed > 45:
                for s in (-1, 1):
                    wheel = back + side * (s * c.WIDTH * 0.42)
                    self.particles.add_skid(wheel - c.velocity * dt, wheel, width=4,
                                            life=7.0, shade=44 if drifting else 54)
                if random.random() < 0.55:
                    self.particles.spawn_smoke(
                        back, -c.velocity,
                        color=(150, 210, 255) if c.nitro_active else (205, 205, 210))

            if c.throttle > 0.6 and speed > 30 and random.random() < 0.22:
                self.particles.spawn_burst(back, 1, (120, 118, 112), speed=40,
                                           life=0.35, radius=2.5, spread=60)

            if c.nitro_active and speed > 25:
                self.particles.spawn_nitro(back, -fwd)
                if c is self.player and random.random() < 0.08:
                    self.game.audio.play("nitro", volume=0.25)

            if c.surface == "grass" and speed > 55 and random.random() < 0.4:
                col = self._dust_color()
                self.particles.spawn_burst(back, 2, col, speed=60, life=0.55,
                                           radius=3.4, spread=140)
            elif c.surface == "kerb" and speed > 90 and random.random() < 0.25:
                self.particles.spawn_burst(back, 1, (230, 230, 235), speed=45,
                                           life=0.3, radius=2.2, spread=90)

    def _dust_color(self):
        kind = self.track.theme.get("runoff_kind", "grass")
        return {
            "sand": (226, 198, 150), "gravel": (150, 142, 128),
            "concrete": (170, 172, 178), "water": (150, 200, 220),
        }.get(kind, (96, 150, 78))

    # ================================================================ #
    #  Rendering
    # ================================================================ #
    def draw(self, surface):
        debug = self.save.settings.show_fps
        self.track.draw(surface, self.camera, debug=False)
        self.particles.draw_marks(surface, self.camera)

        for c in sorted(self.cars, key=lambda c: (c.is_player, c.pos.y)):
            c.draw(surface, self.camera)

        self.particles.draw_particles(surface, self.camera)
        self._draw_offscreen_markers(surface)

        if debug:
            self.track.draw_debug(surface, self.camera, self.cars,
                                  [ai.ai_target for ai in self.ai])

        self.hud.draw(surface, self.player, self, show_debug=debug)

        if self.state == "countdown":
            self._draw_countdown_overlay(surface)

    def _draw_offscreen_markers(self, surface):
        w, h = surface.get_size()
        rect = pygame.Rect(40, 40, w - 80, h - 80)
        cx, cy = w / 2, h / 2
        for c in self.ai:
            sp = self.camera.world_to_screen(c.pos)
            if rect.collidepoint(sp):
                continue
            d = pygame.Vector2(sp.x - cx, sp.y - cy)
            if d.length_squared() < 1:
                continue
            d.scale_to_length(1)
            edge = pygame.Vector2(clamp(cx + d.x * (w / 2 - 30), 30, w - 30),
                                  clamp(cy + d.y * (h / 2 - 30), 30, h - 30))
            pygame.draw.circle(surface, c.color, edge, 7)
            pygame.draw.circle(surface, (0, 0, 0), edge, 7, 1)

    def _draw_countdown_overlay(self, surface):
        w, h = surface.get_size()
        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 70))
        surface.blit(veil, (0, 0))
        draw_text(surface, self.track_name, (w // 2, int(h * 0.16)), size=30,
                  color=settings.COL_TEXT_DIM, bold=True, center=True)
        elapsed = settings.COUNTDOWN_TIME + settings.GO_TIME - self.countdown
        remaining = settings.COUNTDOWN_TIME - elapsed
        if remaining > 0:
            frac = remaining - math.floor(remaining)
            n = int(math.ceil(remaining))
            scale = 1.6 - 0.6 * frac
            draw_text(surface, str(n), (w // 2, h // 2), size=int(150 * scale),
                      color=settings.COL_TEXT, bold=True, center=True, shadow=True)
            pygame.draw.circle(surface, settings.COL_ACCENT, (w // 2, h // 2),
                               int(70 + 120 * (1 - frac)), 4)
        else:
            draw_text(surface, "GO!", (w // 2, h // 2), size=180,
                      color=settings.COL_GOOD, bold=True, center=True, shadow=True)
