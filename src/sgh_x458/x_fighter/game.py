"""Standalone Python implementation of the extracted X-Fighter control flow."""

from sgh_x458.runtime.bitmap_draw import DRAW_STATE
from sgh_x458.runtime.score_editor import ScoreEditor
from sgh_x458.runtime.translated_runtime import TranslatedGame
from sgh_x458.runtime.word_ops import signed

from .game_flow import BLOCKS
from .game_rules import (
    activate_nuclear_attack, collect_power_up,
    finish_player_explosion, handle_combat_key, move_player, restore_player_health, scroll_and_spawn,
    update_battle, update_pickups,
)
from .layout import ASSETS, BATTLE_KEY, MANIFEST, STATE


PLAYER_DESTRUCTION = 0x2302C4
LASER_DEATH_RETURN = 0x2337FE
HANDSET_LASER_DEATH_MS = 382
FIRE_PRIMARY = 0x23060A
ENTER_BATTLE = 0x235AA4
COMBAT_KEY = 0x234724
BATTLE_FRAME = 0x23589C
FILL_FIRST_PIXEL = 0x229E88
SOLID_PIXEL = 0x22A26D


class Game(ScoreEditor, TranslatedGame):
    game_index = 0
    state_address = STATE
    battle_key_address = BATTLE_KEY
    manifest_path = MANIFEST
    data_path = ASSETS / "runtime-data.bin"
    blocks = BLOCKS

    def __init__(self, language=1, on_audio=None, save=None, *, handset_timing=False):
        super().__init__(language, on_audio, save)
        self.reserve_lives = 3
        self.movement_step = 10
        # Only the lethal-beam audio cadence uses a recording-derived delay.
        # Menu/cover X palette timing follows the firmware timers unchanged.
        self.handset_timing = handset_timing
        self.invincible = False
        self.auto_fire = True
        self.drawing = True
        self.primary_fire_requested = False
        self.equipment = None
        self.redraw_ram = None
        self.rules.update({
            0x22FE50: lambda: activate_nuclear_attack(self),
            0x22FF54: lambda: collect_power_up(self, self.r[0]),
            0x22FFFC: lambda: update_pickups(self),
            PLAYER_DESTRUCTION: self.destroy_player,
            FIRE_PRIMARY: self.fire_primary,
            0x230744: lambda: move_player(self, False),
            0x230768: lambda: move_player(self, True),
            0x234480: lambda: scroll_and_spawn(self),
            COMBAT_KEY: lambda: handle_combat_key(self),
            FILL_FIRST_PIXEL: self.fill_rectangle,
            0x235600: self.finish_explosion,
            0x235ABA: self.battle_tick,
        })

    def close(self):
        self.rules.clear()
        self.redraw_ram = None

    def apply_battle_key(self, code):
        """Handle a mobile combat key and redraw between scheduled world updates."""
        self.key(code)
        if self.word(BATTLE_KEY) != code:
            return
        self.call(COMBAT_KEY)

        # The firmware's compositor can also advance effects such as a bomb flash.
        # Compose into scratch RAM so those effects only advance on a world update.
        ram, registers = self.ram, self.r
        flags = self.n, self.z, self.c, self.v
        if self.redraw_ram is None:
            self.redraw_ram = ram.copy()
        else:
            self.redraw_ram[:] = ram
        self.ram, self.r = self.redraw_ram, registers.copy()
        try:
            self.call(BATTLE_FRAME)
        finally:
            self.ram, self.r = ram, registers
            self.n, self.z, self.c, self.v = flags

    def fill_rectangle(self):
        """Draw the clipped RGB565 rectangle by rows, then run the last pixel normally."""
        r = self.r
        if self.word(DRAW_STATE + 60) == SOLID_PIXEL:
            left, right = signed(r[4]), signed(r[6])
            top, bottom = signed(r[7]), signed(r[5])
            if self.load_value(self, DRAW_STATE + 0x46, 1) != 4:
                stride = self.load_value(self, DRAW_STATE + 0x42, 2) * 2
                row = self.read(DRAW_STATE + 0x44, 2) * (right - left + 1)
                offset = self.word(DRAW_STATE + 8) - self.ram_base + top * stride + left * 2
                for _ in range(top, bottom + 1):
                    self.ram[offset:offset + len(row)] = row
                    offset += stride
            r[4], r[7] = r[6], r[5]
        return self.blocks[FILL_FIRST_PIXEL](self, r, self.load_value, self.store_value)

    def set_player_rules(self, reserve_lives, movement_step):
        if not 0 <= reserve_lives <= 99 or not 1 <= movement_step <= 128:
            raise ValueError("Reserve lives must be 0–99 and movement step 1–128")
        self.reserve_lives = reserve_lives
        self.movement_step = movement_step

    def destroy_player(self):
        if self.invincible:
            restore_player_health(self)
            self.r[0] = 1
            return None
        if self.handset_timing and (self.r[14] & ~1) == LASER_DEATH_RETURN:
            # The handset recording measures about 382 ms between lethal beam updates.
            self.main_timer_repeat_floor = HANDSET_LASER_DEATH_MS * 13
        return BLOCKS[PLAYER_DESTRUCTION](self, self.r, self.load_value, self.store_value)

    def fire_primary(self):
        if self.auto_fire or self.primary_fire_requested:
            return BLOCKS[FIRE_PRIMARY](self, self.r, self.load_value, self.store_value)
        return 0x230642  # Return after the firmware updates cooldown and power-up timers.

    def configure_practice(self, *, invincible, auto_fire, upgraded, shield, bombs):
        self.invincible = invincible
        self.auto_fire = auto_fire
        self.prepare_equipment(upgraded, shield, bombs)

    def prepare_equipment(self, upgraded=False, shield=None, bombs=None):
        """Grant starting equipment now in battle, or when the first battle begins.

        self.equipment holds the arguments while they still wait for that battle.
        """
        self.rules.pop(ENTER_BATTLE, None)
        self.equipment = None
        if not (upgraded or shield or bombs is not None):
            return

        def equip():
            if upgraded:
                collect_power_up(self, 2)
            if shield == "full":
                collect_power_up(self, 3)
            elif shield == "off":
                self.store(STATE + 0x84, 0)
            if bombs is not None:
                self.store(STATE + 0x6C, bombs)

        def first_battle():
            self.rules.pop(ENTER_BATTLE)
            self.equipment = None
            equip()
            return BLOCKS[ENTER_BATTLE](self, self.r, self.load_value, self.store_value)

        if self.state == 4:
            equip()
        else:
            self.equipment = [upgraded, shield, bombs]
            self.rules[ENTER_BATTLE] = first_battle

    def finish_explosion(self):
        finish_player_explosion(self)
        return 0x235636

    def battle_tick(self):
        update_battle(self)
        self.primary_fire_requested = False
        return 0x235BE2
