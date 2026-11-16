"""The drawing operations the shared MIDP renderer needs on Android."""

from dataclasses import dataclass
from types import SimpleNamespace

from java import jclass


Raster = jclass("io.github.hb2cpc.sghx458.AndroidRaster")


@dataclass(frozen=True, init=False)
class Rect:
    x: int
    y: int
    w: int
    h: int

    def __init__(self, *values):
        if len(values) == 1:
            values = tuple(values[0])
        for name, value in zip(("x", "y", "w", "h"), values, strict=True):
            object.__setattr__(self, name, value)

    def __iter__(self):
        return iter((self.x, self.y, self.w, self.h))

    def __bool__(self):
        return bool(self.w and self.h)

    @property
    def right(self):
        return self.x + self.w

    @property
    def bottom(self):
        return self.y + self.h

    def clip(self, other):
        x, y = max(self.x, other.x), max(self.y, other.y)
        width = min(self.right, other.right) - x
        height = min(self.bottom, other.bottom) - y
        return Rect(x, y, width, height) if width > 0 and height > 0 else Rect(self.x, self.y, 0, 0)

    def union(self, other):
        x, y = min(self.x, other.x), min(self.y, other.y)
        return Rect(x, y, max(self.right, other.right) - x, max(self.bottom, other.bottom) - y)


def rgb(color):
    r, g, b = color
    return (r << 16) | (g << 8) | b


class Surface:
    def __init__(self, size=None, *, depth=32, raster=None):
        self.native = raster if raster is not None else Raster(*size, depth == 16)
        self.bounds = Rect(0, 0, self.native.width(), self.native.height())
        self.clip = self.bounds

    def get_rect(self):
        return self.bounds

    def get_size(self):
        return self.bounds.w, self.bounds.h

    def get_clip(self):
        return self.clip

    def set_clip(self, rect):
        self.clip = self.bounds.clip(rect)
        self.native.setClip(*self.clip)

    def copy(self):
        return Surface(raster=self.native.copy())

    def fill(self, color):
        self.native.fill(rgb(color))

    def set_colorkey(self, color):
        # The MIDP font creates a transparent glyph surface using its initial fill color.
        self.native.clear()

    def set_at(self, point, color):
        self.native.pixel(*point, rgb(color))

    def blit(self, source, dest, area=None):
        x, y = tuple(dest)[:2]
        box = source.bounds if area is None else source.bounds.clip(area)
        self.native.blit(source.native, x, y, *box)
        return self.clip.clip(Rect(x, y, box.w, box.h))

    def frame(self):
        return self.native.frame()


def load(stream, _filename):
    return Surface(raster=Raster.decode(stream.read()))


def line(surface, color, start, end):
    x, y = start
    u, v = end
    surface.native.line(rgb(color), x, y, u, v)
    return Rect(min(x, u), min(y, v), abs(x - u) + 1, abs(y - v) + 1)


def rect(surface, color, area, *, width, border_radius):
    surface.native.rect(rgb(color), *area, width, border_radius)
    return Rect(area)


def ellipse(surface, color, area):
    surface.native.ellipse(rgb(color), *area)
    return Rect(area)


def polygon(surface, color, points):
    xs, ys = zip(*((int(x), int(y)) for x, y in points))
    surface.native.polygon(rgb(color), xs, ys)
    x, y = min(xs), min(ys)
    return Rect(x, y, max(xs) - x + 1, max(ys) - y + 1)


draw = SimpleNamespace(line=line, rect=rect, ellipse=ellipse, polygon=polygon)
image = SimpleNamespace(load=load)
