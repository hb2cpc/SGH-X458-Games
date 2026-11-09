"""Offline firmware extraction, translation and verification tools.

Shared modules live here; game-specific scripts live in the game subpackages.
Run them from the project root, for example ``python -m tools.spacewar.verify``.
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
