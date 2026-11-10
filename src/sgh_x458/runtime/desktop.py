"""Display and single-channel sound adapters shared by the phone game ports."""

import argparse
import os
import sys
from array import array
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from struct import Struct
from tempfile import NamedTemporaryFile
from threading import get_native_id

from . import read_asset
from .bitmap_draw import rgb565
from .session import HEIGHT, SAVE_SIZE, WIDTH

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")


WINDOW_SIZES = {"128x160": (128, 160), "200x250": (200, 250),
                "300x375": (300, 375), "400x500": (400, 500)}
DEFAULT_SIZE = "400x500"
DEFAULT_VOLUME = 50
DEFAULT_SPEED = "1"
SPEED_QUARTERS = {"0.5": 2, "0.75": 3, "1": 4, "1.5": 6, "2": 8}
# Longest wall-clock gap one frame may advance the game. Windows stops the event
# loop while the window is dragged; without a cap the game would replay the
# whole pause in a single frame the player never sees.
MAX_FRAME_MS = 100
PIXEL = Struct("<H")
# src/sgh_x458/runtime/desktop.py -> project root when running from a source checkout.
SOURCE_ROOT = Path(__file__).resolve().parents[3]
ICON = Path(__file__).resolve().parents[1] / "resources" / "icon.png"
APP_ID = "SGH-X458-Games"

# Number tiles use the same RGB565 entries across the three games and languages.
MENU_KEY_COLORS = {
    0x0200: 0x19A3, 0x8710: 0xA635, 0xC7F8: 0xDFBC,
    0xC698: 0x8410, 0xE7DC: 0x9CF3, 0xF7FE: 0xC618,
}
DISABLED_KEY_COLORS = {
    0x0200: 0x8410, 0x8710: 0x9CF3, 0xC7F8: 0xC618,
    0xFF9F: 0xCE59, 0xFFFF: 0xDEFB,
}


def style_start_menu(frame, *, disable_continue=False):
    """Apply the shared number-tile palette to a desktop title frame."""
    result = bytearray(frame)
    for top in (75, 141):
        for y in range(top, top + 19):
            for x in range(WIDTH):
                offset = (y * WIDTH + x) * PIXEL.size
                color = PIXEL.unpack_from(frame, offset)[0]
                if disable_continue and top == 141 and x < 12:
                    styled = DISABLED_KEY_COLORS.get(color, color)
                elif disable_continue and top == 141 and 12 <= x < 63 and color == 0:
                    styled = 0xBDF7  # Disabled Continue label.
                else:
                    styled = MENU_KEY_COLORS.get(color, color)
                PIXEL.pack_into(result, offset, styled)
    return bytes(result)


def data_directory():
    """Settings and saves: .local/ in a source checkout, otherwise %LOCALAPPDATA%/SGH-X458-Games."""
    if not getattr(sys, "frozen", False) and (SOURCE_ROOT / "pyproject.toml").is_file():
        return SOURCE_ROOT / ".local"
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "SGH-X458-Games"


def use_app_taskbar_icon():
    """Group our windows under the project icon instead of python.exe's on the Windows taskbar."""
    if sys.platform == "win32":
        from ctypes import windll

        windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)


def open_game_display(size):
    import pygame

    if sys.platform == "win32":
        from ctypes import windll

        # The game window handles control keys and has no text entry field.
        windll.imm32.ImmDisableIME(get_native_id())
    use_app_taskbar_icon()
    pygame.display.init()
    pygame.display.set_icon(pygame.image.load(str(ICON.with_suffix(".bmp"))))
    screen = pygame.display.set_mode(size)
    pygame.key.stop_text_input()
    return screen


@lru_cache(maxsize=1)
def rgb565_lookup():
    return [bytes((*rgb565(value), 255)) for value in range(65536)]


def rgb565_surface(frame, size):
    import pygame

    words = array("H")
    words.frombytes(frame)
    if sys.byteorder != "little":
        words.byteswap()
    colors = rgb565_lookup()
    pixels = b"".join(colors[value] for value in words)
    return pygame.image.frombytes(pixels, size, "RGBX")


class Sound:
    def __init__(self, resolve_clip, enabled=True, sample_rate=48000, load_clip=None):
        import pygame

        self.resolve_clip = resolve_clip
        self.load_clip = load_sound_clip if load_clip is None else load_clip
        self.channel = None
        self.request = None
        self.clips = {}
        if enabled:
            try:
                pygame.mixer.init(frequency=sample_rate, size=-16, channels=2, buffer=512)
            except pygame.error as error:
                print(f"Audio unavailable: {error}", file=sys.stderr)
            else:
                self.channel = pygame.mixer.Channel(0)

    def play(self, request):
        if self.channel is None:
            return
        if request is None:
            self.channel.stop()
            self.request = None
        elif request == "pause":
            self.channel.pause()
        elif request == "resume":
            self.channel.unpause()
        else:
            path = self.resolve_clip(request)
            if path not in self.clips:
                self.clips[path] = self.load_clip(path)
            self.channel.play(self.clips[path])
            self.request = request

    def active_request(self):
        if self.channel is not None and self.channel.get_busy():
            return self.request
        return None


def load_sound_clip(path):
    """Load a firmware WAV. The single-file build ships the same sound as OGG Vorbis instead."""
    import pygame

    compressed = path.with_suffix(".ogg")
    if getattr(sys, "frozen", False) and compressed.is_file():
        return pygame.mixer.Sound(file=BytesIO(compressed.read_bytes()))
    return pygame.mixer.Sound(file=BytesIO(read_asset(path)))


def percent(text):
    value = int(text)
    if not 0 <= value <= 100:
        raise argparse.ArgumentTypeError("must be between 0 and 100")
    return value


def add_play_options(parser, *, language_help=None):
    parser.add_argument("--size", choices=WINDOW_SIZES, default=DEFAULT_SIZE)
    parser.add_argument("--volume", type=percent, default=DEFAULT_VOLUME)
    parser.add_argument("--mute", action="store_true")
    parser.add_argument("--language", type=int, choices=range(3), default=1, help=language_help)
    parser.add_argument("--speed", choices=SPEED_QUARTERS, default=DEFAULT_SPEED)


def draw_frame(screen, pixels):
    import pygame

    frame = rgb565_surface(pixels, (WIDTH, HEIGHT))
    screen.blit(pygame.transform.scale(frame, screen.get_size()), (0, 0))
    pygame.display.flip()


def load_record(path, label):
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return bytearray(SAVE_SIZE)
    if len(data) != SAVE_SIZE:
        raise ValueError(f"Invalid {label} file: {path}")
    return bytearray(data)


def write_record(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    output = NamedTemporaryFile(dir=path.parent, delete=False)
    temp = Path(output.name)
    try:
        with output:
            output.write(record)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def firmware_sound(assets, args):
    sound = Sound(lambda request: assets / "audio/firmware_wav" / f"{request.address:06X}.wav",
                  enabled=not args.mute and args.volume > 0)
    if sound.channel is not None:
        sound.channel.set_volume(args.volume / 100)
    return sound


def frame_time(clock, speed_quarters, remainder):
    """Game milliseconds for this frame at the chosen speed, and the carried remainder."""
    return divmod(min(clock.tick(60), MAX_FRAME_MS) * speed_quarters + remainder, 4)


class KeyControls:
    """Default input: pass each key press to handle_key(key, game). Subclass for richer input."""

    def __init__(self, handle_key):
        self.handle_key = handle_key

    def handle_event(self, event, game):
        """Handle one pygame event; return True to close the game."""
        import pygame

        return event.type == pygame.KEYDOWN and self.handle_key(event.key, game) == 1

    def advance(self, game, elapsed):
        game.advance(elapsed)

    def style_menu(self, frame):
        return style_start_menu(frame)


def run_game_loop(game, screen, speed, controls, save_path, saved, *, on_close, resume_slot=None):
    import pygame

    clock = pygame.time.Clock()
    clock.tick()
    speed_quarters = SPEED_QUARTERS[speed]
    remainder = 0
    displayed = -1
    active = True
    while active:
        elapsed, remainder = frame_time(clock, speed_quarters, remainder)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if on_close is not None:
                    on_close()
                active = False
                break
            if event.type == pygame.WINDOWFOCUSGAINED:
                pygame.key.stop_text_input()
            if controls.handle_event(event, game):
                active = False
                break
        if active:
            controls.advance(game, elapsed)
            if displayed != game.frame_number:
                pixels = controls.style_menu(game.frame) if game.ui_state == 0 else game.frame
                draw_frame(screen, pixels)
                displayed = game.frame_number
        if game.save != saved:
            write_record(save_path, game.save)
            saved = bytes(game.save)
        if resume_slot is not None:
            resume_slot.update(game)
