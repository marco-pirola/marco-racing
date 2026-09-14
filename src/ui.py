"""Reusable UI widgets and the in-race HUD."""

from __future__ import annotations

import pygame

from . import settings
from .utils import clamp, draw_bar, draw_panel, draw_text, format_time, lerp


class Button:
    def __init__(self, text, rect, *, on_click=None, size=26, primary=False, enabled=True):
        self.text = text
        self.rect = pygame.Rect(rect)
        self.on_click = on_click
        self.size = size
        self.primary = primary
        self.enabled = enabled
        self.hover = 0.0        # 0..1 animated
        self._was_hover = False

    def update(self, mouse_pos, dt):
        target = 1.0 if (self.enabled and self.rect.collidepoint(mouse_pos)) else 0.0
        self.hover += (target - self.hover) * clamp(14 * dt, 0, 1)
        just = target > 0.5 and not self._was_hover
        self._was_hover = target > 0.5
        return just  # True on the frame the pointer first enters (for a hover sfx)

    def handle_event(self, event):
        if not self.enabled:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if self.on_click:
                    self.on_click()
                return True
        return False

    def draw(self, surface):
        r = self.rect
        h = self.hover
        if self.primary:
            base = settings.COL_ACCENT
            fill = tuple(int(clamp(c + h * 30, 0, 255)) for c in base)
            txt_col = (20, 20, 24)
        else:
            base = settings.COL_PANEL_LIGHT
            fill = tuple(int(clamp(c + h * 34, 0, 255)) for c in base)
            txt_col = settings.COL_TEXT if self.enabled else settings.COL_TEXT_DIM

        offset = int(-2 * h)
        draw_rect = r.move(0, offset)
        # shadow
        sh = pygame.Surface((r.width + 16, r.height + 16), pygame.SRCALPHA)
        pygame.draw.rect(sh, (0, 0, 0, int(70 + 50 * h)), sh.get_rect(), border_radius=16)
        surface.blit(sh, (r.x - 8, r.y - 8 - offset + 6))

        pygame.draw.rect(surface, fill, draw_rect, border_radius=14)
        if not self.primary:
            border_col = tuple(int(lerp(a, b, 0.15 + 0.85 * h))
                               for a, b in zip(settings.COL_PANEL_LIGHT, settings.COL_ACCENT))
            pygame.draw.rect(surface, border_col, draw_rect, width=2, border_radius=14)
        if h > 0.02 and not self.primary:
            accent = pygame.Rect(draw_rect.x + 10, draw_rect.bottom - 6,
                                 int((draw_rect.width - 20) * h), 3)
            pygame.draw.rect(surface, settings.COL_ACCENT, accent, border_radius=2)

        draw_text(surface, self.text, draw_rect.center, size=self.size,
                  color=txt_col, bold=True, center=True)


class Slider:
    def __init__(self, label, rect, value, *, on_change=None):
        self.label = label
        self.rect = pygame.Rect(rect)
        self.value = clamp(value, 0.0, 1.0)
        self.on_change = on_change
        self.dragging = False

    @property
    def _track(self):
        r = self.rect
        return pygame.Rect(r.x + 220, r.centery - 5, r.width - 260, 10)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._track.inflate(16, 24).collidepoint(event.pos):
                self.dragging = True
                self._set_from_x(event.pos[0])
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self._set_from_x(event.pos[0])
            return True
        return False

    def _set_from_x(self, x):
        t = self._track
        self.value = clamp((x - t.x) / t.width, 0.0, 1.0)
        if self.on_change:
            self.on_change(self.value)

    def draw(self, surface):
        draw_text(surface, self.label, (self.rect.x, self.rect.centery),
                  size=22, color=settings.COL_TEXT, bold=True,
                  right=False)
        t = self._track
        pygame.draw.rect(surface, settings.COL_NITRO_EMPTY, t, border_radius=5)
        fill = pygame.Rect(t.x, t.y, int(t.width * self.value), t.height)
        pygame.draw.rect(surface, settings.COL_ACCENT, fill, border_radius=5)
        knob = (t.x + int(t.width * self.value), t.centery)
        pygame.draw.circle(surface, settings.COL_TEXT, knob, 10)
        pygame.draw.circle(surface, settings.COL_ACCENT, knob, 10, 2)
        draw_text(surface, f"{int(self.value * 100)}", (t.right + 40, self.rect.centery),
                  size=20, color=settings.COL_TEXT_DIM, center=True)


class Toggle:
    def __init__(self, label, rect, value, *, on_change=None):
        self.label = label
        self.rect = pygame.Rect(rect)
        self.value = bool(value)
        self.on_change = on_change

    @property
    def _box(self):
        r = self.rect
        return pygame.Rect(r.x + 220, r.centery - 16, 64, 32)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._box.inflate(20, 20).collidepoint(event.pos) or self.rect.collidepoint(event.pos):
                self.value = not self.value
                if self.on_change:
                    self.on_change(self.value)
                return True
        return False

    def draw(self, surface):
        draw_text(surface, self.label, (self.rect.x, self.rect.centery),
                  size=22, color=settings.COL_TEXT, bold=True)
        box = self._box
        col = settings.COL_GOOD if self.value else settings.COL_NITRO_EMPTY
        pygame.draw.rect(surface, col, box, border_radius=16)
        knob_x = box.right - 16 if self.value else box.x + 16
        pygame.draw.circle(surface, settings.COL_TEXT, (knob_x, box.centery), 13)
        draw_text(surface, "ON" if self.value else "OFF",
                  (box.right + 44, box.centery), size=18,
                  color=settings.COL_TEXT_DIM, center=True)


# --------------------------------------------------------------------------- #
#  HUD
# --------------------------------------------------------------------------- #
class HUD:
    def __init__(self):
        self.messages: list[list] = []   # [text, ttl, max_ttl, color]

    def flash(self, text, duration=2.0, color=settings.COL_ACCENT):
        self.messages.append([text, duration, duration, color])

    def update(self, dt):
        for m in self.messages:
            m[1] -= dt
        self.messages = [m for m in self.messages if m[1] > 0]

    # ------------------------------------------------------------------ #
    def draw(self, surface, player, race, *, show_debug=False):
        w, h = surface.get_size()

        # ---- top-left: lap + position -------------------------------- #
        panel = pygame.Rect(24, 22, 232, 92)
        draw_panel(surface, panel, radius=16, alpha=180, shadow=True)
        draw_text(surface, "LAP", (panel.x + 18, panel.y + 12), size=17,
                  color=settings.COL_TEXT_DIM, bold=True)
        draw_text(surface, player.hud_lap_text(), (panel.x + 18, panel.y + 30),
                  size=34, color=settings.COL_TEXT, bold=True)
        draw_text(surface, "POS", (panel.x + 128, panel.y + 12), size=17,
                  color=settings.COL_TEXT_DIM, bold=True)
        pos_col = settings.COL_ACCENT if player.position == 1 else settings.COL_TEXT
        draw_text(surface, f"{player.position}/{race.car_count}",
                  (panel.x + 128, panel.y + 30), size=34, color=pos_col, bold=True)

        # ---- top-right: timing -------------------------------------- #
        tp = pygame.Rect(w - 288, 22, 264, 118)
        draw_panel(surface, tp, radius=16, alpha=180)
        draw_text(surface, "TIME", (tp.x + 18, tp.y + 12), size=17,
                  color=settings.COL_TEXT_DIM, bold=True)
        draw_text(surface, format_time(race.race_time), (tp.x + 18, tp.y + 30),
                  size=30, color=settings.COL_TEXT, bold=True)
        draw_text(surface, "LAP", (tp.x + 18, tp.y + 68), size=15,
                  color=settings.COL_TEXT_DIM, bold=True)
        cur_lap = race.race_time - player.current_lap_start if player.lap >= 1 else 0.0
        draw_text(surface, format_time(cur_lap), (tp.x + 58, tp.y + 64),
                  size=22, color=settings.COL_TEXT)
        draw_text(surface, "BEST", (tp.x + 148, tp.y + 68), size=15,
                  color=settings.COL_TEXT_DIM, bold=True)
        best = player.best_lap_time if player.best_lap_time is not None else race.best_lap_ref
        draw_text(surface, format_time(best), (tp.x + 192, tp.y + 64),
                  size=22, color=settings.COL_ACCENT_2)

        # ---- bottom-left: speed ------------------------------------- #
        sp = pygame.Rect(24, h - 116, 236, 92)
        draw_panel(surface, sp, radius=16, alpha=180)
        draw_text(surface, f"{int(player.speed_kmh)}", (sp.x + 18, sp.y + 20),
                  size=48, color=settings.COL_TEXT, bold=True)
        draw_text(surface, "KM/H", (sp.x + 150, sp.y + 46), size=18,
                  color=settings.COL_TEXT_DIM, bold=True)

        # ---- bottom-centre: nitro bar ------------------------------ #
        nb = pygame.Rect(w // 2 - 150, h - 52, 300, 24)
        draw_panel(surface, nb.inflate(20, 16), radius=14, alpha=170, shadow=False)
        frac = getattr(player, "nitro_frac", 0.0)
        col = settings.COL_NITRO if getattr(player, "nitro_ready", True) else settings.COL_BAD
        draw_bar(surface, nb, frac, fill=col, back=settings.COL_NITRO_EMPTY, radius=10)
        label = "NITRO" + ("  ▲" if getattr(player, "nitro_active", False) else "")
        draw_text(surface, label, (nb.centerx, nb.y - 14), size=15,
                  color=settings.COL_TEXT_DIM, bold=True, center=True)

        # ---- centre messages -------------------------------------- #
        for i, (text, ttl, mx, color) in enumerate(self.messages):
            a = clamp(ttl / mx * 3, 0, 1)
            y = h * 0.26 + i * 44
            scale = 1.0 + 0.12 * clamp((mx - ttl) * 4, 0, 1) * (1 if ttl > mx * 0.8 else 0)
            draw_text(surface, text, (w // 2, y), size=int(40 * scale),
                      color=color, bold=True, center=True, shadow=True,
                      alpha=int(255 * a))

        # ---- mini standings (top-right, below timing) ------------- #
        self._draw_standings(surface, race, tp)

        # ---- debug ------------------------------------------------- #
        if show_debug:
            self._draw_debug(surface, player, race)

    def _draw_standings(self, surface, race, tp):
        x = tp.x
        y = tp.bottom + 12
        for idx, car in enumerate(race.standings[:4]):
            row = pygame.Rect(x, y + idx * 26, tp.width, 23)
            bg = (settings.COL_ACCENT if car.is_player else settings.COL_PANEL)
            s = pygame.Surface(row.size, pygame.SRCALPHA)
            s.fill((*bg, 70 if not car.is_player else 120))
            surface.blit(s, row.topleft)
            name = car.name if len(car.name) <= 12 else car.name[:12]
            tcol = (20, 20, 24) if car.is_player else settings.COL_TEXT
            draw_text(surface, f"{idx + 1}", (row.x + 8, row.centery), size=16,
                      color=tcol, bold=True, midleft=True)
            draw_text(surface, name, (row.x + 30, row.centery), size=16, color=tcol,
                      midleft=True)
            tl = getattr(car, "total_laps", settings.TOTAL_LAPS)
            gap = "FIN" if car.finished else f"L{max(1, min(car.lap, tl))}"
            draw_text(surface, gap, (row.right - 10, row.centery), size=15,
                      color=tcol, right=True)

    def _draw_debug(self, surface, player, race):
        s = race.track.sample(player.pos, player.progress_hint)
        lines = [
            f"FPS {race.game.clock.get_fps():5.1f}   {race.track_name}  ({race.track_id})",
            f"pos ({player.pos.x:7.1f}, {player.pos.y:7.1f})",
            f"spd {player.speed:6.1f}  ({player.speed_kmh:5.1f} km/h)   thr {player.throttle:+.2f}",
            f"vel_lat {player.telemetry.get('vel_lat', 0):6.1f}  slip {player.telemetry.get('slip', 0):5.1f}",
            f"surface {s['surface']:<6} side {s['side']}  offset {s['offset']:+7.1f}",
            f"wall {s['wall']}  dist_to_wall {s['dist_to_wall']:6.1f}  pen {s['penetration']:.1f}",
            f"lap {player.lap}  next_cp {player.next_cp}  cp_in_lap {player.cp_in_lap}",
            f"progress {player.progress:8.1f} / {race.track.length:8.1f}",
            f"particles {race.particles.count}   cars {race.car_count}",
            f"state {race.state}  countdown {race.countdown:.2f}",
        ]
        panel = pygame.Rect(24, 150, 420, 24 + len(lines) * 20)
        s = pygame.Surface(panel.size, pygame.SRCALPHA)
        s.fill((0, 0, 0, 150))
        surface.blit(s, panel.topleft)
        for i, ln in enumerate(lines):
            draw_text(surface, ln, (panel.x + 12, panel.y + 10 + i * 20),
                      size=16, color=(120, 255, 160))
