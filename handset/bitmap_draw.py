"""Draw the firmware's packed bitmaps into its original RGB565 framebuffer."""

from functools import lru_cache
from struct import unpack

from .word_ops import signed


DRAW_STATE = 0x103EE78
PALETTE_RAM = 0x12DA3E0


def rgb565(color):
    return (color >> 11) * 255 // 31, ((color >> 5) & 63) * 255 // 63, (color & 31) * 255 // 31


class BitmapDraw:
    def __init__(self, game):
        self.game = game
        self.runs = lru_cache(maxsize=1024)(self.decode)

    def decode(self, address, palette, mirror):
        read = self.game.read
        kind, width, height, anchor_x, anchor_y = unpack("<BBBbb", read(address, 5))
        bits = 1 << (kind - 5)
        lookup_length = 0 if kind == 8 else 1 << bits
        lookup = read(address + 5, lookup_length) if lookup_length else bytes(range(182))
        packed = read(address + 5 + lookup_length, (width * height * bits + 7) // 8)
        colors = [None if index == 4 else palette[2 * index:2 * index + 2] for index in lookup]
        mask = (1 << bits) - 1
        rows = []
        for row in range(height):
            pixels = []
            for bit in range(row * width * bits, (row + 1) * width * bits, bits):
                pixels.append(colors[(packed[bit // 8] >> (8 - bits - bit % 8)) & mask])
            if mirror:
                pixels.reverse()
            runs = []
            start = 0
            while start < width:
                if pixels[start] is None:
                    start += 1
                    continue
                end = start + 1
                while end < width and pixels[end] is not None:
                    end += 1
                runs.append((start, b"".join(pixels[start:end])))
                start = end
            rows.append(runs)
        return width, height, anchor_x, anchor_y, rows

    def draw(self, mirror=False):
        g = self.game
        address, x, y = g.r[:3]
        palette = g.read(PALETTE_RAM, 182 * 2)
        width, height, anchor_x, anchor_y, rows = self.runs(address, palette, mirror)
        x = signed((x - (width - anchor_x if mirror else anchor_x)) & 0xFFFF, 16)
        y = signed((y - anchor_y) & 0xFFFF, 16)
        left, top, right, bottom = unpack("<4i", g.read(DRAW_STATE + 0x1C, 16))
        stride = g.load_value(g, DRAW_STATE + 0x42, 2) * 2
        buffer = g.word(DRAW_STATE + 8) - g.ram_base
        for dy in range(max(top, y), min(bottom + 1, y + height)):
            target = buffer + dy * stride
            for offset, data in rows[dy - y]:
                start = x + offset
                first = max(left, start)
                last = min(right + 1, start + len(data) // 2)
                if first < last:
                    g.ram[target + first * 2:target + last * 2] = data[(first - start) * 2:(last - start) * 2]

    def draw_flippable(self):
        return self.draw_entry(0x22B174, bool(self.game.r[3]))

    def draw_normal(self):
        return self.draw_entry(0x22B100, False)

    def draw_entry(self, address, mirror):
        game = self.game
        if 5 <= game.load_value(game, game.r[0], 1) <= 8:
            return self.draw(mirror)
        # Older bitmap encodings follow their extracted rendering routine.
        block = game.blocks[address]
        return block(game, game.r, game.load_value, game.store_value)
