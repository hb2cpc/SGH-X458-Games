"""SpaceWar-specific ROM and RAM locations and launch options."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
MANIFEST = ASSETS / "manifest.json"
GAME_ENTRY = 0x2379DD
IMAGE_START, AUDIO_START, AUDIO_END, DATA_END = 0x5ADDD8, 0x6123E5, 0x61A8E3, 0x61ABB8
STATE_BASE = 0x0103F698
INITIAL_DATA = ((0x6AD00C, 0x6AD8CC, 0x0103EEC0),)

SCENES = ("menu", "stage")
ITEMS = ("none", "boost", "slow", "life")
STAGES = tuple(range(1, 11))
DEFAULT_LIVES = 3
MAX_LIVES = 100
