"""Small 2D previews of a circuit, generated from its real layout.

Cached per (track id, size) - a preview is only built the first time it is
shown.
"""

from __future__ import annotations

import pygame

from .tracks.base import build_centerline, theme as get_theme

_CACHE: dict[tuple, pygame.Surface] = {}


def render(definition, size, *, player_progress=None, track=None) -> pygame.Surface:
    key = (definition.id, size, round(player_progress, 1) if player_progress else None)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    w, h = size
    surf = pygame.Surface(size, pygame.SRCALPHA)
    th = get_theme(definition.theme)

    pts = build_centerline(definition)
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    span_x = max(1.0, maxx - minx)
    span_y = max(1.0, maxy - miny)
    pad = 16
    scale = min((w - pad * 2) / span_x, (h - pad * 2) / span_y)
    ox = pad + (w - pad * 2 - span_x * scale) / 2
    oy = pad + (h - pad * 2 - span_y * scale) / 2

    def T(p):
        return (ox + (p.x - minx) * scale, oy + (p.y - miny) * scale)

    screen_pts = [T(p) for p in pts]
    road_w = max(5, int(definition.road_half * scale * 2 * 0.5))

    # outline / shoulder
    pygame.draw.lines(surf, th["barrier"], True, screen_pts, road_w + 6)
    pygame.draw.lines(surf, th["asphalt"], True, screen_pts, road_w)
    pygame.draw.lines(surf, th["line"], True, screen_pts, max(1, road_w // 7))

    # start / finish marker
    p0 = pts[0]
    p1 = pts[1 % len(pts)]
    tan = (p1 - p0)
    if tan.length_squared() > 1e-6:
        nrm = pygame.Vector2(-tan.y, tan.x).normalize()
        a = T(p0 + nrm * definition.road_half)
        b = T(p0 - nrm * definition.road_half)
        pygame.draw.line(surf, (245, 245, 245), a, b, max(2, road_w // 3))
    sx, sy = T(p0)
    pygame.draw.circle(surf, (255, 210, 90), (int(sx), int(sy)), max(3, road_w // 3))

    _CACHE[key] = surf
    return surf


def clear_cache():
    _CACHE.clear()
