"""The human-controlled car: input handling + nitro."""

from __future__ import annotations

import pygame

from . import settings
from .car import Car
from .utils import clamp, move_toward


class Player(Car):
    def __init__(self, spec, pos, angle):
        super().__init__(spec, pos, angle, name="YOU", is_player=True)
        self.nitro = settings.NITRO_MAX
        self.nitro_ready = True
        self._steer_input = 0.0

    # ------------------------------------------------------------------ #
    def handle_input(self, keys, dt):
        if self.frozen or self.finished:
            self.throttle = 0.0
            self.steer = move_toward(self.steer, 0.0, 4.0 * dt)
            self.handbrake = False
            self.nitro_active = False
            self._regen_nitro(dt)
            return

        up = keys[pygame.K_w] or keys[pygame.K_UP]
        down = keys[pygame.K_s] or keys[pygame.K_DOWN]
        left = keys[pygame.K_a] or keys[pygame.K_LEFT]
        right = keys[pygame.K_d] or keys[pygame.K_RIGHT]

        target_throttle = (1.0 if up else 0.0) + (-1.0 if down else 0.0)
        # smooth the throttle a touch for nicer feel
        self.throttle = move_toward(self.throttle, target_throttle, 6.0 * dt)

        target_steer = (-1.0 if left else 0.0) + (1.0 if right else 0.0)
        steer_speed = 5.5 if target_steer != 0 else 8.0
        self.steer = move_toward(self.steer, target_steer, steer_speed * dt)

        self.handbrake = keys[pygame.K_SPACE]

        want_nitro = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        self._update_nitro(want_nitro, dt)

    # ------------------------------------------------------------------ #
    def _update_nitro(self, want, dt):
        if want and self.nitro_ready and self.nitro > 0 and self.throttle > 0.1:
            self.nitro_active = True
            self.nitro = max(0.0, self.nitro - settings.NITRO_DRAIN * dt)
            if self.nitro <= 0.0:
                self.nitro_ready = False
        else:
            self.nitro_active = False
            self._regen_nitro(dt)

    def _regen_nitro(self, dt):
        self.nitro = min(settings.NITRO_MAX, self.nitro + settings.NITRO_REGEN * dt)
        if not self.nitro_ready and self.nitro >= settings.NITRO_MIN_TO_USE:
            self.nitro_ready = True

    @property
    def nitro_frac(self):
        return clamp(self.nitro / settings.NITRO_MAX, 0.0, 1.0)
