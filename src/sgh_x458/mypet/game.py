"""Standalone Python port of the SGH-X458 MyPet firmware game.

The control flow in game_flow.py is a static translation of the Thumb blocks
observed in the firmware. This class supplies the handset services, bitmaps
and arithmetic helpers those blocks call.
"""

import math
from struct import Struct

from sgh_x458.runtime.session import GAME_CONTROLLER
from sgh_x458.runtime.translated_runtime import TranslatedGame
from sgh_x458.runtime.word_ops import MASK, signed

from .game_flow import BLOCKS
from .layout import ASSETS, MANIFEST, STATE_BASE


FLOAT = Struct("<f")
PET_PHASE = STATE_BASE - 4
INTRO = 1
READ_CLOCK = 0x22833C

# Thumb-to-ARM stubs for the compiler's single-precision helper library. Pet
# stat updates convert integer deltas to floats, scale them, sum them, then
# truncate back to a byte. IEEE-754 round-to-nearest matches the ARM routines
# for the finite values the game produces.
FLOAT_STUBS = {
    0x14B9A0: "int_to_float",
    0x14BB4C: "float_multiply",
    0x14C174: "float_add",
    0x14BD60: "float_to_int",
}


def float_bits(value):
    return int.from_bytes(FLOAT.pack(value), "little")


def float_value(bits):
    return FLOAT.unpack(bits.to_bytes(4, "little"))[0]


class Game(TranslatedGame):
    game_index = 2
    state_address = STATE_BASE
    extended_math = True
    manifest_path = MANIFEST
    data_path = ASSETS / "runtime-data.bin"
    blocks = BLOCKS
    # Pet room updates repaint a full 128x160 frame; leave headroom for the
    # translated blocks that walk the bitmap data.
    step_limit = 5_000_000

    def __init__(self, language=1, on_audio=None, save=None):
        super().__init__(language, on_audio, save)
        self.rules.update({address: getattr(self, name) for address, name in FLOAT_STUBS.items()})
        self.rules[READ_CLOCK] = self.read_clock

    def read_clock(self):
        # The handset OS updates the clock that this routine reads from RAM.
        self.sync_clock()
        return BLOCKS[READ_CLOCK](self, self.r, self.load_value, self.store_value)

    def save_on_close(self):
        if self.ui_state == 1 and self.word(PET_PHASE) == INTRO:
            # Initialize the pet before the firmware writes its record.
            if not self.timers:
                self.key(4)
            self.key(30)
        self.call(GAME_CONTROLLER, 3)

    def int_to_float(self):
        self.r[0] = float_bits(float(signed(self.r[0], 32)))

    def float_multiply(self):
        self.r[0] = float_bits(float_value(self.r[0]) * float_value(self.r[1]))

    def float_add(self):
        self.r[0] = float_bits(float_value(self.r[0]) + float_value(self.r[1]))

    def float_to_int(self):
        value = float_value(self.r[0])
        result = int(value) if math.isfinite(value) else 0
        self.r[0] = min(max(result, -0x80000000), 0x7FFFFFFF) & MASK
