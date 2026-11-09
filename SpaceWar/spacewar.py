"""Standalone Python port of the SpaceWar firmware game."""

from functools import partial

from handset.score_editor import ScoreEditor
from handset.translated_runtime import TranslatedGame
from handset.word_ops import signed

from .game_flow import BLOCKS
from .layout import ASSETS, DEFAULT_LIVES, INITIAL_DATA, MANIFEST, STATE_BASE


CAMPAIGN_ENTRY = 0x237BC8
CAMPAIGN_READY = 0x237BCC
INITIALIZE_STAGE = 0x235BFC
REGISTER_COLLISION = 0x2368E6
ADVANCE_ENEMY = 0x2368F0
DRAW_TEXT = 0x228C40
LIVES_TEXT_RETURN = 0x23722D
HUD_DIGIT_WIDTH = 6
STAGE = STATE_BASE + 0x44
LIVES = STATE_BASE + 0x48
ITEM_TIMERS = {"boost": 0x12DF448, "slow": 0x12DF44C, "life": 0x12DF450}
ITEM_TICKS = 40

class Game(ScoreEditor, TranslatedGame):
    game_index = 1
    state_address = STATE_BASE + 0x2C
    initial_data = INITIAL_DATA
    extended_math = True
    manifest_path = MANIFEST
    data_path = ASSETS / "runtime-data.bin"
    blocks = BLOCKS
    # Closing a region scans the 2-bit screen grid to decide which side to fill.
    # A small region already costs ~480k blocks; invincible runs can enclose
    # half the screen, so the default 500k guard would abort a legitimate fill.
    step_limit = 10_000_000

    def configure_campaign(self, stage, lives, item, *, invincible=False):
        if invincible:
            self.rules[REGISTER_COLLISION] = self.ignore_collision
        if (stage, lives, item) != (1, DEFAULT_LIVES, "none"):
            self.rules[CAMPAIGN_ENTRY] = partial(self.start_campaign, stage, lives, item)
            self.rules[DRAW_TEXT] = self.draw_practice_text

    @staticmethod
    def ignore_collision():
        # Skip the damage flag and vibration, then finish the enemy's movement.
        return ADVANCE_ENEMY

    def start_campaign(self, stage, lives, item):
        # The intro confirmation has set up a fresh campaign. The same stage
        # initializer is shared by later stages and continues.
        self.store(STAGE, stage - 1)
        self.store(LIVES, lives)
        self.call_rule(INITIALIZE_STAGE)
        if item in ITEM_TIMERS:
            self.store(ITEM_TIMERS[item], ITEM_TICKS)
        return CAMPAIGN_READY

    def draw_practice_text(self):
        # The original HUD builds a single digit. Fit three digits to the
        # left of the HUD divider, keeping the existing one- and two-digit layout.
        if self.r[14] == LIVES_TEXT_RETURN and (lives := signed(self.word(LIVES))) >= 10:
            digits = str(lives).encode("ascii")
            self.r[0] -= HUD_DIGIT_WIDTH * max(0, len(digits) - 2)
            self.write(self.r[2], digits + b"\0")
        return self.blocks[DRAW_TEXT](self, self.r, self.load_value, self.store_value)
