"""Offline reference execution for G133 MyPet."""

from MyPet.layout import GAME_ENTRY, MANIFEST, STATE_BASE
from tools.x_fighter.runtime import FirmwareGame


class Oracle(FirmwareGame):
    game_index = 2
    event_entry = GAME_ENTRY
    manifest_path = MANIFEST
    instruction_limit = 20_000_000
    state_address = STATE_BASE
