"""Procedural sound system.

No external audio files are required.  Every sound is synthesised at startup
into a raw 16-bit buffer and wrapped in a :class:`pygame.mixer.Sound`.  If the
mixer cannot be initialised (no audio device, head-less CI, ...) the whole
module degrades to silent no-ops.

If a matching ``.wav`` / ``.ogg`` file exists in ``assets/sounds/`` it is used
instead of the synthesised version, so real assets can be dropped in later.
"""

from __future__ import annotations

import array
import math
import os
import random

import pygame

from . import settings

SAMPLE_RATE = 22050


def _envelope(i: int, total: int, attack: float, release: float) -> float:
    a = int(total * attack) or 1
    r = int(total * release) or 1
    if i < a:
        return i / a
    if i > total - r:
        return max(0.0, (total - i) / r)
    return 1.0


def _tone(freq, duration, *, vol=0.5, kind="sine", attack=0.01, release=0.2, sweep=0.0):
    n = int(SAMPLE_RATE * duration)
    buf = array.array("h")
    for i in range(n):
        t = i / SAMPLE_RATE
        f = freq + sweep * (i / max(1, n))
        phase = 2 * math.pi * f * t
        if kind == "sine":
            s = math.sin(phase)
        elif kind == "square":
            s = 1.0 if math.sin(phase) >= 0 else -1.0
        elif kind == "saw":
            s = 2.0 * ((f * t) % 1.0) - 1.0
        elif kind == "noise":
            s = random.uniform(-1.0, 1.0)
        else:
            s = math.sin(phase)
        s *= _envelope(i, n, attack, release) * vol
        v = int(max(-1.0, min(1.0, s)) * 32767)
        buf.append(v)
        buf.append(v)
    return buf


def _mix(*buffers):
    length = max(len(b) for b in buffers)
    out = array.array("h", [0]) * length
    for b in buffers:
        for i in range(len(b)):
            out[i] = max(-32767, min(32767, out[i] + b[i]))
    return out


def _engine_loop():
    """A short, seamlessly-looping low engine drone."""
    duration = 0.35
    n = int(SAMPLE_RATE * duration)
    base = 70.0
    buf = array.array("h")
    for i in range(n):
        t = i / SAMPLE_RATE
        # make it loop cleanly: use an integer number of cycles
        s = 0.0
        s += 0.55 * (2.0 * ((base * t) % 1.0) - 1.0)          # saw fundamental
        s += 0.25 * math.sin(2 * math.pi * base * 2 * t)       # 2nd harmonic
        s += 0.12 * math.sin(2 * math.pi * base * 3 * t)       # 3rd harmonic
        s += 0.06 * random.uniform(-1.0, 1.0)                  # grit
        s *= 0.5
        v = int(max(-1.0, min(1.0, s)) * 32767)
        buf.append(v)
        buf.append(v)
    return buf


class _NullSound:
    def play(self, *a, **k):
        return None

    def stop(self):
        pass

    def set_volume(self, *a):
        pass

    def get_num_channels(self):
        return 0


class Audio:
    def __init__(self, save_settings):
        self.enabled = False
        self.settings = save_settings
        self.sounds: dict[str, object] = {}
        self._engine_channel = None
        self._skid_channel = None
        self._engine_playing = False
        self._skid_playing = False

        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2, buffer=512)
            pygame.mixer.set_num_channels(24)
            pygame.mixer.set_reserved(2)  # channels 0 & 1 for engine + skid loops
            self.enabled = True
        except pygame.error as exc:
            print(f"[audio] mixer unavailable, running silent: {exc}")
            self.enabled = False

        self._build_sounds()
        self._engine_channel = self._reserve_channel(0)
        self._skid_channel = self._reserve_channel(1)
        self.apply_volumes()

    # ------------------------------------------------------------------ #
    def _reserve_channel(self, idx):
        if not self.enabled:
            return None
        try:
            return pygame.mixer.Channel(idx)
        except pygame.error:
            return None

    def _load_or_make(self, name, factory):
        for ext in (".ogg", ".wav"):
            path = os.path.join(settings.SOUNDS_DIR, name + ext)
            if os.path.exists(path):
                try:
                    return pygame.mixer.Sound(path)
                except pygame.error:
                    pass
        try:
            return pygame.mixer.Sound(buffer=factory().tobytes())
        except (pygame.error, ValueError) as exc:
            print(f"[audio] failed to build sound '{name}': {exc}")
            return _NullSound()

    def _build_sounds(self):
        if not self.enabled:
            self.sounds = {k: _NullSound() for k in
                           ("click", "beep", "go", "engine", "skid", "hit", "nitro", "finish")}
            return
        self.sounds = {
            "click": self._load_or_make("click", lambda: _tone(660, 0.05, vol=0.35, kind="square", release=0.6)),
            "beep": self._load_or_make("beep", lambda: _tone(880, 0.18, vol=0.4, kind="sine", release=0.5)),
            "go": self._load_or_make("go", lambda: _tone(1320, 0.45, vol=0.5, kind="sine", release=0.4)),
            "engine": self._load_or_make("engine", _engine_loop),
            "skid": self._load_or_make("skid", lambda: _tone(0, 0.5, vol=0.25, kind="noise", attack=0.05, release=0.3)),
            "hit": self._load_or_make("hit", lambda: _mix(
                _tone(120, 0.25, vol=0.5, kind="noise", attack=0.001, release=0.6),
                _tone(80, 0.25, vol=0.4, kind="square", release=0.7))),
            "nitro": self._load_or_make("nitro", lambda: _tone(300, 0.5, vol=0.35, kind="saw",
                                                              attack=0.02, release=0.5, sweep=500)),
            "finish": self._load_or_make("finish", lambda: _mix(
                _tone(523, 0.6, vol=0.32, release=0.5),
                _tone(659, 0.6, vol=0.30, release=0.5),
                _tone(784, 0.6, vol=0.28, release=0.5))),
        }

    # ------------------------------------------------------------------ #
    def apply_volumes(self):
        master = float(self.settings.volume_master)
        sfx = float(self.settings.volume_sfx) * master
        for name, snd in self.sounds.items():
            try:
                snd.set_volume(sfx)
            except Exception:
                pass
        try:
            pygame.mixer.music.set_volume(master * 0.5)
        except Exception:
            pass

    def play(self, name, volume=1.0):
        snd = self.sounds.get(name)
        if snd is None:
            return
        try:
            ch = snd.play()
            if ch is not None and volume != 1.0:
                base = float(self.settings.volume_sfx) * float(self.settings.volume_master)
                ch.set_volume(base * volume)
        except Exception:
            pass

    # -- looping engine ------------------------------------------------- #
    def start_engine(self):
        if not self.enabled or self._engine_channel is None or self._engine_playing:
            return
        try:
            self._engine_channel.play(self.sounds["engine"], loops=-1)
            self._engine_playing = True
        except Exception:
            pass

    def update_engine(self, throttle: float, speed_frac: float):
        if not self._engine_playing or self._engine_channel is None:
            return
        base = float(self.settings.volume_sfx) * float(self.settings.volume_master)
        vol = base * (0.18 + 0.55 * speed_frac + 0.15 * max(0.0, throttle))
        try:
            self._engine_channel.set_volume(min(1.0, vol))
        except Exception:
            pass

    def stop_engine(self):
        if self._engine_channel is not None:
            try:
                self._engine_channel.stop()
            except Exception:
                pass
        self._engine_playing = False

    # -- looping skid ------------------------------------------------- #
    def set_skid(self, active: bool, intensity: float = 1.0):
        if self._skid_channel is None:
            return
        if active and not self._skid_playing:
            try:
                self._skid_channel.play(self.sounds["skid"], loops=-1)
                self._skid_playing = True
            except Exception:
                pass
        elif not active and self._skid_playing:
            try:
                self._skid_channel.fadeout(120)
            except Exception:
                pass
            self._skid_playing = False
        if self._skid_playing:
            base = float(self.settings.volume_sfx) * float(self.settings.volume_master)
            try:
                self._skid_channel.set_volume(min(1.0, base * (0.3 + 0.7 * intensity)))
            except Exception:
                pass

    def stop_all_loops(self):
        self.stop_engine()
        self.set_skid(False)
