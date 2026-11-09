"""Offline reference execution for G94 SpaceWar."""

from sgh_x458.spacewar.layout import GAME_ENTRY, INITIAL_DATA, MANIFEST, STATE_BASE
from tools.oracle import FirmwareGame


class Oracle(FirmwareGame):
    game_index = 1
    event_entry = GAME_ENTRY
    manifest_path = MANIFEST
    instruction_limit = 12_000_000
    state_address = STATE_BASE + 0x2C
    initial_data = INITIAL_DATA
