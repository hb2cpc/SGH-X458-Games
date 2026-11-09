"""Generate the project icon from a 32x32 pixel-art map.

Writes src/sgh_x458/resources/icon.png (256x256), icon.ico (16-256 px) and
icon.bmp (64x64 with alpha, for pygame windows: the single-file build ships
without pygame's PNG decoder, but BMP is always supported).
The artwork is original: a retro candy-bar phone playing a shooter.

    python -m tools.make_icon
"""

import struct
import zlib

from tools import PROJECT_ROOT


OUTPUT = PROJECT_ROOT / "src" / "sgh_x458" / "resources"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

PALETTE = {
    "K": (20, 26, 43),     # Outline.
    "b": (112, 133, 176),  # Body highlight.
    "B": (61, 79, 120),    # Body.
    "d": (40, 53, 86),     # Body shadow.
    "L": (28, 36, 58),     # Earpiece.
    "C": (10, 14, 26),     # Screen bezel.
    "S": (22, 60, 128),    # Screen, upper half.
    "T": (13, 40, 92),     # Screen, lower half.
    "s": (200, 220, 255),  # Star.
    "W": (255, 255, 255),  # Bullet.
    "Y": (255, 210, 63),   # Jet.
    "c": (120, 225, 255),  # Cockpit.
    "R": (255, 93, 58),    # Jet wings.
    "O": (255, 166, 43),   # Exhaust.
    "G": (218, 225, 238),  # Key.
    "g": (140, 152, 180),  # Key shadow.
}

JET = (
    "....Y....",
    "...YYY...",
    "...YcY...",
    "..RYYYR..",
    ".RRYYYRR.",
    "RRRYYYRRR",
    "R..YYY..R",
    "...RYR...",
    "..R.O.R..",
    "....O....",
)
STARS = ((8, 7), (22, 7), (9, 12), (23, 11), (8, 17), (21, 16), (19, 18))


def compose():
    """Build the 32x32 map: phone body, screen, jet, stars, keypad."""
    grid = [["."] * 32 for _ in range(32)]

    def fill(x0, y0, x1, y1, c):  # Inclusive bounds.
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                grid[y][x] = c

    fill(4, 2, 27, 29, "B")
    fill(4, 2, 4, 29, "b")
    fill(4, 2, 27, 2, "b")
    fill(27, 3, 27, 29, "d")
    fill(5, 29, 27, 29, "d")
    fill(4, 1, 27, 1, "K")
    fill(4, 30, 27, 30, "K")
    fill(3, 2, 3, 29, "K")
    fill(28, 2, 28, 29, "K")
    fill(13, 3, 18, 3, "L")
    fill(6, 5, 25, 19, "C")
    fill(7, 6, 24, 11, "S")
    fill(7, 12, 24, 18, "T")
    for x, y in STARS:
        grid[y][x] = "s"
    grid[6][15] = "W"
    for row, line in enumerate(JET):
        for col, c in enumerate(line):
            if c != ".":
                grid[8 + row][11 + col] = c
    for top in (21, 24, 27):
        for left in (6, 13, 20):
            fill(left, top, left + 5, top, "G")
            fill(left, top + 1, left + 5, top + 1, "g")
    return ["".join(row) for row in grid]


PIXELS = compose()


def base_pixels():
    assert len(PIXELS) == 32 and all(len(row) == 32 for row in PIXELS), "icon map must be 32x32"
    return [[PALETTE.get(c) for c in row] for row in PIXELS]


def render(size):
    """RGBA rows at the requested size: nearest-neighbour for multiples of 32, box filter below."""
    base = base_pixels()
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            if size >= 32:
                color = base[y * 32 // size][x * 32 // size]
                row.append((*color, 255) if color else (0, 0, 0, 0))
                continue
            # Average the covered source pixels, weighting colour by alpha.
            x0, x1 = x * 32 // size, (x + 1) * 32 // size
            y0, y1 = y * 32 // size, (y + 1) * 32 // size
            cells = [base[j][i] for j in range(y0, y1) for i in range(x0, x1)]
            solid = [c for c in cells if c]
            if not solid:
                row.append((0, 0, 0, 0))
                continue
            r, g, b = (sum(c[k] for c in solid) // len(solid) for k in range(3))
            row.append((r, g, b, 255 * len(solid) // len(cells)))
        rows.append(row)
    return rows


def png_bytes(rows):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    size = len(rows)
    raw = b"".join(b"\0" + bytes(v for pixel in row for v in pixel) for row in rows)
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def bmp_bytes(rows):
    """32-bit BMP with a BITMAPV4HEADER alpha mask, bottom-up rows."""
    size = len(rows)
    pixels = b"".join(bytes((b, g, r, a)) for row in reversed(rows) for r, g, b, a in row)
    info = struct.pack("<IiiHHIIiiII", 108, size, size, 1, 32, 3, len(pixels), 2835, 2835, 0, 0)
    info += struct.pack("<IIII", 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    info += struct.pack("<I", 0x73524742) + bytes(36) + bytes(12)  # sRGB, no endpoints or gamma.
    header = struct.pack("<2sIHHI", b"BM", 14 + len(info) + len(pixels), 0, 0, 14 + len(info))
    return header + info + pixels


def ico_bytes(images):
    """Windows ICO with PNG-compressed entries (supported since Windows Vista)."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    directory, data = b"", b""
    for size, png in images:
        dim = 0 if size >= 256 else size
        directory += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    return header + directory + data


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    pngs = {size: png_bytes(render(size)) for size in ICO_SIZES}
    (OUTPUT / "icon.png").write_bytes(pngs[256])
    (OUTPUT / "icon.ico").write_bytes(ico_bytes(sorted(pngs.items())))
    (OUTPUT / "icon.bmp").write_bytes(bmp_bytes(render(64)))
    print(f"wrote icon.png, icon.ico and icon.bmp to {OUTPUT}")


if __name__ == "__main__":
    main()
