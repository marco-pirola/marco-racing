"""Lightweight particle + skid-mark system.

Everything is stored in world coordinates and drawn through the camera.  Counts
are capped so the effects never become a performance problem.
"""

from __future__ import annotations

import random

import pygame

from .utils import clamp

MAX_PARTICLES = 320
MAX_MARKS = 900


class Particle:
    __slots__ = ("pos", "vel", "life", "max_life", "radius", "color", "grow", "drag")

    def __init__(self, pos, vel, life, radius, color, grow=0.0, drag=1.6):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)
        self.life = life
        self.max_life = life
        self.radius = radius
        self.color = color
        self.grow = grow
        self.drag = drag

    def update(self, dt):
        self.life -= dt
        self.pos += self.vel * dt
        self.vel *= clamp(1.0 - self.drag * dt, 0.0, 1.0)
        self.radius += self.grow * dt

    @property
    def alive(self):
        return self.life > 0 and self.radius > 0.4


class SkidMark:
    __slots__ = ("a", "b", "life", "max_life", "width", "shade")

    def __init__(self, a, b, life, width, shade):
        self.a = pygame.Vector2(a)
        self.b = pygame.Vector2(b)
        self.life = life
        self.max_life = life
        self.width = width
        self.shade = shade


class ParticleSystem:
    def __init__(self):
        self.particles: list[Particle] = []
        self.marks: list[SkidMark] = []

    def clear(self):
        self.particles.clear()
        self.marks.clear()

    # ------------------------------------------------------------------ #
    def add(self, particle: Particle):
        if len(self.particles) < MAX_PARTICLES:
            self.particles.append(particle)

    def spawn_burst(self, pos, count, base_color, *, speed=60, life=0.5, radius=4, spread=360):
        for _ in range(count):
            if len(self.particles) >= MAX_PARTICLES:
                break
            ang = random.uniform(0, spread)
            v = pygame.Vector2(speed * random.uniform(0.3, 1.0), 0).rotate(ang)
            jitter = tuple(clamp(c + random.randint(-18, 18), 0, 255) for c in base_color)
            self.particles.append(Particle(pos, v, life * random.uniform(0.6, 1.2),
                                           radius * random.uniform(0.6, 1.3), jitter,
                                           grow=random.uniform(-2, 6)))

    def spawn_smoke(self, pos, vel, color=(210, 210, 210)):
        if len(self.particles) >= MAX_PARTICLES:
            return
        v = pygame.Vector2(vel) * 0.2 + pygame.Vector2(random.uniform(-12, 12), random.uniform(-12, 12))
        self.particles.append(Particle(pos, v, random.uniform(0.5, 0.9),
                                       random.uniform(4, 7), color, grow=random.uniform(10, 22),
                                       drag=0.9))

    def spawn_nitro(self, pos, back_dir, color=(120, 200, 255)):
        if len(self.particles) >= MAX_PARTICLES:
            return
        v = pygame.Vector2(back_dir) * random.uniform(80, 180)
        v += pygame.Vector2(random.uniform(-20, 20), random.uniform(-20, 20))
        self.particles.append(Particle(pos, v, random.uniform(0.18, 0.34),
                                       random.uniform(3, 6), color, grow=random.uniform(-6, 4),
                                       drag=2.2))

    def add_skid(self, a, b, *, width=5, life=6.0, shade=40):
        if len(self.marks) >= MAX_MARKS:
            self.marks.pop(0)
        self.marks.append(SkidMark(a, b, life, width, shade))

    # ------------------------------------------------------------------ #
    def update(self, dt):
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.alive]
        for m in self.marks:
            m.life -= dt
        if self.marks:
            self.marks = [m for m in self.marks if m.life > 0]

    # ------------------------------------------------------------------ #
    def draw_marks(self, surface, camera):
        for m in self.marks:
            a = camera.world_to_screen(m.a)
            b = camera.world_to_screen(m.b)
            alpha = clamp(m.life / m.max_life, 0.0, 1.0)
            w = max(1, int(m.width * camera.zoom))
            col = (m.shade, m.shade, m.shade + 4)
            s = surface
            if alpha < 1.0:
                # fade by blending a dark line with reduced alpha
                line = pygame.Surface((abs(b.x - a.x) + w * 2 + 2, abs(b.y - a.y) + w * 2 + 2), pygame.SRCALPHA)
                off = pygame.Vector2(min(a.x, b.x) - w - 1, min(a.y, b.y) - w - 1)
                pygame.draw.line(line, (*col, int(120 * alpha)), a - off, b - off, w)
                s.blit(line, off)
            else:
                pygame.draw.line(s, col, a, b, w)

    def draw_particles(self, surface, camera):
        for p in self.particles:
            sp = camera.world_to_screen(p.pos)
            r = p.radius * camera.zoom
            if r < 0.6:
                continue
            alpha = clamp(p.life / p.max_life, 0.0, 1.0)
            size = int(r * 2) + 2
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*p.color, int(200 * alpha)), (size // 2, size // 2), max(1, int(r)))
            surface.blit(surf, (sp.x - size // 2, sp.y - size // 2))

    @property
    def count(self):
        return len(self.particles) + len(self.marks)
