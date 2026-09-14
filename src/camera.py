"""Smooth top-down chase camera with speed zoom and collision shake."""

from __future__ import annotations

import random

import pygame

from .utils import clamp, lerp


class Camera:
    def __init__(self, screen_size, world_pos=(0, 0)):
        self.screen_size = pygame.Vector2(screen_size)
        self.pos = pygame.Vector2(world_pos)          # world point at screen centre
        self.target = pygame.Vector2(world_pos)
        self.zoom = 1.0
        self.target_zoom = 1.0
        self._shake_time = 0.0
        self._shake_mag = 0.0
        self._shake_offset = pygame.Vector2()
        self.enable_shake = True

    def resize(self, screen_size):
        self.screen_size = pygame.Vector2(screen_size)

    def snap_to(self, world_pos):
        self.pos = pygame.Vector2(world_pos)
        self.target = pygame.Vector2(world_pos)
        self._shake_offset.update(0, 0)

    def add_shake(self, magnitude):
        if not self.enable_shake:
            return
        self._shake_mag = max(self._shake_mag, magnitude)
        self._shake_time = max(self._shake_time, min(0.6, 0.12 + magnitude * 0.02))

    def follow(self, world_pos, speed_frac: float, look_ahead=(0, 0)):
        self.target = pygame.Vector2(world_pos) + pygame.Vector2(look_ahead)
        # zoom out a little at speed for a better view of what's coming
        self.target_zoom = lerp(1.12, 0.82, clamp(speed_frac, 0.0, 1.0))

    def update(self, dt):
        # critically-damped-ish follow
        follow_k = clamp(6.5 * dt, 0.0, 1.0)
        self.pos += (self.target - self.pos) * follow_k
        self.zoom += (self.target_zoom - self.zoom) * clamp(3.0 * dt, 0.0, 1.0)

        if self._shake_time > 0.0:
            self._shake_time -= dt
            decay = clamp(self._shake_time / 0.6, 0.0, 1.0)
            mag = self._shake_mag * decay
            self._shake_offset.update(random.uniform(-mag, mag), random.uniform(-mag, mag))
            if self._shake_time <= 0.0:
                self._shake_mag = 0.0
                self._shake_offset.update(0, 0)
        else:
            self._shake_offset.update(0, 0)

    # ------------------------------------------------------------------ #
    def world_to_screen(self, world_pos) -> pygame.Vector2:
        w = pygame.Vector2(world_pos)
        return (w - self.pos) * self.zoom + self.screen_size * 0.5 + self._shake_offset

    def screen_to_world(self, screen_pos) -> pygame.Vector2:
        s = pygame.Vector2(screen_pos)
        return (s - self.screen_size * 0.5 - self._shake_offset) / self.zoom + self.pos

    def visible_rect(self) -> pygame.Rect:
        half = self.screen_size * 0.5 / self.zoom
        top_left = self.pos - half
        return pygame.Rect(top_left.x, top_left.y, half.x * 2, half.y * 2)
