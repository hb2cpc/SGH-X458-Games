"""Offline reference execution for G58 AirShooting (X-Fighter)."""

from sgh_x458.x_fighter.layout import BATTLE_KEY, GAME_ENTRY, MANIFEST, STATE
from tools.oracle import FirmwareGame


class Oracle(FirmwareGame):
    game_index = 0
    event_entry = GAME_ENTRY
    manifest_path = MANIFEST
    state_address = STATE
    battle_key_address = BATTLE_KEY
