"""X-Fighter assets, firmware state addresses and launch options."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
MANIFEST = ASSETS / "manifest.json"
STATE = 0x0103F4CC
BATTLE_KEY = STATE + 0x98
DEFAULT_BOMBS = 3
MAX_BOMBS = 10
