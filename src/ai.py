"""Opponent AI.

Each opponent drives to a racing line rather than just chasing the next
waypoint: it aims for a point ahead, pulls that point toward the apex of the
corner it can see coming, brakes *before* the corner based on how much faster
than the corner speed it currently is, then feeds the throttle back in on the
exit.  Personalities change how well it does all of that, and small timed
mistakes keep it human.
"""

from __future__ import annotations

import math
import random

import pygame

from . import settings
from .car import Car
from .utils import angle_diff, clamp, lerp, sign


# skill profiles -------------------------------------------------------------- #
#   speed        : fraction of the car's own top speed used on a straight
#   corner       : how much it respects the corner-speed hint (1 = perfect)
#   brake        : braking precision (1 = brakes at the last moment)
#   line         : racing-line / apex accuracy
#   err_freq     : mistakes per ~second        err_mag : how big they are
#   throttle_gain / steer_react : how quickly it acts
#   nitro        : probability it uses nitro when it makes sense
#   handbrake    : whether it leans on the handbrake for tight corners
PROFILES = {
    "EASY":   dict(speed=0.84, corner=0.68, brake=0.66, line=0.42, err_freq=0.11,
                   err_mag=0.34, throttle_gain=6.0, steer_react=7.5, nitro=0.0,
                   handbrake=True),
    "NORMAL": dict(speed=0.93, corner=0.84, brake=0.84, line=0.70, err_freq=0.05,
                   err_mag=0.22, throttle_gain=8.0, steer_react=9.5, nitro=0.4,
                   handbrake=True),
    "HARD":   dict(speed=0.985, corner=0.93, brake=0.93, line=0.88, err_freq=0.026,
                   err_mag=0.14, throttle_gain=10.0, steer_react=12.0, nitro=0.85,
                   handbrake=False),
    "ELITE":  dict(speed=1.02, corner=0.985, brake=0.985, line=0.96, err_freq=0.012,
                   err_mag=0.08, throttle_gain=12.0, steer_react=14.0, nitro=1.0,
                   handbrake=False),
}
PROFILES["MEDIUM"] = PROFILES["NORMAL"]      # backwards-compatible alias


class AICar(Car):
    def __init__(self, spec, pos, angle, difficulty="NORMAL", name="AI"):
        super().__init__(spec, pos, angle, name=name, is_player=False)
        self.difficulty = difficulty if difficulty in PROFILES else "NORMAL"
        self.p = PROFILES[self.difficulty]

        self._base_offset = random.uniform(-0.16, 0.16)      # personal line bias
        self._offset = self._base_offset
        self._wander_phase = random.uniform(0, 10)
        self._mistake_timer = random.uniform(1.0, 4.0)
        self._mistake_steer = 0.0
        self._lift_timer = 0.0
        self._stuck_time = 0.0
        self._recover_time = 0.0
        self._last_progress = 0.0
        self.nitro = settings.NITRO_MAX
        self.nitro_ready = True
        self.ai_target = pygame.Vector2(pos)                 # for the debug view

    # ------------------------------------------------------------------ #
    def think(self, track, dt, race_time, rivals=None):
        if self.frozen or self.finished:
            self.throttle *= 0.9
            self.steer *= 0.85
            self.nitro_active = False
            return

        p = self.p
        speed = self.speed
        vmax = self.max_speed

        # ---- stuck / wrong-way detection & recovery -------------- #
        on_line = track.node_at_progress(self.progress + 90.0)[0]
        to_line = on_line - self.pos
        line_err = angle_diff(math.degrees(math.atan2(to_line.y, to_line.x)), self.angle)
        vel_fwd = self.telemetry.get("vel_fwd", 0.0)

        gained = (self.progress - self._last_progress) % track.length
        self._last_progress = self.progress
        making_progress = 4.0 < gained < track.length * 0.5
        wrong_way = abs(line_err) > 105.0 or vel_fwd < -50.0
        if (speed < 30.0 and not making_progress) or wrong_way:
            self._stuck_time += dt
        else:
            self._stuck_time = max(0.0, self._stuck_time - dt * 2.5)
        if self._recover_time <= 0.0 and self._stuck_time > 1.4:
            self._recover_time = 1.2
            self._stuck_time = 0.0
        if self._recover_time > 0.0:
            self._recover_time -= dt
            self.handbrake = False
            self.nitro_active = False
            if speed < 15.0:
                # dead stop / nosed in -> reverse away, rotate nose toward line
                self.throttle = -1.0
                self.steer = clamp(-line_err / 50.0, -1.0, 1.0)
            else:
                # rolling (often backwards) -> drive forward, aim at the line
                self.throttle = 1.0
                self.steer = clamp(line_err / 38.0, -1.0, 1.0)
            if abs(line_err) < 32.0 and vel_fwd > 40.0:
                self._recover_time = 0.0     # recovered - hand back to normal
            return

        # ---- where to aim ----------------------------------------- #
        look = 120.0 + speed * 0.55
        aim = track.point_ahead(self.progress, look)
        _, tan_ahead, node_ahead = track.node_at_progress(self.progress + look)
        nrm_ahead = pygame.Vector2(-tan_ahead.y, tan_ahead.x)

        # signed curvature (deg / 100u) of the corner we're heading into -> apex pull
        sc = track.signed_curvature_ahead(self.progress, 240.0 + speed * 0.4)
        apex_pull = -sign(sc) * clamp(abs(sc) / 38.0, 0.0, 1.0) * (track.road_half * 0.78) * p["line"]

        # slow personal wander so cars don't share one perfect line
        self._wander_phase += dt * 1.1
        self._offset = lerp(self._offset, self._base_offset, clamp(dt * 0.4, 0, 1))
        wander = math.sin(self._wander_phase) * track.road_half * 0.10 * (1.4 - p["line"])

        lateral = apex_pull + self._offset * track.road_half + wander

        # ---- overtaking / avoidance ----------------------------- #
        lateral += self._traffic_bias(track, rivals, nrm_ahead)

        target = aim + nrm_ahead * clamp(lateral, -track.road_half * 0.95, track.road_half * 0.95)
        self.ai_target = target

        to_target = target - self.pos
        desired = math.degrees(math.atan2(to_target.y, to_target.x))
        err = angle_diff(desired, self.angle)

        # ---- mistakes ------------------------------------------- #
        self._mistake_timer -= dt
        if self._mistake_timer <= 0:
            self._mistake_timer = random.uniform(2.0, 5.5)
            if random.random() < p["err_freq"] * 10:
                self._mistake_steer = random.uniform(-p["err_mag"], p["err_mag"])
                if random.random() < 0.4:
                    self._lift_timer = random.uniform(0.2, 0.6)      # brief lift
        self._mistake_steer *= (1.0 - clamp(dt * 1.6, 0, 1))
        self._lift_timer = max(0.0, self._lift_timer - dt)

        steer_cmd = clamp(err / 40.0 + self._mistake_steer, -1.0, 1.0)
        self.steer = lerp(self.steer, steer_cmd, clamp(p["steer_react"] * dt, 0, 1))

        # ---- speed control: brake before the corner ------------- #
        future = clamp(speed * 1.5, 140.0, 780.0)
        cs_now = track.corner_speed_ahead(self.progress, 70.0)
        cs_soon = track.corner_speed_ahead(self.progress, future)
        corner_frac = min(cs_now, cs_soon)
        target_frac = lerp(1.0, corner_frac, p["corner"])
        target_speed = vmax * p["speed"] * target_frac

        brake_margin = 1.0 + (1.0 - p["brake"]) * 0.7 + 0.04
        if abs(err) > 105:
            throttle_target = 1.0            # facing very wrong way: power round
        elif self._lift_timer > 0:
            throttle_target = 0.0
        elif speed > target_speed * brake_margin:
            throttle_target = -1.0
        elif speed < target_speed - 22:
            throttle_target = 1.0
        else:
            throttle_target = 0.22
        if 55 < abs(err) <= 105:
            throttle_target = min(throttle_target, 0.0)   # ease, never force reverse

        self.throttle = lerp(self.throttle, throttle_target,
                             clamp(p["throttle_gain"] * dt, 0, 1))

        # handbrake only as a low-skill crutch for very tight corners
        self.handbrake = (p["handbrake"] and abs(sc) > 42.0
                          and speed > vmax * 0.60 and throttle_target < 0)

        # ---- nitro -------------------------------------------- #
        straight = corner_frac > 0.86 and abs(err) < 12
        want = (p["nitro"] > 0 and straight and speed > vmax * 0.5 and self.nitro > 22)
        if want and random.random() < p["nitro"]:
            self.nitro_active = True
            self.nitro = max(0.0, self.nitro - settings.NITRO_DRAIN * dt)
        else:
            self.nitro_active = False
            self.nitro = min(settings.NITRO_MAX, self.nitro + settings.NITRO_REGEN * dt)

    # ------------------------------------------------------------------ #
    def _traffic_bias(self, track, rivals, forward_normal):
        """Nudge the aim point sideways to pass / not clip a nearby car."""
        if not rivals:
            return 0.0
        fwd = self.forward_vec()
        bias = 0.0
        for other in rivals:
            if other is self:
                continue
            delta = other.pos - self.pos
            ahead = delta.dot(fwd)
            side = delta.dot(forward_normal)
            dist = delta.length()
            if 4.0 < ahead < 165.0 and abs(side) < 80.0 and dist < 175.0:
                # someone slower just ahead and roughly on my line -> go round
                closing = self.speed - other.speed
                urgency = clamp((175.0 - dist) / 175.0, 0.2, 1.0)
                want_side = -sign(side) if abs(side) > 6 else (1.0 if self._base_offset >= 0 else -1.0)
                bias += want_side * track.road_half * 0.55 * urgency
                if closing < 10:
                    bias *= 0.7
            elif dist < 46.0 and abs(side) < 40.0:
                # side-by-side contact risk -> ease away
                bias += -sign(side or 1.0) * track.road_half * 0.4
        return clamp(bias, -track.road_half * 0.9, track.road_half * 0.9)
