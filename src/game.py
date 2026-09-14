"""Top-level application: window, main loop, fixed-timestep, screen routing.

Flow:  MENU -> TRACK SELECT -> GARAGE (car select) -> RACE -> RESULTS -> ...
"""

from __future__ import annotations

import pygame

from . import settings
from .audio import Audio
from .menu import (Garage, MainMenu, PauseOverlay, ResultsOverlay,
                   SettingsScreen, TrackSelect)
from .race import Race
from .save_data import SaveData
from .utils import draw_text


class Game:
    def __init__(self):
        pygame.mixer.pre_init(22050, -16, 2, 512)
        pygame.init()
        try:
            pygame.mixer.init()
        except pygame.error:
            pass

        self.save = SaveData()
        self.audio = Audio(self.save.settings)

        self.windowed_size = (settings.BASE_WIDTH, settings.BASE_HEIGHT)
        self.screen = None
        self.apply_display_mode(initial=True)
        pygame.display.set_caption(settings.GAME_TITLE)

        self.clock = pygame.time.Clock()
        self.running = True
        self._accumulator = 0.0

        self.mode = "menu"
        self.scene = MainMenu(self)
        self.race: Race | None = None
        self.overlay = None
        self._results_shown = False

    # ================================================================ #
    #  Display
    # ================================================================ #
    def apply_display_mode(self, initial=False):
        if self.save.settings.fullscreen:
            flags = pygame.FULLSCREEN | pygame.SCALED
            size = (settings.BASE_WIDTH, settings.BASE_HEIGHT)
        else:
            flags = pygame.RESIZABLE
            size = self.windowed_size
        try:
            self.screen = pygame.display.set_mode(size, flags, vsync=1)
        except pygame.error:
            self.screen = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        if not initial:
            self._relayout()

    def _relayout(self):
        for obj in (self.scene, self.overlay):
            if obj is not None and hasattr(obj, "layout"):
                try:
                    obj.layout()
                except Exception:
                    pass
        if self.race is not None:
            self.race.resize(self.screen.get_size())

    def handle_resize(self, size):
        size = (max(settings.MIN_WIDTH, size[0]), max(settings.MIN_HEIGHT, size[1]))
        if not self.save.settings.fullscreen:
            self.windowed_size = size
            try:
                self.screen = pygame.display.set_mode(size, pygame.RESIZABLE, vsync=1)
            except pygame.error:
                self.screen = pygame.display.set_mode(size, pygame.RESIZABLE)
        self._relayout()

    # ================================================================ #
    #  Routing
    # ================================================================ #
    def goto_menu(self):
        self._teardown_race()
        self.mode = "menu"
        self.scene = MainMenu(self)
        self.overlay = None

    def goto_track_select(self):
        self._teardown_race()
        self.mode = "track_select"
        self.scene = TrackSelect(self)
        self.overlay = None

    def goto_garage(self, context="menu"):
        self.mode = "garage"
        self.scene = Garage(self, context=context)
        self.overlay = None

    def goto_settings(self):
        self.mode = "settings"
        self.scene = SettingsScreen(self)

    def choose_track(self, track_id, start_now=False):
        self.save.selected_track = track_id
        self.save.save()
        if start_now:
            self.start_race()
        else:
            self.goto_garage(context="prerace")

    def start_race(self):
        self._teardown_race()
        try:
            self.race = Race(self, self.save.selected_car, self.save.selected_track, self.save)
        except Exception as exc:
            print(f"[game] failed to start race: {exc}")
            import traceback
            traceback.print_exc()
            self.goto_menu()
            return
        self.mode = "race"
        self.scene = None
        self.overlay = None
        self._results_shown = False
        self._accumulator = 0.0

    def pause_race(self):
        if (self.mode == "race" and self.overlay is None and self.race
                and self.race.state != "finished"):
            self.overlay = PauseOverlay(self)
            self.audio.play("click", volume=0.4)
            self.audio.stop_all_loops()

    def resume_race(self):
        if isinstance(self.overlay, PauseOverlay):
            self.overlay = None
            if self.race:
                self.audio.start_engine()

    def restart_race(self):
        self.audio.stop_all_loops()
        self.start_race()

    def quit_to_menu(self):
        self.goto_menu()

    def quit_to_track_select(self):
        self.goto_track_select()

    def _teardown_race(self):
        if self.race is not None:
            self.audio.stop_all_loops()
        self.race = None
        self.overlay = None

    def quit(self):
        self.running = False

    # ================================================================ #
    #  Loop
    # ================================================================ #
    def run(self):
        try:
            while self.running:
                dt = min(self.clock.tick(settings.TARGET_FPS) / 1000.0, settings.MAX_FRAME_TIME)
                self._handle_events()
                self._update(dt)
                self._draw()
            self._shutdown()
        except Exception:
            import traceback
            traceback.print_exc()
            self._shutdown()
            raise

    def _shutdown(self):
        try:
            self.save.save()
        except Exception:
            pass
        try:
            self.audio.stop_all_loops()
        except Exception:
            pass
        pygame.quit()

    # ------------------------------------------------------------------ #
    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return
            if event.type == pygame.VIDEORESIZE:
                self.handle_resize(event.size)
                continue
            if event.type == pygame.WINDOWFOCUSLOST:
                self.pause_race()
                continue
            if event.type == pygame.KEYDOWN and self._handle_keydown(event):
                continue

            if self.overlay is not None:
                self.overlay.handle_event(event)
            elif self.scene is not None:
                self.scene.handle_event(event)

    def _handle_keydown(self, event):
        key = event.key
        if key == pygame.K_ESCAPE:
            if self.mode == "race":
                if isinstance(self.overlay, PauseOverlay):
                    self.resume_race()
                elif self.overlay is None:
                    self.pause_race()
            elif self.mode == "garage":
                self.audio.play("click")
                if getattr(self.scene, "context", "menu") == "prerace":
                    self.goto_track_select()
                else:
                    self.goto_menu()
            elif self.mode == "settings":
                self.audio.play("click")
                self.save.save()
                self.goto_menu()
            elif self.mode == "track_select":
                self.audio.play("click")
                self.goto_menu()
            elif self.mode == "menu":
                self.running = False
            return True

        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if isinstance(self.overlay, ResultsOverlay):
                self.restart_race()
            elif isinstance(self.overlay, PauseOverlay):
                self.resume_race()
            elif self.mode == "menu":
                self.goto_track_select()
            elif self.mode == "track_select" and hasattr(self.scene, "_confirm"):
                self.scene._confirm()
            elif self.mode == "garage" and hasattr(self.scene, "_select"):
                self.scene._select()
            else:
                return False
            return True

        if key == pygame.K_F11 and self.mode != "race":
            self.save.settings.fullscreen = not self.save.settings.fullscreen
            self.apply_display_mode()
            return True
        if key == pygame.K_r and self.mode == "race" and event.mod & pygame.KMOD_CTRL:
            self.restart_race()
            return True
        return False

    # ------------------------------------------------------------------ #
    def _update(self, dt):
        if self.mode == "race" and self.race is not None:
            if self.overlay is None:
                keys = pygame.key.get_pressed()
                self._accumulator += dt
                steps = 0
                while self._accumulator >= settings.FIXED_DT and steps < 8:
                    self.race.update(settings.FIXED_DT, keys)
                    self._accumulator -= settings.FIXED_DT
                    steps += 1
                if (self.race.state == "finished" and self.race.result is not None
                        and self.race._finish_delay > 1.4 and not self._results_shown):
                    self.overlay = ResultsOverlay(self, self.race)
                    self._results_shown = True
            else:
                self.overlay.update(dt)
        elif self.scene is not None:
            self.scene.update(dt)

    # ------------------------------------------------------------------ #
    def _draw(self):
        surface = self.screen
        if self.mode == "race" and self.race is not None:
            self.race.draw(surface)
            if self.overlay is not None:
                self.overlay.draw(surface)
        elif self.scene is not None:
            self.scene.draw(surface)

        if self.save.settings.show_fps:
            draw_text(surface, f"{self.clock.get_fps():4.0f} FPS",
                      (surface.get_width() - 12, surface.get_height() - 20),
                      size=16, color=(120, 255, 160), right=True)

        pygame.display.flip()


def main():
    Game().run()
