"""X-Fighter asset paths, ROM banks, RAM state addresses and launch limits."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
MANIFEST = ASSETS / "manifest.json"
GAME_ENTRY = 0x235A35
IMAGE_START, AUDIO_START, AUDIO_END, DATA_END = 0x59DCD0, 0x5A4FEC, 0x5ABDF5, 0x5ADDD8
STATE = 0x0103F4CC
BATTLE_KEY = STATE + 0x98
DEFAULT_BOMBS = 3
MAX_BOMBS = 10
