"""Small helpers shared across the code base.

Kept dependency-free apart from pygame itself.
"""

from __future__ import annotations

from functools import lru_cache

import pygame

from . import settings


# --------------------------------------------------------------------------- #
#  Maths
# --------------------------------------------------------------------------- #
def clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def move_toward(current: float, target: float, delta: float) -> float:
    """Step `current` toward `target` by at most `delta`."""
    if current < target:
        return min(current + delta, target)
    return max(current - delta, target)


def sign(x: float) -> float:
    return (x > 0) - (x < 0)


def angle_diff(a: float, b: float) -> float:
    """Smallest signed difference a-b in degrees, in range (-180, 180]."""
    d = (a - b) % 360.0
    if d > 180.0:
        d -= 360.0
    return d


def catmull_rom(p0, p1, p2, p3, t: float) -> pygame.Vector2:
    """Centripetal Catmull-Rom interpolation between p1 and p2 (t in 0..1).

    The centripetal (alpha = 0.5) parametrisation is used because, unlike the
    uniform form, it never forms cusps or self-loops on tight, unevenly spaced
    corners - exactly what a hand-authored racing line needs.
    """
    def knot(ti, a, b):
        d = (pygame.Vector2(b) - pygame.Vector2(a)).length()
        return ti + max(d, 1e-6) ** 0.5

    t0 = 0.0
    t1 = knot(t0, p0, p1)
    t2 = knot(t1, p1, p2)
    t3 = knot(t2, p2, p3)
    tt = t1 + t * (t2 - t1)

    a1 = p0 * ((t1 - tt) / (t1 - t0)) + p1 * ((tt - t0) / (t1 - t0))
    a2 = p1 * ((t2 - tt) / (t2 - t1)) + p2 * ((tt - t1) / (t2 - t1))
    a3 = p2 * ((t3 - tt) / (t3 - t2)) + p3 * ((tt - t2) / (t3 - t2))
    b1 = a1 * ((t2 - tt) / (t2 - t0)) + a2 * ((tt - t0) / (t2 - t0))
    b2 = a2 * ((t3 - tt) / (t3 - t1)) + a3 * ((tt - t1) / (t3 - t1))
    return b1 * ((t2 - tt) / (t2 - t1)) + b2 * ((tt - t1) / (t2 - t1))


def smooth_closed_loop(points, samples_per_segment: int = 14):
    """Return a dense, smooth closed poly-line through `points`."""
    pts = [pygame.Vector2(p) for p in points]
    n = len(pts)
    out = []
    for i in range(n):
        p0 = pts[(i - 1) % n]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n]
        for s in range(samples_per_segment):
            out.append(catmull_rom(p0, p1, p2, p3, s / samples_per_segment))
    return out


def segments_intersect(p1, p2, p3, p4) -> bool:
    """True if segment p1-p2 crosses segment p3-p4."""
    def ccw(a, b, c):
        return (c.y - a.y) * (b.x - a.x) - (b.y - a.y) * (c.x - a.x)

    d1 = ccw(p3, p4, p1)
    d2 = ccw(p3, p4, p2)
    d3 = ccw(p1, p2, p3)
    d4 = ccw(p1, p2, p4)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    return False


def format_time(seconds: float) -> str:
    """Format as MM:SS.hh  (e.g. 00:37.42)."""
    if seconds is None or seconds < 0 or seconds == float("inf"):
        return "--:--.--"
    total_cs = int(round(seconds * 100))
    minutes, rem = divmod(total_cs, 6000)
    secs, cs = divmod(rem, 100)
    return f"{minutes:02d}:{secs:02d}.{cs:02d}"


# --------------------------------------------------------------------------- #
#  Fonts
# --------------------------------------------------------------------------- #
_FONT_CANDIDATES = ["Segoe UI", "SF Pro Display", "Helvetica Neue", "Arial", "Verdana", "DejaVu Sans"]


@lru_cache(maxsize=64)
def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    if not pygame.font.get_init():
        pygame.font.init()
    name = pygame.font.match_font(",".join(_FONT_CANDIDATES), bold=bold)
    try:
        if name:
            return pygame.font.Font(name, size)
    except Exception:
        pass
    return pygame.font.SysFont(None, size, bold=bold)


@lru_cache(maxsize=512)
def _render_cached(text: str, size: int, bold: bool, color: tuple) -> pygame.Surface:
    return get_font(size, bold).render(text, True, color)


def draw_text(surface, text, pos, size=22, color=settings.COL_TEXT, *,
              bold=False, center=False, right=False, midleft=False, shadow=False, alpha=255):
    surf = _render_cached(str(text), int(size), bool(bold), tuple(color))
    if alpha < 255:
        surf = surf.copy()
        surf.set_alpha(alpha)
    rect = surf.get_rect()
    if center:
        rect.center = pos
    elif right:
        rect.midright = pos
    elif midleft:
        rect.midleft = pos
    else:
        rect.topleft = pos
    if shadow:
        sh = _render_cached(str(text), int(size), bool(bold), settings.COL_SHADOW)
        if alpha < 255:
            sh = sh.copy()
            sh.set_alpha(int(alpha * 0.6))
        surface.blit(sh, rect.move(2, 2))
    surface.blit(surf, rect)
    return rect


def text_size(text, size=22, bold=False):
    return get_font(int(size), bool(bold)).size(str(text))


# --------------------------------------------------------------------------- #
#  Drawing helpers
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=32)
def vertical_gradient(width: int, height: int, top: tuple, bottom: tuple) -> pygame.Surface:
    surf = pygame.Surface((width, height)).convert()
    for y in range(height):
        t = y / max(1, height - 1)
        col = (
            int(lerp(top[0], bottom[0], t)),
            int(lerp(top[1], bottom[1], t)),
            int(lerp(top[2], bottom[2], t)),
        )
        pygame.draw.line(surf, col, (0, y), (width, y))
    return surf


def draw_panel(surface, rect, *, radius=16, fill=settings.COL_PANEL,
               border=None, border_width=2, shadow=True, shadow_offset=8, alpha=255):
    rect = pygame.Rect(rect)
    if shadow:
        sh = pygame.Surface((rect.width + shadow_offset * 2, rect.height + shadow_offset * 2), pygame.SRCALPHA)
        pygame.draw.rect(sh, (0, 0, 0, 90), sh.get_rect(), border_radius=radius + shadow_offset)
        surface.blit(sh, (rect.x - shadow_offset, rect.y - shadow_offset + 3))
    panel = pygame.Surface(rect.size, pygame.SRCALPHA)
    fill_col = (*fill, alpha) if len(fill) == 3 else fill
    pygame.draw.rect(panel, fill_col, panel.get_rect(), border_radius=radius)
    # subtle top highlight
    hl = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(hl, (255, 255, 255, 14), (0, 0, rect.width, max(2, rect.height // 2)),
                     border_radius=radius)
    panel.blit(hl, (0, 0))
    surface.blit(panel, rect.topleft)
    if border:
        pygame.draw.rect(surface, border, rect, width=border_width, border_radius=radius)


def draw_bar(surface, rect, fraction, *, fill=settings.COL_ACCENT,
             back=settings.COL_NITRO_EMPTY, radius=6, border=None):
    rect = pygame.Rect(rect)
    fraction = clamp(fraction, 0.0, 1.0)
    pygame.draw.rect(surface, back, rect, border_radius=radius)
    if fraction > 0.001:
        inner = pygame.Rect(rect.x, rect.y, max(radius * 2, int(rect.width * fraction)), rect.height)
        pygame.draw.rect(surface, fill, inner, border_radius=radius)
    if border:
        pygame.draw.rect(surface, border, rect, width=1, border_radius=radius)
