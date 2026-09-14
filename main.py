"""Marco Racing - entry point.

Run with:  python main.py
"""

from __future__ import annotations

import sys


def _fail(message: str, exc: Exception | None = None) -> None:
    print("=" * 60)
    print("Marco Racing could not start.")
    print(message)
    if exc is not None:
        print(f"\n{type(exc).__name__}: {exc}")
    print("=" * 60)
    sys.exit(1)


def main() -> None:
    try:
        import pygame  # noqa: F401
    except ImportError as exc:
        _fail("Pygame is not installed.  Install the dependencies with:\n"
              "    pip install -r requirements.txt", exc)

    from src.game import main as run_game

    run_game()


if __name__ == "__main__":
    main()
