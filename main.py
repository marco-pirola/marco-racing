"""Marco Racing - entry point.

Run on desktop with:  python main.py
Run in the browser via pygbag:  pygbag .

This module is intentionally asyncio-based: pygbag drives the game through
its own asyncio event loop when built for the web, and ``asyncio.run`` is a
transparent no-op wrapper for the same code on desktop.
"""

from __future__ import annotations

import asyncio
import sys


def _fail(message: str, exc: Exception | None = None) -> None:
    print("=" * 60)
    print("Marco Racing could not start.")
    print(message)
    if exc is not None:
        print(f"\n{type(exc).__name__}: {exc}")
    print("=" * 60)
    sys.exit(1)


async def main() -> None:
    try:
        import pygame  # noqa: F401
    except ImportError as exc:
        _fail("Pygame is not installed.  Install the dependencies with:\n"
              "    pip install -r requirements.txt", exc)
        return

    from src.game import main as run_game

    await run_game()


if __name__ == "__main__":
    asyncio.run(main())
