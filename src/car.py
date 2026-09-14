"""Reusable car: physical state, race progress bookkeeping and procedural art."""

from __future__ import annotations

import math

import pygame

from . import physics, settings
from .utils import clamp


class Car:
    LENGTH = 46
    WIDTH = 24

    def __init__(self, spec: dict, pos, angle, *, name="CAR", is_player=False):
        self.spec = spec
        self.name = name
        self.is_player = is_player
        self.color = tuple(spec["color"])
        self.accent = tuple(spec.get("accent", (255, 255, 255)))

        # tuning (copied so per-car nitro tweaks never touch the shared spec)
        self.engine_power = spec["engine_power"]
        self.max_speed = spec["max_speed"]
        self.brake_power = spec["brake_power"]
        self.reverse_speed = spec["reverse_speed"]
        self.grip = spec["grip"]
        self.drift_grip = spec["drift_grip"]
        self.drag = spec["drag"]
        self.steer_rate = spec["steer_rate"]
        self.category = spec.get("category", "Balanced")
        self.silhouette = spec.get("silhouette", "standard")
        self.offroad_grip = float(spec.get("offroad", 1.0))
        nitro_mult = float(spec.get("nitro_mult", 1.0))
        self.nitro_power_mult = 1.0 + (settings.NITRO_POWER_MULT - 1.0) * nitro_mult
        self.nitro_speed_mult = 1.0 + (settings.NITRO_SPEED_MULT - 1.0) * nitro_mult
        self.nitro_mult = nitro_mult
        self.total_laps = settings.TOTAL_LAPS

        # state
        self.pos = pygame.Vector2(pos)
        self.velocity = pygame.Vector2()
        self.angle = float(angle)
        self.surface = "track"
        self.frozen = True                 # released after the countdown

        # control inputs (filled by Player / AI each frame)
        self.throttle = 0.0
        self.steer = 0.0
        self.handbrake = False
        self.nitro_active = False

        # telemetry from the last physics step
        self.telemetry = {"speed": 0.0, "slip": 0.0, "drifting": False, "braking": False,
                          "vel_fwd": 0.0, "vel_lat": 0.0}

        # race progress
        self.progress_hint = 0
        self.progress = 0.0                 # arc length along centre line
        self.lap = 0
        self.next_cp = 0
        self.cp_in_lap = 0
        self.finished = False
        self.finish_time = None
        self.total_progress = 0.0           # laps * track_len + progress (for sorting)
        self.current_lap_start = 0.0
        self.last_lap_time = None
        self.best_lap_time = None
        self.lap_times: list[float] = []
        self.position = 1
        self._prev_pos = pygame.Vector2(pos)
        self.new_best_lap_flash = 0.0
        self.wheel_spin = 0.0               # visual only

    # ------------------------------------------------------------------ #
    @property
    def speed(self):
        return self.velocity.length()

    @property
    def speed_kmh(self):
        return self.speed * settings.KMH_FACTOR

    @property
    def speed_frac(self):
        return clamp(self.speed / self.max_speed, 0.0, 1.0)

    def forward_vec(self):
        return pygame.Vector2(1, 0).rotate(self.angle)

    # ------------------------------------------------------------------ #
    def update_physics(self, dt, track):
        self._prev_pos = pygame.Vector2(self.pos)

        if self.frozen:
            self.velocity *= 0.82
            self.telemetry["speed"] = self.velocity.length()
            self.telemetry["drifting"] = False
            self.telemetry["braking"] = False
            sample = track.sample(self.pos, self.progress_hint)
            self.progress_hint = sample["node"]
            self.progress = sample["progress"]
            self.surface = "track"
            return

        sample = track.sample(self.pos, self.progress_hint)
        self.surface = sample["surface"]

        self.telemetry = physics.simulate(
            self, self.throttle, self.steer, self.handbrake, dt,
            nitro=self.nitro_active,
        )

        # wall collision (re-sample after moving); iterate a couple of times so a
        # fast single-frame incursion is fully corrected - no tunnelling.
        sample = track.sample(self.pos, sample["node"])
        impact = 0.0
        for _ in range(3):
            if not sample["wall"]:
                break
            hit = physics.resolve_wall(self, sample["wall_normal"], sample["penetration"])
            impact = max(impact, hit)
            sample = track.sample(self.pos, sample["node"])

        self.progress_hint = sample["node"]
        self.progress = sample["progress"]
        self.surface = sample["surface"]

        self.wheel_spin += (self.telemetry["vel_fwd"] * 0.05 + self.steer * 6.0) * dt
        if self.new_best_lap_flash > 0:
            self.new_best_lap_flash = max(0.0, self.new_best_lap_flash - dt)
        return impact

    # ------------------------------------------------------------------ #
    def check_gates(self, track, race_time):
        """Advance checkpoint / lap counters.  Returns an event string or None."""
        if self.finished:
            return None
        from .utils import segments_intersect

        a, b = self._prev_pos, self.pos
        cp_total = track.checkpoint_count
        need_all = cp_total - 1          # checkpoints 1..cp_total-1
        total_laps = getattr(self, "total_laps", settings.TOTAL_LAPS)
        event = None

        # We only ever need to test one gate: the next one in sequence.
        gate = track.gates[self.next_cp]
        if not segments_intersect(a, b, gate["a"], gate["b"]):
            return None

        if self.next_cp != 0:
            # ordinary checkpoint
            self.cp_in_lap += 1
            self.next_cp = (self.next_cp + 1) % cp_total
            return "checkpoint"

        # crossing the start / finish line
        if self.lap == 0:
            self.lap = 1
            self.cp_in_lap = 0
            self.next_cp = 1
            self.current_lap_start = race_time
            return None

        if self.cp_in_lap < need_all:
            return None                 # missed a checkpoint -> not a valid lap

        lap_time = race_time - self.current_lap_start
        self.last_lap_time = lap_time
        self.lap_times.append(lap_time)
        if self.best_lap_time is None or lap_time < self.best_lap_time:
            self.best_lap_time = lap_time
            self.new_best_lap_flash = 2.2
            event = "best_lap"
        else:
            event = "lap"

        self.lap += 1
        self.cp_in_lap = 0
        self.next_cp = 1
        self.current_lap_start = race_time
        if self.lap > total_laps:
            self.finished = True
            self.finish_time = race_time
            self.lap = total_laps
            event = "finished"
        return event

    def update_total_progress(self, track):
        # lap 0 == still behind the line on the formation lap
        completed = self.lap - 1
        self.total_progress = completed * track.length + self.progress
        if self.finished and self.finish_time is not None:
            # finishers ranked by finish time, always ahead of everyone racing
            self.total_progress = 1e9 - self.finish_time

    # ------------------------------------------------------------------ #
    #  Rendering
    # ------------------------------------------------------------------ #
    def draw(self, surface, camera):
        center = camera.world_to_screen(self.pos)
        z = camera.zoom
        L = self.LENGTH * z
        W = self.WIDTH * z
        ang = self.angle

        # --- shadow ------------------------------------------------- #
        shadow = pygame.Surface((L * 1.5, L * 1.5), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 90),
                            (L * 0.25, L * 0.55, L, W))
        shadow = pygame.transform.rotate(shadow, -ang)
        surface.blit(shadow, shadow.get_rect(center=(center.x + 4 * z, center.y + 5 * z)))

        body = self._body_surface(z)
        rot = pygame.transform.rotate(body, -ang)
        surface.blit(rot, rot.get_rect(center=center))

        # nitro flame
        if self.nitro_active and self.speed > 30:
            back = self.pos - self.forward_vec() * (self.LENGTH * 0.55)
            bp = camera.world_to_screen(back)
            r = (6 + 4 * math.sin(pygame.time.get_ticks() * 0.05)) * z
            glow = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
            pygame.draw.circle(glow, (120, 200, 255, 120), (r * 2, r * 2), int(r * 1.8))
            pygame.draw.circle(glow, (200, 240, 255, 200), (r * 2, r * 2), int(r))
            surface.blit(glow, glow.get_rect(center=bp))

    def _body_surface(self, z):
        """Draw the car pointing +x on its own surface."""
        L = self.LENGTH * z
        W = self.WIDTH * z
        pad = 10 * z
        surf = pygame.Surface((L + pad * 2, W + pad * 2), pygame.SRCALPHA)
        ox, oy = pad, pad

        def R(x, y, w, h, color, radius=3):
            pygame.draw.rect(surf, color, (ox + x * z, oy + y * z, w * z, h * z),
                             border_radius=int(radius * z))

        wl = self.LENGTH
        ww = self.WIDTH
        sil = getattr(self, "silhouette", "standard")

        # wheels
        wheel_col = (24, 24, 28)
        tyre_w = 7 if sil == "rally" else 6
        for wx, wy in ((wl * 0.16, -2), (wl * 0.16, ww - 4 - (tyre_w - 6)),
                       (wl * 0.74, -2), (wl * 0.74, ww - 4 - (tyre_w - 6))):
            R(wx, wy, wl * 0.16, tyre_w, wheel_col, radius=2)

        # rear wing for the fast cars
        if sil in ("sport", "turbo"):
            R(-1.5, 1.0, 3.5, ww - 2, tuple(int(c * 0.55) for c in self.color), radius=1)

        # body
        dark = tuple(int(c * 0.7) for c in self.color)
        body_inset = 1.0 if sil == "rally" else 2.5
        R(0, 1, wl, ww - 2, dark, radius=6)
        R(1.5, body_inset, wl - 3, ww - body_inset * 2, self.color, radius=6)
        # hood / nose accent
        nose = tuple(min(255, int(c * 1.12)) for c in self.color)
        R(wl * 0.62, 3.5, wl * 0.32, ww - 7, nose, radius=4)
        # cockpit / windshield
        R(wl * 0.30, 4.5, wl * 0.26, ww - 9, (40, 48, 66), radius=3)
        R(wl * 0.33, 5.5, wl * 0.10, ww - 11, (150, 200, 230), radius=2)
        # centre racing stripe
        R(0, ww * 0.5 - 1.4, wl, 2.8, self.accent, radius=1)
        if sil == "grip":
            R(0, 2.0, wl, 1.6, self.accent, radius=1)
            R(0, ww - 3.6, wl, 1.6, self.accent, radius=1)
        # front lights
        R(wl - 4.5, 3.0, 3, 3.5, (255, 245, 200), radius=1)
        R(wl - 4.5, ww - 6.5, 3, 3.5, (255, 245, 200), radius=1)
        # rear lights
        R(1.5, 3.0, 2, 3.0, (255, 80, 80), radius=1)
        R(1.5, ww - 6.0, 2, 3.0, (255, 80, 80), radius=1)
        return surf

    # ------------------------------------------------------------------ #
    def hud_lap_text(self):
        tl = getattr(self, "total_laps", settings.TOTAL_LAPS)
        return f"{min(max(self.lap, 1), tl)}/{tl}"
