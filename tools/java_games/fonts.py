"""Decode the handset fonts the X458 Java VM uses for MIDP text.

Graphics.drawString (native 0x12FEAC) maps Font sizes to the firmware font list at
ROM 0x50CCDC (0x38-byte entries) through 0x1311F8: SMALL is entry 1 (SmallFont) or
entry 2 (SmallFontB) for bold, MEDIUM is entry 4 (Chinese) and LARGE is entry 5 (SEC).
Each entry's selector picks a glyph record by character; for printable ASCII,
Chinese uses its second record and the others their first.

A glyph record is: flags (byte 2 = proportional, byte 3 = fixed width),
height, last character, glyph table, bitmap. Fixed fonts store `width` column bytes
per character with the top row in bit 0. Proportional tables hold
(1, width, offset16) per character. Their bitmaps sit 0x400 bytes after the table
as three 8-row planes of `width` bytes each, again with the top row in bit 0.
"""

from struct import unpack_from

FONT_LIST = 0x50CCDC
FONT_ENTRY = 0x38
# MIDP size -> (plain entry, bold entry, record index used for ASCII)
SIZES = {8: (1, 2, 0), 0: (4, 4, 1), 16: (5, 5, 0)}
CHARACTERS = range(0x20, 0x7F)


def record(rom, entry, index):
    return unpack_from("<I", rom, FONT_LIST + entry * FONT_ENTRY + 0x20 + 4 * index)[0]


def glyphs(rom, address):
    """Return (height, {character: (width, [row bitmasks])}) for one glyph record."""
    flags, height, _last, table, bitmap = unpack_from("<5I", rom, address)
    proportional = (flags >> 16) & 0xFF
    fixed_width = flags >> 24
    result = {}
    for code in CHARACTERS:
        rows = [0] * height
        if proportional:
            _, width, offset = unpack_from("<BBH", rom, table + 4 * code)
            start = table + 0x400 + offset
            for x in range(width):
                for plane in range(3):
                    column = rom[start + plane * width + x]
                    for bit in range(8):
                        y = plane * 8 + bit
                        if y < height and column >> bit & 1:
                            rows[y] |= 1 << x
        else:
            width = fixed_width
            start = bitmap + code * width
            for x in range(width):
                column = rom[start + x]
                for y in range(height):
                    if column >> y & 1:
                        rows[y] |= 1 << x
        result[code] = (width, rows)
    return height, result


def midp_fonts(rom):
    fonts = {}
    for size, (plain, bold, index) in SIZES.items():
        for style, entry in ((0, plain), (1, bold)):
            height, table = glyphs(rom, record(rom, entry, index))
            fonts[f"{size}/{style}"] = {
                "height": height,
                "glyphs": {str(code): [width, rows] for code, (width, rows) in table.items()},
            }
    return fonts
