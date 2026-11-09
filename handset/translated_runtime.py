"""Memory and host calls used by statically converted SGH-X458 games."""

from functools import partial
from struct import Struct, unpack_from

from .bitmap_draw import BitmapDraw
from .session import Session
from .word_ops import MASK, MATH_RULES, signed


RAM_BASE = 0x1000000
RAM_SIZE = 0x400000
STATIC_END = 0x700000
STACK = 0x13FF000
RETURN_SITE = 0x13FF800
HALF = Struct("<H")
WORD = Struct("<I")


class TranslatedGame(Session):
    ram_base = RAM_BASE
    # Guard against a runaway translated control flow. Games whose work scales
    # with the screen area raise this (see SpaceWar.Game).
    step_limit = 500_000
    extended_math = False

    def __init__(self, language=1, on_audio=None, save=None):
        super().__init__(language, on_audio, save)
        self.r = [0] * 16
        self.n = self.z = self.c = self.v = 0
        self.ram = bytearray(RAM_SIZE)
        self.data = bytearray(STATIC_END)
        self.present = bytearray(STATIC_END)
        self.load_static()
        self.initialize_ram()
        self.bitmap = BitmapDraw(self)
        self.rules = {
            0x14B3A4: self.divide_words,
            0x14B3EC: self.unsigned_decimal,
            0x14B468: self.signed_decimal,
            0x22815E: self.no_device_action,
            0x2283A0: self.no_device_action,
            0x2283AC: self.no_device_action,
            0x22B100: self.bitmap.draw_normal,
            0x22B174: self.bitmap.draw_flippable,
            0x262954: self.memset,
            0x262998: self.memcpy,
        }
        if self.extended_math:
            self.rules.update({address: partial(rule, self) for address, rule in MATH_RULES.items()})

    def load_static(self):
        data = self.data_path.read_bytes()
        cursor = 4
        for _ in range(unpack_from("<I", data)[0]):
            address, size = unpack_from("<II", data, cursor)
            cursor += 8
            block = data[cursor:cursor + size]
            if len(block) != size or address + size > STATIC_END:
                raise ValueError("Malformed game data block")
            self.data[address:address + size] = block
            self.present[address:address + size] = b"\1" * size
            cursor += size
        if cursor != len(data):
            raise ValueError("Unexpected bytes after game static data")

    def read(self, address, size):
        if address >= RAM_BASE:
            offset = address - RAM_BASE
            if offset + size <= RAM_SIZE:
                return bytes(self.ram[offset:offset + size])
        elif 0 <= address and address + size <= STATIC_END and all(self.present[address:address + size]):
            return bytes(self.data[address:address + size])
        raise RuntimeError(f"Cannot read game data at {address:#x} ({size} bytes)")

    def write(self, address, data):
        offset = address - RAM_BASE
        if not 0 <= offset <= RAM_SIZE - len(data):
            raise RuntimeError(f"Cannot write game state at {address:#x}")
        self.ram[offset:offset + len(data)] = data

    def load_value(self, _game, address, size):
        if address >= RAM_BASE:
            data, offset = self.ram, address - RAM_BASE
        elif 0 <= address < STATIC_END and self.present[address]:
            data, offset = self.data, address
        else:
            raise RuntimeError(f"Missing extracted data at {address:#x}")
        if size == 4:
            return WORD.unpack_from(data, offset)[0]
        if size == 2:
            return HALF.unpack_from(data, offset)[0]
        return data[offset]

    def store_value(self, _game, address, size, value):
        offset = address - RAM_BASE
        if not 0 <= offset < RAM_SIZE:
            raise RuntimeError(f"Cannot write game state at {address:#x}")
        if size == 4:
            WORD.pack_into(self.ram, offset, value & MASK)
        elif size == 2:
            HALF.pack_into(self.ram, offset, value & 0xFFFF)
        else:
            self.ram[offset] = value & 0xFF

    def word(self, address):
        return self.load_value(self, address, 4)

    def store(self, address, value):
        self.store_value(self, address, 4, value)

    def call(self, address, a=0, b=0, c=0):
        self.r[:3] = a & MASK, b & MASK, c & MASK
        self.r[13] = STACK
        self.r[14] = RETURN_SITE | 1
        self.execute(address)
        return self.r[0]

    def call_rule(self, address):
        link = self.r[14]
        self.r[14] = RETURN_SITE | 1
        self.execute(address)
        self.r[14] = link

    def execute(self, address):
        r, rd, wr = self.r, self.load_value, self.store_value
        blocks, rules, devices = self.blocks, self.rules, self.devices
        for _ in range(self.step_limit):
            address &= ~1
            if address == RETURN_SITE:
                return
            if (rule := rules.get(address)) is not None:
                target = rule()
                address = r[14] if target is None else target
            elif (device := devices.get(address)) is not None:
                r[0] = device(r[0], r[1], r[2], r[14])
                address = r[14]
            elif (block := blocks.get(address)) is not None:
                address = block(self, r, rd, wr)
            else:
                raise RuntimeError(f"Unresolved game control flow at {address:#x}")
        raise RuntimeError(f"Game control flow exceeded its step limit at {address:#x}")

    def divide(self, numerator, denominator):
        quotient = abs(numerator) // abs(denominator)
        if (numerator < 0) != (denominator < 0):
            quotient = -quotient
        self.r[0] = quotient & MASK
        self.r[1] = (numerator - quotient * denominator) & MASK

    def divide_words(self):
        self.divide(signed(self.r[1]), signed(self.r[0]))

    def signed_decimal(self):
        self.divide(signed(self.r[0]), 10)

    def unsigned_decimal(self):
        self.r[0], self.r[1] = divmod(self.r[0], 10)

    def no_device_action(self):
        self.r[0] = 0

    def memset(self):
        dest, value, size = self.r[:3]
        if size:
            self.write(dest, bytes((value & 255,)) * size)

    def memcpy(self):
        dest, source, size = self.r[:3]
        if size:
            self.write(dest, self.read(source, size))
