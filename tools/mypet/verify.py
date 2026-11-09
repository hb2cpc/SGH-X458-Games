"""Check the MyPet Python port against the original ARM callbacks.

Every step compares the RGB565 frame, the whole non-stack RAM image, the
timer queue, audio requests and the 76-byte save record. Run with the research
dependencies installed and the firmware image present.
"""

import json
import wave
from datetime import datetime as RealDateTime, timedelta
from hashlib import sha256
from struct import pack
from unittest.mock import patch

from unicorn import UC_HOOK_CODE

from handset import session
from MyPet.layout import ASSETS, MANIFEST, SAVE_BUFFER
from MyPet.mypet import Game, READ_CLOCK
from tools.x_fighter.firmware import ROM_SHA256, load_rom

from .oracle import Oracle

class FixedDateTime:
    """MyPet reads the handset clock, so both sides must see the same second."""

    @classmethod
    def now(cls):
        return RealDateTime(2026, 11, 8, 22, 30, 0)


RAM_BASE = 0x01000000
RAM_COMPARE = 0x3FE000  # Exclude the stack: transient frames differ by design.
TICK_MS = 600
MENU_KEYS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 0, 23, 26, 27, 28, 29, 30)
PLAY_KEYS = MENU_KEYS


class Comparison:
    def __init__(self, rom, language=1, save=None):
        self.events = [], []
        self.port = Game(language=language, on_audio=self.events[0].append, save=save)
        self.rom = Oracle(rom=rom, language=language, on_audio=self.events[1].append,
                          save=None if save is None else bytearray(save))
        self.frames = 0
        self.step("boot")

    def step(self, method, *args):
        first = getattr(self.port, method)(*args)
        second = getattr(self.rom, method)(*args)
        where = (method, args, self.port.frame_number)
        assert first == second, ("return value", where)
        assert self.port.frame == self.rom.frame, ("RGB565 frame", where)
        assert self.port.frame_number == self.rom.frame_number, ("frame count", where)
        assert bytes(self.port.ram[:RAM_COMPARE]) == bytes(
            self.rom.cpu.mem_read(RAM_BASE, RAM_COMPARE)), ("RAM image", where)
        assert self.port.ui_state == self.rom.ui_state, ("menu state", where)
        assert self.port.pending == self.rom.pending, ("timer queue", where)
        assert self.port.timers == self.rom.timers, ("timers", where)
        assert self.port.audio_events == self.rom.audio_events, ("audio log", where)
        assert self.events[0] == self.events[1], ("audio requests", where)
        assert self.port.save == self.rom.save, ("save record", where)
        self.frames = self.port.frame_number

    def key(self, code):
        self.step("key", code)

    def ticks(self, count, milliseconds=TICK_MS):
        for _ in range(count):
            self.step("advance", milliseconds)

    def keys(self, codes):
        for code in codes:
            self.key(code)
            self.ticks(1)

    def set_word(self, address, value):
        self.step("write", address, pack("<I", value))


def assets_match(rom):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["firmware_sha256"] == ROM_SHA256
    game = Game()
    for asset in manifest["images"] + manifest["shared_images"]:
        address, size = int(asset["address"], 16), asset["size"]
        assert game.read(address, size) == rom[address:address + size], asset
    for asset in manifest["audio"]:
        address, size = int(asset["address"], 16), asset["size"]
        data = (ASSETS / asset["file"]).read_bytes()
        assert data == rom[address:address + size], asset
        assert sha256(data).hexdigest() == asset["sha256"]
        with wave.open(str(ASSETS / "audio/firmware_wav" / f"{address:06X}.wav"), "rb") as clip:
            assert (clip.getframerate(), clip.getsampwidth(), clip.getnchannels()) == (48000, 2, 2)
            assert clip.getnframes() > 0
    return len(manifest["images"]), len(manifest["audio"])


def menus(rom):
    frames = 0
    for language in range(3):
        game = Comparison(rom, language)
        game.ticks(3)
        for code in (2, 4, 5, 6, 7, 8, 9, 0, 26, 27, 28, 29, 30):
            game.key(code)
        game.key(3)
        assert game.port.ui_state == 4
        game.ticks(2)
        game.key(23)  # On the first help page only CLR returns to the menu.
        assert game.port.ui_state == 0
        game.key(1)
        assert game.port.ui_state == 1
        game.ticks(3)
        frames += game.frames
    return frames


def help_pages(rom):
    game = Comparison(rom)
    game.key(3)
    assert game.port.ui_state == 4
    game.ticks(3)
    for code in (27,) * 5 + (26,) * 5 + (30,):
        game.key(code)
        game.ticks(1)
    assert game.port.ui_state == 0
    game.ticks(3)
    return game.frames


def intro(rom):
    game = Comparison(rom)
    game.key(1)
    game.ticks(6)
    for code in (2, 3, 4, 5, 6, 7, 8, 9, 0, 28, 29):
        game.key(code)
        game.ticks(1)
    game.key(30)
    game.ticks(3)
    assert game.port.word(SAVE_BUFFER) != 0  # The pet record is now populated.
    return game.frames


def play(rom):
    game = Comparison(rom)
    game.key(1)
    game.key(30)
    game.ticks(4)
    for code in PLAY_KEYS:
        if code == 23:  # Leave the room at the end of this scenario.
            continue
        game.key(code)
        game.ticks(1)
    for selected in range(7):
        game.key(27)
        game.key(30)
        game.ticks(2)
    game.ticks(12, 260)
    game.ticks(3, 204)
    return game.frames


def save_and_continue(rom):
    game = Comparison(rom)
    game.key(1)
    game.key(30)
    game.ticks(5)
    game.key(6)
    game.key(30)
    game.ticks(4)
    game.key(23)
    saved = bytes(game.port.save)
    assert saved != bytes(len(saved))
    assert game.port.read(SAVE_BUFFER, len(saved)) == saved
    again = Comparison(rom, save=bytearray(saved))
    assert bytes(again.port.save) == saved
    again.key(4)
    again.ticks(4)
    for code in (26, 27, 30, 5, 23):
        again.key(code)
        again.ticks(1)
    return game.frames + again.frames


def live_clock(rom):
    game = Comparison(rom)

    def sync_rom_clock(*_):
        game.rom.sync_clock()

    game.rom.cpu.hook_add(UC_HOOK_CODE, sync_rom_clock, begin=READ_CLOCK, end=READ_CLOCK)
    start = FixedDateTime.now()
    game.key(1)
    with patch.object(FixedDateTime, "now", return_value=start + timedelta(hours=2)):
        game.key(30)
        assert game.port.read(SAVE_BUFFER + 1, 6) == bytes((26, 11, 9, 0, 30, 0))
    with patch.object(FixedDateTime, "now", return_value=start + timedelta(hours=6)):
        game.key(23)
        assert game.port.save[7:13] == bytes((26, 11, 9, 4, 30, 0))
    saved_stats = game.port.save[15:23]
    with patch.object(FixedDateTime, "now", return_value=start + timedelta(hours=12)):
        game.key(4)
        game.ticks(1, 260)
        assert game.port.read(SAVE_BUFFER + 15, 8) != saved_stats
    return game.frames


@patch.object(session, "datetime", FixedDateTime)
def main():
    rom = load_rom()
    images, audio = assets_match(rom)
    total = 0
    for name, check in (("menus", menus), ("help", help_pages), ("intro", intro),
                        ("play", play), ("save/continue", save_and_continue), ("live clock", live_clock)):
        frames = check(rom)
        total += frames
        print(f"{name}: {frames} frames matched")
    print(f"MyPet verified: {total} frames, {images} bitmaps, {audio} SMAF clips, "
          "full RAM/timers/audio/save match")


if __name__ == "__main__":
    main()
