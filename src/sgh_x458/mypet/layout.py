"""MyPet-specific ROM and RAM locations."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
MANIFEST = ASSETS / "manifest.json"
GAME_ENTRY = 0x238023
CALLBACK = GAME_ENTRY & ~1

# The pet state sits just after the two earlier games' state blocks.
STATE_BASE = 0x0103F740
SAVE_BUFFER = 0x12DF454

# Bank boundaries verified against the X458ZCEK1 image.
IMAGE_START, AUDIO_START, AUDIO_END, DATA_END = 0x61ABB8, 0x653DA9, 0x65C3E3, 0x65D000
SHARED_IMAGE_START = 0x5860F0
