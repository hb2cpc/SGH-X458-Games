"""Drawing operations used by the SGH-X458 MIDP canvases."""

from math import cos, radians, sin

class Graphics:
    """MIDP Graphics with the X458 firmware's clipping rules.

    ``limit`` is Graphics.maxWidth/maxHeight from the ROM's javax.microedition.lcdui.Graphics.
    The screen Graphics is ``new Graphics(128, Display.HEIGHT)`` with Display.HEIGHT = 144,
    while the screen buffer is the full 128x160 LCD.

    The ROM's reset() and setClip() keep a ``clipped`` flag. setClip clamps the rectangle
    to the limit and only ever sets the flag; it stays false while the clip covers the
    whole limit. Unclipped image blits reach the full LCD, while the other primitives
    keep to the clip rectangle. After Fun2Link's setClip(0, 0, 128, 160) the clip is
    0..144, so its bottom HUD image shows on the phone and the later
    fillRect(0, 151, 128, 9) does not. Golf never calls setClip, so its HUD text keeps
    the unclamped 0..160 clip from reset().
    """

    def __init__(self, surface, drawing, fonts, limit=None, clip=None):
        self.surface = surface
        self.drawing = drawing
        self.limit = surface.get_rect() if limit is None else drawing.Rect(limit)
        self.color = 0
        self.font = fonts[0, 0]
        self.pixels = 0  # Pixels touched by drawing calls, for the handset timing model.
        self.reset(surface.get_rect() if clip is None else drawing.Rect(clip))

    def reset(self, rect):
        x1, y1 = max(rect.x, 0), max(rect.y, 0)
        x2, y2 = rect.right, rect.bottom
        self.clip = self.drawing.Rect(x1, y1, max(x2 - x1, 0), max(y2 - y1, 0))
        self.clipped = x1 > 0 or y1 > 0 or x2 < self.limit.right or y2 < self.limit.bottom

    def set_clip(self, x, y, width, height):
        limit = self.limit
        if x >= limit.right or width <= 0 or y >= limit.bottom or height <= 0:
            self.clip = self.drawing.Rect(0, 0, 0, 0)
            self.clipped = True
            return
        x1, y1 = max(x, 0), max(y, 0)
        x2, y2 = min(x + width, limit.right), min(y + height, limit.bottom)
        self.clip = self.drawing.Rect(x1, y1, max(x2 - x1, 0), max(y2 - y1, 0))
        if x1 > 0 or y1 > 0 or x2 < limit.right or y2 < limit.bottom:
            self.clipped = True

    def area(self, method):
        # Image blits skip clipping while the flag is false; other primitives always use
        # the clip rectangle, which setClip has clamped to the limit.
        if method == "drawImage" and not self.clipped:
            return self.surface.get_rect()
        return self.clip

    def draw(self, method, *args):
        if method == "setClip":
            self.set_clip(*args)
            return None
        if method.startswith("getClip"):
            return getattr(self.clip, {"X": "x", "Y": "y", "Width": "w", "Height": "h"}[method[7:]])
        if method == "setColor":
            self.color = (args[0] & 0xFFFFFF if len(args) == 1
                          else (args[0] << 16) | (args[1] << 8) | args[2])
            return None
        if method == "getColor":
            return self.color
        if method == "setFont":
            self.font = args[0]
            return None
        surface = self.surface
        original = surface.get_clip()
        area = self.area(method)
        surface.set_clip(area)
        try:
            bounds = self.paint(method, *args)
        finally:
            surface.set_clip(original)
        if bounds is not None:
            touched = area.clip(bounds)
            self.pixels += touched.w * touched.h
        return None

    def paint(self, method, *args):
        surface = self.surface
        color = self.color >> 16, (self.color >> 8) & 255, self.color & 255
        if method == "drawImage":
            image, x, y, anchor = args
            return surface.blit(image, anchored(x, y, *image.get_size(), anchor))
        elif method == "drawString":
            return self.font.draw(surface, args[0], args[1], args[2], args[3], color)
        elif method == "drawLine":
            x1, y1, x2, y2 = args
            return self.drawing.draw.line(surface, color, (x1, y1), (x2, y2))
        elif method in ("drawRect", "fillRect", "fillRoundRect"):
            x, y, width, height, *rounding = args
            if width < 0 or height < 0:
                return
            outline = method == "drawRect"
            return self.drawing.draw.rect(surface, color, (x, y, width + outline, height + outline),
                                          width=int(outline), border_radius=min(rounding) // 2 if rounding else 0)
        elif method == "fillArc":
            x, y, width, height, first, sweep = args
            if abs(sweep) >= 360:
                return self.drawing.draw.ellipse(surface, color, (x, y, width, height))
            if sweep:
                rx, ry = width / 2, height / 2
                cx, cy = x + rx, y + ry
                steps = abs(sweep) // 12 + 1
                angles = [radians(first + sweep * i / steps) for i in range(steps + 1)]
                return self.drawing.draw.polygon(surface, color, [
                    (cx, cy), *((cx + rx * cos(a), cy - ry * sin(a)) for a in angles),
                ])
        else:
            raise NotImplementedError(method)


def anchored(x, y, width, height, anchor):
    x -= width if anchor & 8 else width // 2 if anchor & 1 else 0
    y -= height if anchor & 32 else height // 2 if anchor & 2 else 0
    return x, y


# Native drawString (ROM 0x13D96C) moves the top edge by these amounts for each anchor.
ANCHOR_OFFSETS = {8: {16: 2, 64: -8, 32: -9}, 0: {64: -14, 32: -17}, 16: {64: -19, 32: -24}}
def load_fonts(data, drawing):
    """Install the handset glyphs decoded by tools/java_games/fonts.py."""
    fonts = {}
    for key, font in data.items():
        size, style = map(int, key.split("/"))
        fonts[size, style] = HandsetFont(drawing, size, font["height"], {
            chr(int(code)): glyph for code, glyph in font["glyphs"].items()})
    return fonts


class HandsetFont:
    def __init__(self, drawing, size, height, glyphs):
        self.drawing = drawing
        self.size = size
        self.height = height
        self.glyphs = glyphs
        self.cache = {}

    def width(self, character):
        return self.glyphs.get(character, self.glyphs[" "])[0]

    def draw(self, surface, text, x, y, anchor, color):
        width = sum(map(self.width, text))
        if anchor & 8:
            x -= width
        elif anchor & 1:
            x -= width // 2
        y += ANCHOR_OFFSETS[self.size].get(anchor & 0xF0, 0)
        # Characters left of x=0 are dropped whole; the rest stop before passing x=128.
        while text and x < 0:
            x += self.width(text[0])
            text = text[1:]
        end, right = 0, x
        while end < len(text) and right + self.width(text[end]) <= 128:
            right += self.width(text[end])
            end += 1
        if end:
            return surface.blit(self.render(text[:end], color), (x, y))
        return None

    def render(self, text, color):
        key = text, color
        image = self.cache.get(key)
        if image is None:
            image = self.drawing.Surface((max(1, sum(map(self.width, text))), self.height))
            ink = (0, 0, 0) if color != (0, 0, 0) else (255, 255, 255)
            image.fill(ink)
            image.set_colorkey(ink)
            left = 0
            for character in text:
                width, rows = self.glyphs.get(character, self.glyphs[" "])
                for row, bits in enumerate(rows):
                    for column in range(width):
                        if bits >> column & 1:
                            image.set_at((left + column, row), color)
                left += width
            if len(self.cache) > 512:
                self.cache.clear()
            self.cache[key] = image
        return image
