# 🏁 Marco Racing

A **2D top-down arcade racer** built from scratch with Python + Pygame.

**10 circuits · 5 cars · 4 AI skill levels · unlock-based progression.**
Runs with **zero external assets** — every graphic and every sound is generated
procedurally at startup.

```bash
pip install -r requirements.txt
python main.py
```

---

## ✨ Features

### Racing
- **Arcade driving model** — separate longitudinal / lateral velocity, speed
  dependent steering, grip, drift, tyre scrub, handbrake slides, **nitro** boost.
- **10 hand-authored circuits**, each with its own layout, length, width,
  difficulty (★–★★★★★) and visual theme: *City Loop, Industrial, Coastal,
  Mountain, Night District, Desert Run, Tech Circuit, Grand Prix, Storm,
  Marco GP*.
- **Highly readable track** — ground → barrier → run-off shoulder (grass /
  gravel / sand / concrete) → kerb → asphalt, with procedural asphalt texture,
  continuous corner kerbs, lane lines, checkered start line and checkpoint
  markers.
- **Solid barrier collision** — fully analytic (nearest centre-line segment +
  signed offset + local normal), so it is immediate, predictable and never
  tunnels, even at top speed. Kerbs cost a little grip; the grass costs a lot;
  the wall pushes you back and scrubs your speed while letting you scrape along.
- **Competitive AI** at **EASY / NORMAL / HARD / ELITE** — drives a racing line,
  brakes *before* corners based on how much faster than the corner speed it is,
  gets back on the power at the exit, picks its own line, races for position
  and makes small, believable mistakes. Each circuit picks an appropriate
  field.
- **Overtaking** — opponents move off-line to pass or avoid a clip, with
  momentum-exchange contact.
- Countdown grid start, 3 laps, checkpoints, live total / lap / best-lap
  timers, `NEW BEST LAP!` / `NEW TRACK RECORD`, smooth chase camera with speed
  zoom and collision shake, tyre marks, smoke, nitro flames, dust.

### Front-end & progression
- Animated **main menu** with a career summary (wins / best lap / cars / tracks).
- **Track Select** screen with a live 2D **preview generated from each layout**,
  difficulty stars, per-track best lap and locked/unlocked state.
- **Garage** — 5 cars (MARCO GT / SPORT / GRIP / TURBO / RALLY), each with a
  category, description, rotating preview and **animated TOP SPEED /
  ACCELERATION / HANDLING / GRIP / NITRO bars** that reflect the real physics.
- **Unlock system** — start with MARCO GT; win races to unlock SPORT (1),
  GRIP (3), TURBO (5), RALLY (8). Finish a circuit to unlock the next one.
- **Settings** — master / SFX volume, fullscreen, FPS+debug overlay, screen
  shake. All saved.
- Pause (Resume / Restart / Track Select / Main Menu) and a Results screen
  (position, total, best lap, per-lap splits, records, unlocks) with
  **RACE AGAIN / NEXT TRACK / TRACK SELECT / MAIN MENU**.

### Under the hood
- Frame-rate-independent fixed-timestep physics.
- **Save system** — JSON in `data/`, auto-created, corruption-safe, and it
  **migrates old (v1) saves** without losing anything.
- Procedural audio: engine, skid, countdown, collision, nitro, UI clicks,
  finish jingle. Drop a `.wav`/`.ogg` into `assets/sounds/` and it is used
  automatically.
- Debug overlay (`Settings ▸ Show FPS`) draws the centre line, collision
  boundary, checkpoints, AI target points, projected position and current
  surface / side.
- Resizable window, fullscreen toggle (`F11`).

---

## 📸 Screenshots

*(placeholder — run the game and grab your own!)*

| Menu | Track Select | Race | Results |
|------|--------------|------|---------|
| _—_ | _—_ | _—_ | _—_ |

---

## 🎮 Controls

| Action | Keys |
|--------|------|
| Accelerate | `W` / `↑` |
| Brake / reverse | `S` / `↓` |
| Steer | `A` `D` / `←` `→` |
| Handbrake | `Space` |
| Nitro | `Shift` |
| Pause | `Esc` |
| Quick restart | `Ctrl` + `R` |
| Confirm / Play | `Enter` |
| Navigate menus / grids | Mouse, or arrows + `Enter` |
| Toggle fullscreen | `F11` (outside a race) |

---

## 🗂 Project structure

```
marco-racing/
├── main.py                 # entry point only
├── requirements.txt
├── data/                   # save.json is created here at runtime
├── assets/                 # optional — game runs fully without them
│   └── sounds/             # drop-in .wav/.ogg override the synthesised audio
├── tests/
│   └── test_smoke.py       # headless: registry, 10 layouts, flow, save, unlocks
└── src/
    ├── game.py             # window, main loop, fixed timestep, screen routing
    ├── race.py             # race simulation, effects, results
    ├── track.py            # builds a circuit from a definition: geometry,
    │                       #   analytic collision, curvature, themed rendering
    ├── tracks/             # the track DATA system
    │   ├── base.py         #   TrackDefinition + visual themes
    │   ├── library.py      #   the 10 circuits
    │   └── registry.py     #   ordered lookup
    ├── track_preview.py    # 2D preview thumbnails from a layout
    ├── car.py              # reusable Car: state + procedural art
    ├── player.py           # human input + nitro
    ├── ai.py               # opponent AI: racing line, braking, personalities
    ├── physics.py          # arcade motion model + collision response
    ├── camera.py           # smooth chase camera
    ├── particles.py        # particles + skid marks
    ├── ui.py               # buttons, sliders, toggles, HUD
    ├── menu.py             # main menu, track select, garage, settings, overlays
    ├── settings.py         # constants, palette, car definitions, unlock rules
    ├── save_data.py        # JSON save (v2) + migration + settings
    └── utils.py            # maths, fonts, drawing helpers
```

```
Game
├── MainMenu ─ TrackSelect ─ Garage ─ Settings
└── Race
    ├── Player  ·  AICar × 3
    ├── Track (Camera, ParticleSystem, HUD)
    ├── PauseOverlay
    └── ResultsOverlay
```

---

## 🧪 Tests

```bash
python -m tests.test_smoke      # headless (dummy SDL drivers), or: pytest -q
```

Covers: the 10-track registry, every layout being drivable, the
menu → track select → garage → race → results flow, a full simulated race,
save migration + corruption recovery, and unlock progression.

---

## 🌐 Web build

The game also runs in the browser via [pygbag](https://github.com/pygame-web/pygbag),
which compiles the same source to WebAssembly. `main.py` and `Game.run()` are
asyncio-based specifically so the same entry point works unchanged on both
desktop (`asyncio.run`) and the web (pygbag's own event loop).

```bash
pip install pygbag
python -m pygbag --build main.py     # writes static output to build/web/
```

`build/web/` is generated output and is not committed (see `.gitignore`).
Serve it locally with `python -m pygbag main.py` (opens a dev server +
browser), or deploy the `build/web/` folder to any static host — a
`vercel.json` is included for one-command deploys to Vercel
(`vercel --prod`, with `outputDirectory` already pointed at `build/web`).

---

## 🛠 Technologies

Python 3.10+ · Pygame 2 · pygbag (web build) · nothing else.

---

## 📌 Project status

**V2 — playable and complete.** All systems implemented and tested end to end.
Later ideas: more cars, ghost/replay laps, gamepad support, weather.
