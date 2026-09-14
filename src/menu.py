"""Front-end screens: main menu, track select, garage, settings, plus the
pause / results overlays.

Every screen exposes ``handle_event``, ``update(dt)`` and ``draw(surface)`` and
talks back to :class:`game.Game` through its public ``goto_*`` / ``choose_*``
helpers.
"""

from __future__ import annotations

import math

import pygame

from . import settings, track_preview
from .car import Car
from .tracks.registry import ALL_TRACKS, TRACK_IDS, get_track, next_track_id
from .ui import Button, Slider, Toggle
from .utils import clamp, draw_panel, draw_text, format_time, lerp, vertical_gradient


class BaseScreen:
    def __init__(self, game):
        self.game = game
        self.buttons: list[Button] = []
        self.widgets: list = []
        self.t = 0.0
        self.layout()

    def layout(self):
        ...

    def _bg(self, surface):
        w, h = surface.get_size()
        surface.blit(vertical_gradient(w, h, settings.COL_BG, settings.COL_BG_2), (0, 0))
        streak = tuple(int(lerp(c, 255, 0.055)) for c in settings.COL_BG_2)
        for i in range(-2, int(w / 130) + 4):
            x = int((i * 130 + self.t * 40) % (w + 400)) - 200
            pygame.draw.line(surface, streak, (x, 0), (x - 160, h), 2)

    def handle_event(self, event):
        for b in self.buttons:
            b.handle_event(event)
        for wdg in self.widgets:
            wdg.handle_event(event)

    def update(self, dt):
        self.t += dt
        mouse = pygame.mouse.get_pos()
        for b in self.buttons:
            if b.update(mouse, dt):
                self.game.audio.play("click", volume=0.35)

    def draw(self, surface):
        self._bg(surface)
        for b in self.buttons:
            b.draw(surface)
        for wdg in self.widgets:
            wdg.draw(surface)

    def on_resize(self):
        self.layout()


# =========================================================================== #
class MainMenu(BaseScreen):
    def layout(self):
        w, h = self.game.screen.get_size()
        cx = w // 2
        bw, bh, gap = 320, 60, 16
        top = int(h * 0.40)
        specs = [
            ("PLAY", self.game.goto_track_select, True),
            ("GARAGE", self.game.goto_garage, False),
            ("SETTINGS", self.game.goto_settings, False),
            ("QUIT", self.game.quit, False),
        ]
        self.buttons = [
            Button(label, pygame.Rect(cx - bw // 2, top + i * (bh + gap), bw, bh),
                   on_click=self._wrap(cb), primary=primary, size=25)
            for i, (label, cb, primary) in enumerate(specs)
        ]

    def _wrap(self, cb):
        def inner():
            self.game.audio.play("click")
            cb()
        return inner

    def draw(self, surface):
        self._bg(surface)
        w, h = surface.get_size()
        cx = w // 2
        save = self.game.save
        pulse = 1.0 + 0.02 * math.sin(self.t * 2.4)
        draw_text(surface, "MARCO", (cx, int(h * 0.17)), size=int(94 * pulse),
                  color=settings.COL_TEXT, bold=True, center=True, shadow=True)
        draw_text(surface, "RACING", (cx, int(h * 0.28)), size=int(62 * pulse),
                  color=settings.COL_ACCENT, bold=True, center=True, shadow=True)
        draw_text(surface, "arcade racing  ·  10 circuits  ·  5 cars",
                  (cx, int(h * 0.335)), size=17, color=settings.COL_TEXT_DIM, center=True)

        for b in self.buttons:
            b.draw(surface)

        # ---- career summary strip -------------------------------- #
        cars_n = len(save.available_cars())
        tracks_n = len(save.available_tracks())
        stats = [
            ("WINS", str(save.wins)),
            ("BEST LAP", format_time(save.best_lap) if save.best_lap else "--:--.--"),
            ("CARS", f"{cars_n}/{len(settings.CAR_ORDER)}"),
            ("TRACKS", f"{tracks_n}/{len(TRACK_IDS)}"),
        ]
        panel = pygame.Rect(cx - 360, h - 120, 720, 84)
        draw_panel(surface, panel, radius=16, alpha=200)
        for i, (lab, val) in enumerate(stats):
            x = panel.x + 90 + i * 180
            draw_text(surface, val, (x, panel.y + 26), size=28,
                      color=settings.COL_TEXT, bold=True, center=True)
            draw_text(surface, lab, (x, panel.y + 56), size=14,
                      color=settings.COL_TEXT_DIM, bold=True, center=True)
        draw_text(surface, f"CAR:  {save.selected_car}", (cx, h - 24), size=15,
                  color=settings.COL_TEXT_DIM, center=True)


# =========================================================================== #
class TrackSelect(BaseScreen):
    COLS = 5

    def layout(self):
        w, h = self.game.screen.get_size()
        margin = 40
        gap = 18
        self.card_w = (w - margin * 2 - gap * (self.COLS - 1)) / self.COLS
        self.card_h = self.card_w * 0.94 + 46
        self.grid_x = margin
        self.grid_y = int(h * 0.17)
        self.sel = max(0, TRACK_IDS.index(self.game.save.selected_track)
                       if self.game.save.selected_track in TRACK_IDS else 0)
        self.buttons = [
            Button("BACK", pygame.Rect(30, 30, 120, 44), on_click=self._back, size=19),
            Button("RACE", pygame.Rect(w // 2 - 150, h - 74, 300, 52),
                   on_click=self._confirm, primary=True, size=23),
            Button("GARAGE", pygame.Rect(w - 190, 30, 160, 44),
                   on_click=self._garage, size=19),
        ]

    def _card_rect(self, i):
        col = i % self.COLS
        row = i // self.COLS
        x = self.grid_x + col * (self.card_w + 18)
        y = self.grid_y + row * (self.card_h + 18)
        return pygame.Rect(x, y, self.card_w, self.card_h)

    def _back(self):
        self.game.audio.play("click")
        self.game.goto_menu()

    def _garage(self):
        self.game.audio.play("click")
        self.game.goto_garage()

    def _confirm(self):
        tid = TRACK_IDS[self.sel]
        if not self.game.save.is_track_unlocked(tid):
            self.game.audio.play("hit", volume=0.3)
            return
        self.game.audio.play("click")
        self.game.choose_track(tid)

    def handle_event(self, event):
        super().handle_event(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i in range(len(ALL_TRACKS)):
                if self._card_rect(i).collidepoint(event.pos):
                    if self.sel == i:
                        self._confirm()
                    else:
                        self.sel = i
                        self.game.audio.play("click", volume=0.4)
                    return
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RIGHT, pygame.K_d):
                self.sel = (self.sel + 1) % len(ALL_TRACKS)
            elif event.key in (pygame.K_LEFT, pygame.K_a):
                self.sel = (self.sel - 1) % len(ALL_TRACKS)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.sel = (self.sel + self.COLS) % len(ALL_TRACKS)
            elif event.key in (pygame.K_UP, pygame.K_w):
                self.sel = (self.sel - self.COLS) % len(ALL_TRACKS)

    def draw(self, surface):
        self._bg(surface)
        w, h = surface.get_size()
        draw_text(surface, "SELECT TRACK", (w // 2, int(h * 0.09)), size=44,
                  color=settings.COL_TEXT, bold=True, center=True, shadow=True)

        save = self.game.save
        for i, definition in enumerate(ALL_TRACKS):
            rect = self._card_rect(i)
            unlocked = save.is_track_unlocked(definition.id)
            selected = i == self.sel
            fill = settings.COL_PANEL_LIGHT if selected else settings.COL_PANEL
            draw_panel(surface, rect, radius=14, fill=fill,
                       border=settings.COL_ACCENT if selected else None,
                       border_width=3, shadow=selected)

            thumb = pygame.Rect(rect.x + 10, rect.y + 30, rect.w - 20, rect.w * 0.5)
            pygame.draw.rect(surface, settings.COL_BG, thumb, border_radius=8)
            prev = track_preview.render(definition, (int(thumb.w), int(thumb.h)))
            surface.blit(prev, thumb.topleft)

            draw_text(surface, f"{i + 1:02d}", (rect.x + 14, rect.y + 8), size=15,
                      color=settings.COL_TEXT_DIM, bold=True)
            draw_text(surface, definition.name, (rect.centerx, thumb.bottom + 16),
                      size=16, color=settings.COL_TEXT if unlocked else settings.COL_TEXT_DIM,
                      bold=True, center=True)
            draw_text(surface, definition.stars, (rect.centerx, thumb.bottom + 36),
                      size=15, color=settings.COL_ACCENT, center=True)
            rec = save.record(definition.id)["best_lap"]
            draw_text(surface, format_time(rec) if rec else "no time",
                      (rect.centerx, thumb.bottom + 56), size=13,
                      color=settings.COL_ACCENT_2 if rec else settings.COL_TEXT_DIM,
                      center=True)

            if not unlocked:
                lock = pygame.Surface(rect.size, pygame.SRCALPHA)
                lock.fill((10, 12, 18, 180))
                surface.blit(lock, rect.topleft)
                draw_text(surface, "LOCKED", rect.center, size=18,
                          color=settings.COL_TEXT_DIM, bold=True, center=True)

        # selected-track detail line
        d = ALL_TRACKS[self.sel]
        draw_text(surface, d.blurb, (w // 2, h - 108), size=15,
                  color=settings.COL_TEXT_DIM, center=True)
        for b in self.buttons:
            b.draw(surface)


# =========================================================================== #
class Garage(BaseScreen):
    def __init__(self, game, context="menu"):
        self.context = context
        super().__init__(game)

    def layout(self):
        w, h = self.game.screen.get_size()
        cx = w // 2
        try:
            self.index = settings.CAR_ORDER.index(self.game.save.selected_car)
        except ValueError:
            self.index = 0
        back_cb = self.game.goto_track_select if self.context == "prerace" else self.game.goto_menu
        self.buttons = [
            Button("<", pygame.Rect(cx - 470, h // 2 - 34, 64, 68),
                   on_click=lambda: self._cycle(-1), size=30),
            Button(">", pygame.Rect(cx + 406, h // 2 - 34, 64, 68),
                   on_click=lambda: self._cycle(1), size=30),
            Button("SELECT" if self.context == "menu" else "START RACE",
                   pygame.Rect(cx - 160, int(h * 0.84), 320, 54),
                   on_click=self._select, primary=True, size=23),
            Button("BACK", pygame.Rect(30, 30, 120, 44),
                   on_click=self._wrap(back_cb), size=19),
        ]
        self._shown = {k: 0.0 for k in ("top_speed", "acceleration", "handling", "grip", "nitro")}
        self._preview_angle = 0.0
        self._shine = 0.0

    def _wrap(self, cb):
        def inner():
            self.game.audio.play("click")
            cb()
        return inner

    def _cycle(self, d):
        self.game.audio.play("click", volume=0.5)
        self.index = (self.index + d) % len(settings.CAR_ORDER)
        self._shine = 1.0

    def _select(self):
        key = settings.CAR_ORDER[self.index]
        if not self.game.save.is_car_unlocked(key):
            self.game.audio.play("hit", volume=0.3)
            return
        self.game.audio.play("click")
        self.game.save.selected_car = key
        self.game.save.save()
        if self.context == "prerace":
            self.game.start_race()
        else:
            self.game.goto_menu()

    def update(self, dt):
        super().update(dt)
        self._preview_angle += dt * 42
        self._shine = max(0.0, self._shine - dt * 1.5)
        spec = settings.CARS[settings.CAR_ORDER[self.index]]
        for k, target in spec["stats"].items():
            self._shown[k] = lerp(self._shown[k], target, clamp(dt * 6, 0, 1))

    def handle_event(self, event):
        super().handle_event(event)
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RIGHT, pygame.K_d):
                self._cycle(1)
            elif event.key in (pygame.K_LEFT, pygame.K_a):
                self._cycle(-1)

    def draw(self, surface):
        self._bg(surface)
        w, h = surface.get_size()
        cx = w // 2
        key = settings.CAR_ORDER[self.index]
        spec = settings.CARS[key]
        save = self.game.save
        unlocked = save.is_car_unlocked(key)

        draw_text(surface, "GARAGE", (cx, int(h * 0.10)), size=48,
                  color=settings.COL_TEXT, bold=True, center=True, shadow=True)

        panel = pygame.Rect(cx - 400, int(h * 0.18), 800, int(h * 0.60))
        draw_panel(surface, panel, radius=22)

        draw_text(surface, spec["name"], (cx, panel.y + 34), size=38,
                  color=spec["color"] if unlocked else settings.COL_TEXT_DIM,
                  bold=True, center=True)
        draw_text(surface, spec["category"], (cx, panel.y + 70), size=16,
                  color=settings.COL_ACCENT, bold=True, center=True)

        # rotating preview
        preview = Car(spec, (0, 0), self._preview_angle)
        body = preview._body_surface(4.4)
        body = pygame.transform.rotozoom(body, -self._preview_angle, 1.0)
        car_pos = (cx, panel.y + 168)
        surface.blit(body, body.get_rect(center=car_pos))
        if self._shine > 0.02:
            r = int(90 * (1.2 - self._shine))
            glow = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(glow, (255, 255, 255, int(90 * self._shine)), (r, r), r)
            surface.blit(glow, glow.get_rect(center=car_pos))

        # stat bars (animated)
        labels = [("TOP SPEED", "top_speed"), ("ACCELERATION", "acceleration"),
                  ("HANDLING", "handling"), ("GRIP", "grip"), ("NITRO", "nitro")]
        bx = cx - 210
        by = panel.y + 236
        for i, (lab, skey) in enumerate(labels):
            y = by + i * 34
            draw_text(surface, lab, (bx, y + 8), size=16, color=settings.COL_TEXT,
                      bold=True, midleft=True)
            track = pygame.Rect(bx + 180, y, 240, 16)
            pygame.draw.rect(surface, settings.COL_NITRO_EMPTY, track, border_radius=8)
            val = clamp(self._shown[skey], 0.02, 1.0)
            col = settings.COL_NITRO if skey == "nitro" else settings.COL_ACCENT
            pygame.draw.rect(surface, col, pygame.Rect(track.x, track.y,
                             int(track.width * val), track.height), border_radius=8)

        draw_text(surface, spec["tagline"], (cx, panel.bottom - 30), size=15,
                  color=settings.COL_TEXT_DIM, center=True)

        if not unlocked:
            veil = pygame.Surface(panel.size, pygame.SRCALPHA)
            veil.fill((8, 10, 16, 150))
            surface.blit(veil, panel.topleft)
            draw_text(surface, "LOCKED", (cx, panel.centery - 12), size=40,
                      color=settings.COL_TEXT, bold=True, center=True)
            draw_text(surface, save.car_unlock_hint(key), (cx, panel.centery + 26),
                      size=17, color=settings.COL_ACCENT, center=True)
        elif key == save.selected_car:
            draw_text(surface, "● EQUIPPED", (cx, panel.bottom + 4), size=15,
                      color=settings.COL_GOOD, center=True)

        draw_text(surface, f"{self.index + 1} / {len(settings.CAR_ORDER)}",
                  (cx, int(h * 0.795)), size=15, color=settings.COL_TEXT_DIM, center=True)
        for b in self.buttons:
            b.draw(surface)


# =========================================================================== #
class SettingsScreen(BaseScreen):
    def layout(self):
        w, h = self.game.screen.get_size()
        s = self.game.save.settings
        cx = w // 2
        x = cx - 320
        y0 = int(h * 0.24)
        row_h = 60
        self.widgets = [
            Slider("MASTER VOLUME", pygame.Rect(x, y0, 640, 44), s.volume_master,
                   on_change=self._set_master),
            Slider("SFX VOLUME", pygame.Rect(x, y0 + row_h, 640, 44), s.volume_sfx,
                   on_change=self._set_sfx),
            Toggle("FULLSCREEN", pygame.Rect(x, y0 + row_h * 2, 640, 44), s.fullscreen,
                   on_change=self._set_fullscreen),
            Toggle("SHOW FPS / DEBUG", pygame.Rect(x, y0 + row_h * 3, 640, 44), s.show_fps,
                   on_change=self._set_fps),
            Toggle("SCREEN SHAKE", pygame.Rect(x, y0 + row_h * 4, 640, 44), s.screen_shake,
                   on_change=self._set_shake),
        ]
        self.buttons = [
            Button("BACK", pygame.Rect(30, 30, 120, 46), on_click=self._back, size=20),
            Button("DONE", pygame.Rect(cx - 150, int(h * 0.8), 300, 56),
                   on_click=self._back, primary=True, size=24),
        ]

    def _set_master(self, v):
        self.game.save.settings.volume_master = v
        self.game.audio.apply_volumes()

    def _set_sfx(self, v):
        self.game.save.settings.volume_sfx = v
        self.game.audio.apply_volumes()

    def _set_fullscreen(self, v):
        self.game.save.settings.fullscreen = v
        self.game.apply_display_mode()

    def _set_fps(self, v):
        self.game.save.settings.show_fps = v

    def _set_shake(self, v):
        self.game.save.settings.screen_shake = v

    def _back(self):
        self.game.audio.play("click")
        self.game.save.save()
        self.game.goto_menu()

    def draw(self, surface):
        self._bg(surface)
        w, h = surface.get_size()
        draw_text(surface, "SETTINGS", (w // 2, int(h * 0.12)), size=54,
                  color=settings.COL_TEXT, bold=True, center=True, shadow=True)
        panel = pygame.Rect(w // 2 - 380, int(h * 0.19), 760, int(h * 0.56))
        draw_panel(surface, panel, radius=22)
        for wdg in self.widgets:
            wdg.draw(surface)
        for b in self.buttons:
            b.draw(surface)


# =========================================================================== #
class PauseOverlay:
    def __init__(self, game):
        self.game = game
        self.buttons: list[Button] = []
        self.layout()

    def layout(self):
        w, h = self.game.screen.get_size()
        cx = w // 2
        bw, bh, gap = 300, 52, 14
        top = int(h * 0.40)
        labels = [
            ("RESUME", self.game.resume_race, True),
            ("RESTART", self.game.restart_race, False),
            ("TRACK SELECT", self.game.quit_to_track_select, False),
            ("MAIN MENU", self.game.quit_to_menu, False),
        ]
        self.buttons = [
            Button(lab, pygame.Rect(cx - bw // 2, top + i * (bh + gap), bw, bh),
                   on_click=self._wrap(cb), primary=primary, size=22)
            for i, (lab, cb, primary) in enumerate(labels)
        ]

    def _wrap(self, cb):
        def inner():
            self.game.audio.play("click")
            cb()
        return inner

    def handle_event(self, event):
        for b in self.buttons:
            b.handle_event(event)

    def update(self, dt):
        mouse = pygame.mouse.get_pos()
        for b in self.buttons:
            if b.update(mouse, dt):
                self.game.audio.play("click", volume=0.3)

    def draw(self, surface):
        w, h = surface.get_size()
        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        veil.fill((6, 8, 14, 205))
        surface.blit(veil, (0, 0))
        draw_text(surface, "PAUSED", (w // 2, int(h * 0.26)), size=68,
                  color=settings.COL_TEXT, bold=True, center=True, shadow=True)
        if self.game.race:
            draw_text(surface, self.game.race.track_name, (w // 2, int(h * 0.33)),
                      size=20, color=settings.COL_TEXT_DIM, center=True)
        for b in self.buttons:
            b.draw(surface)


# =========================================================================== #
class ResultsOverlay:
    def __init__(self, game, race):
        self.game = game
        self.race = race
        self.t = 0.0
        self.buttons: list[Button] = []
        self.layout()

    def layout(self):
        w, h = self.game.screen.get_size()
        cx = w // 2
        nxt = next_track_id(self.race.track_id)
        has_next = nxt is not None and self.game.save.is_track_unlocked(nxt)
        specs = [("RACE AGAIN", self._again, True)]
        if has_next:
            specs.append(("NEXT TRACK", self._next, False))
        specs.append(("TRACK SELECT", self._select, False))
        specs.append(("MAIN MENU", self._menu, False))
        n = len(specs)
        bw = min(260, (w - 80) / n - 16)
        total = n * bw + (n - 1) * 16
        x0 = cx - total / 2
        self.buttons = [
            Button(lab, pygame.Rect(x0 + i * (bw + 16), h - 78, bw, 52),
                   on_click=self._wrap(cb), primary=primary, size=20)
            for i, (lab, cb, primary) in enumerate(specs)
        ]

    def _wrap(self, cb):
        def inner():
            self.game.audio.play("click")
            cb()
        return inner

    def _again(self):
        self.game.restart_race()

    def _next(self):
        nxt = next_track_id(self.race.track_id)
        if nxt:
            self.game.choose_track(nxt, start_now=True)

    def _select(self):
        self.game.quit_to_track_select()

    def _menu(self):
        self.game.quit_to_menu()

    def handle_event(self, event):
        for b in self.buttons:
            b.handle_event(event)

    def update(self, dt):
        self.t += dt
        mouse = pygame.mouse.get_pos()
        for b in self.buttons:
            if b.update(mouse, dt):
                self.game.audio.play("click", volume=0.3)

    def draw(self, surface):
        w, h = surface.get_size()
        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        veil.fill((6, 8, 14, 220))
        surface.blit(veil, (0, 0))
        cx = w // 2
        res = self.race.result or {}
        news = self.race.result_news or {}
        pos = res.get("position", 1)
        won = pos == 1

        draw_text(surface, "RACE COMPLETE", (cx, int(h * 0.09)), size=44,
                  color=settings.COL_TEXT, bold=True, center=True, shadow=True)
        draw_text(surface, res.get("track_name", self.race.track_name),
                  (cx, int(h * 0.15)), size=22, color=settings.COL_ACCENT_2,
                  bold=True, center=True)
        if won:
            g = 1.0 + 0.06 * math.sin(self.t * 4)
            draw_text(surface, "★  VICTORY  ★", (cx, int(h * 0.225)), size=int(44 * g),
                      color=settings.COL_ACCENT, bold=True, center=True, shadow=True)
        else:
            draw_text(surface, f"P{pos}", (cx, int(h * 0.225)), size=40,
                      color=settings.COL_TEXT, bold=True, center=True)

        panel = pygame.Rect(cx - 300, int(h * 0.29), 600, int(h * 0.40))
        draw_panel(surface, panel, radius=20)
        rows = [
            ("POSITION", f"{pos} / {self.race.car_count}"),
            ("TOTAL TIME", format_time(res.get("total_time"))),
            ("BEST LAP", format_time(res.get("best_lap"))),
        ]
        for i, (lab, val) in enumerate(rows):
            y = panel.y + 34 + i * 46
            draw_text(surface, lab, (panel.x + 36, y), size=18,
                      color=settings.COL_TEXT_DIM, bold=True, midleft=True)
            draw_text(surface, val, (panel.right - 36, y), size=26,
                      color=settings.COL_TEXT, bold=True, right=True)
        laps = res.get("laps", [])
        for i, lt in enumerate(laps):
            y = panel.y + 34 + 3 * 46 + i * 24
            draw_text(surface, f"LAP {i + 1}", (panel.x + 36, y), size=15,
                      color=settings.COL_TEXT_DIM, midleft=True)
            draw_text(surface, format_time(lt), (panel.right - 36, y), size=16,
                      color=settings.COL_TEXT_DIM, right=True)

        # feedback tags
        tags = []
        if news.get("track_record"):
            tags.append(("NEW TRACK RECORD", settings.COL_ACCENT))
        elif news.get("best_lap"):
            tags.append(("NEW BEST LAP", settings.COL_ACCENT))
        if news.get("best_total"):
            tags.append(("NEW BEST TIME", settings.COL_GOOD))
        y = panel.bottom + 20
        for txt, col in tags:
            draw_text(surface, txt, (cx, y), size=20, color=col, bold=True, center=True)
            y += 26

        for cid in news.get("unlocked_cars", []):
            draw_text(surface, f"UNLOCKED:  {cid}", (cx, y), size=20,
                      color=settings.COL_GOOD, bold=True, center=True)
            y += 26
        for tid in news.get("unlocked_tracks", []):
            draw_text(surface, f"NEW TRACK UNLOCKED:  {get_track(tid).name}", (cx, y),
                      size=20, color=settings.COL_GOOD, bold=True, center=True)
            y += 26

        for b in self.buttons:
            b.draw(surface)
