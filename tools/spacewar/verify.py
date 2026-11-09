"""Check the SpaceWar Python port against the original ARM callbacks."""

import json
import wave
from hashlib import sha256
from struct import pack

from sgh_x458.runtime.score_editor import SCORE_ENTRY, SCORE_NAME_BUFFER, SCORE_NAME_CURSOR, SCORE_NAME_LIMIT
from sgh_x458.spacewar.layout import ASSETS, DEFAULT_LIVES, MANIFEST, MAX_LIVES, STAGES, STATE_BASE
from sgh_x458.spacewar.game import DRAW_TEXT, ITEM_TIMERS, ITEM_TICKS, LIVES, STAGE, Game
from tools.firmware import ROM_SHA256, load_rom

from .oracle import Oracle


TICK_MS = 204
PHASE = STATE_BASE + 0x2C
SCORE = STATE_BASE + 0x7C


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
        assert self.port.read(STATE_BASE, 0x80) == self.rom.read(STATE_BASE, 0x80), ("game state", where)
        assert self.port.ui_state == self.rom.ui_state, ("menu state", where)
        assert self.port.pending == self.rom.pending and self.port.timers == self.rom.timers, ("timers", where)
        assert self.events[0] == self.events[1], ("audio", where)
        assert self.port.save == self.rom.save, ("score record", where)
        self.frames = self.port.frame_number

    def key(self, code):
        self.step("key", code)

    def ticks(self, count):
        for _ in range(count):
            self.step("advance", TICK_MS)

    def set_word(self, address, value):
        self.step("write", address, pack("<I", value))


def assets_match(rom):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["firmware_sha256"] == ROM_SHA256
    game_data = Game()
    for asset in manifest["images"]:
        address, size = int(asset["address"], 16), asset["size"]
        data = game_data.read(address, size)
        assert data == rom[address:address + size], asset
    for asset in manifest["audio"]:
        address, size = int(asset["address"], 16), asset["size"]
        data = (ASSETS / asset["file"]).read_bytes()
        assert data == rom[address:address + size], asset
        assert sha256(data).hexdigest() == asset["sha256"]
        with wave.open(str(ASSETS / "audio/firmware_wav" / f"{address:06X}.wav"), "rb") as clip:
            assert (clip.getframerate(), clip.getsampwidth(), clip.getnchannels()) == (48000, 2, 2)
            assert clip.getnframes() > 0


def menus(rom):
    frames = 0
    for language in range(3):
        game = Comparison(rom, language)
        game.ticks(3)
        game.key(3)
        assert game.port.ui_state == 4
        game.key(30)
        game.key(2)
        assert game.port.ui_state == 3
        game.key(23)
        game.key(1)
        game.ticks(14)
        game.key(30)
        game.ticks(3)
        assert game.port.state == 1
        frames += game.frames
    return frames


def play_and_save(rom):
    game = Comparison(rom)
    game.key(1)
    game.key(30)
    game.ticks(5)
    game.key(6)
    game.ticks(10)
    game.key(8)
    game.ticks(24)
    assert game.port.word(SCORE) == 2209

    paused = game.port.frame_number
    game.key(23)
    assert not game.port.timers
    game.ticks(5)
    assert game.port.frame_number > paused
    paused = game.port.frame_number
    game.ticks(5)
    assert game.port.frame_number == paused
    game.key(4)
    assert game.port.timers

    for code, ticks in ((6, 25), (2, 25), (4, 25), (8, 25), (6, 11)):
        game.key(code)
        game.ticks(ticks)
    game.set_word(LIVES, 0)
    game.key(2)
    game.ticks(25)
    assert game.port.state == 3
    assert game.port.word(LIVES) == 0xFFFFFFFF
    game.key(7)
    game.ticks(4)
    assert game.port.state == 1 and game.port.word(LIVES) == 3
    # Jump to the second defeat prompt to cover decline, score entry and persistence.
    game.set_word(PHASE, 3)
    game.key(9)
    assert game.port.ui_state == 2
    # A fresh name row: moving right reads the shared UI blank string at
    # 0x22BB54, which must be packed into runtime-data.bin.
    game.key(27)
    game.key(2)
    game.key(2)
    game.key(27)
    game.key(3)
    game.key(30)
    assert any(game.port.save) and game.port.ui_state == 0

    reopened = Comparison(rom, save=bytearray(game.port.save))
    reopened.key(2)
    assert reopened.port.ui_state == 3
    return game.frames + reopened.frames


def stages(rom):
    game = Comparison(rom)
    game.key(1)
    game.key(30)
    for stage in range(10):
        assert game.port.word(STAGE) == stage
        if stage == 0:
            for code, ticks in ((5, 5), (6, 10), (8, 24), (5, 2), (6, 6),
                                (2, 24), (None, 2), (4, 2), (8, 24)):
                if code is not None:
                    game.key(code)
                game.ticks(ticks)
            assert game.port.state == 4 and game.port.word(SCORE) == 4548
        else:
            game.ticks(8)
            game.key(6)
            game.ticks(10)
            game.key(8)
            game.ticks(24)
            # Enter the cleared-stage callback directly to cover the later transitions.
            game.set_word(PHASE, 4)
        game.ticks(2)
        game.key(30)
        game.ticks(2)
        if stage < 9:
            assert game.port.state == 2
            game.key(30)
            assert game.port.state == 1
        else:
            assert game.port.state == 5
            game.ticks(16)
            game.key(30)
            assert game.port.ui_state in (0, 2)
    return game.frames


def custom_campaigns():
    for stage in STAGES:
        game = Game()
        game.configure_campaign(stage, 0, "none")
        game.boot()
        game.key(1)
        assert game.state == 0
        game.key(30)
        game.advance(TICK_MS)
        assert (game.state, game.word(STAGE), game.word(LIVES)) == (1, stage - 1, 0)

    enemy_positions = {}
    for item in ("none", *ITEM_TIMERS):
        game = Game()
        game.configure_campaign(5, 9, item)
        game.boot()
        game.key(1)
        game.key(30)
        game.advance(6 * TICK_MS)
        game.key(6)
        game.advance(TICK_MS)
        assert game.word(STATE_BASE + 4) == (5 if item == "boost" else 3)
        assert game.word(LIVES) == (10 if item == "life" else 9)
        if item in ITEM_TIMERS:
            assert game.word(ITEM_TIMERS[item]) == ITEM_TICKS - 7
        enemy_positions[item] = game.read(0x12DBE24, 4)

        game.store(PHASE, 4)
        game.key(30)
        game.key(30)
        assert game.word(STAGE) == 5
        assert game.word(LIVES) == (10 if item == "life" else 9)
        assert all(game.word(timer) == 0 for timer in ITEM_TIMERS.values())

        game.store(PHASE, 3)
        game.key(7)
        assert game.word(STAGE) == 5 and game.word(LIVES) == 3
        assert all(game.word(timer) == 0 for timer in ITEM_TIMERS.values())
    assert enemy_positions["slow"] != enemy_positions["none"]


def invincible_and_life_limit():
    assert MAX_LIVES == 100, "The launcher uses MAX_LIVES for its spinbox and argument checks"
    assert Game.step_limit > 500_000, "A small region fill already needs ~480k blocks"

    def collide(invincible, lives):
        game = Game()
        game.configure_campaign(1, lives, "none", invincible=invincible)
        game.boot()
        game.key(1)
        game.key(30)
        for _ in range(5):
            game.advance(TICK_MS)
        game.key(6)
        for _ in range(10):
            game.advance(TICK_MS)
        game.key(8)
        for _ in range(24):
            game.advance(TICK_MS)
        game.key(23)
        game.key(4)
        for code, ticks in ((6, 25), (2, 25), (4, 25), (8, 25), (6, 11)):
            game.key(code)
            for _ in range(ticks):
                game.advance(TICK_MS)
        game.store(LIVES, 0)
        game.key(2)
        for _ in range(25):
            game.advance(TICK_MS)
        return game.state, game.word(LIVES)

    assert collide(False, DEFAULT_LIVES) == (3, 0xFFFFFFFF), "The probe must reach a fatal collision"
    assert collide(True, DEFAULT_LIVES) == (1, 0), "Invincibility must keep the ship alive"

    game = Game()
    game.configure_campaign(1, MAX_LIVES, "none")
    game.boot()
    game.key(1)
    game.key(30)
    game.advance(TICK_MS)
    assert (game.state, game.word(STAGE), game.word(LIVES)) == (1, 0, MAX_LIVES)
    assert DRAW_TEXT in game.rules, "Three-digit HUD text is needed at the life limit"


def region_fill_budget():
    def fill(limit):
        game = Game()
        game.step_limit = limit
        game.boot()
        game.key(1)
        game.key(30)
        for code, ticks in ((5, 5), (6, 10), (8, 24), (5, 2), (6, 6),
                            (2, 24), (None, 2), (4, 2), (8, 24)):
            if code is not None:
                game.key(code)
            for _ in range(ticks):
                game.advance(TICK_MS)
        return game.state

    # Closing even a small region costs ~481k translated blocks. The old 500k
    # guard left no room for the half-screen fills that invincibility allows.
    assert Game.step_limit >= 5_000_000
    assert fill(Game.step_limit) == 4, "A region fill must finish within the budget"
    try:
        fill(100_000)
    except RuntimeError as error:
        assert "step limit" in str(error)
    else:
        raise AssertionError("A small budget must still stop runaway control flow")


def desktop_score_entry():
    from sgh_x458.spacewar.play import pygame, score_entry_key

    def editor():
        game = Game()
        game.boot()
        game.key(1)
        game.key(30)
        for _ in range(5):
            game.advance(TICK_MS)
        game.key(6)
        for _ in range(10):
            game.advance(TICK_MS)
        game.key(8)
        for _ in range(24):
            game.advance(TICK_MS)
        game.key(23)
        for _ in range(10):
            game.advance(TICK_MS)
        game.key(4)
        for code, ticks in ((6, 25), (2, 25), (4, 25), (8, 25), (6, 11)):
            game.key(code)
            for _ in range(ticks):
                game.advance(TICK_MS)
        game.store(LIVES, 0)
        game.key(2)
        for _ in range(25):
            game.advance(TICK_MS)
        game.key(7)
        for _ in range(4):
            game.advance(TICK_MS)
        game.store(PHASE, 3)
        game.key(9)
        assert game.ui_state == SCORE_ENTRY
        return game

    game = editor()
    frames = game.frame_number
    for character in "AB1 CD":
        game.type_score_character(character)
    assert game.word(SCORE_NAME_CURSOR) == 6
    assert game.read(game.word(SCORE_NAME_BUFFER), 7) == b"AB1 CD\0"
    assert game.frame_number == frames + 6, "Each typed character must redraw the board"
    game.key(30)
    assert game.ui_state == 0 and bytes(game.save[5:11]) == b"AB1 CD"

    game = editor()
    for _ in range(SCORE_NAME_LIMIT + 3):
        game.type_score_character("Z")
    assert game.word(SCORE_NAME_CURSOR) == SCORE_NAME_LIMIT
    assert game.read(game.word(SCORE_NAME_BUFFER), SCORE_NAME_LIMIT + 1) == (
        b"Z" * SCORE_NAME_LIMIT + b"\0")

    # Desktop keys must reach the Python editor instead of the handset keypad.
    class Recorder:
        def __init__(self):
            self.typed, self.codes = [], []

        def type_score_character(self, character):
            self.typed.append(character)

        def key(self, code):
            self.codes.append(code)

    recorder = Recorder()
    for key in (pygame.K_a, pygame.K_z, pygame.K_5, pygame.K_SPACE):
        score_entry_key(key, recorder)
    assert recorder.typed == ["A", "Z", "5", " "]
    for key in (pygame.K_BACKSPACE, pygame.K_RETURN, pygame.K_LEFT, pygame.K_RIGHT):
        score_entry_key(key, recorder)
    assert recorder.codes == [23, 30, 26, 27]

    # End to end: real SDL key codes must land in the real editor buffer.
    game = editor()
    for key in (pygame.K_a, pygame.K_w, pygame.K_7, pygame.K_SPACE):
        score_entry_key(key, game)
    assert game.read(game.word(SCORE_NAME_BUFFER), 5) == b"AW7 \0"
    assert game.word(SCORE_NAME_CURSOR) == 4
    game.key(30)
    assert bytes(game.save[5:9]) == b"AW7 "


def main():
    rom = load_rom()
    assets_match(rom)
    frames = menus(rom) + play_and_save(rom) + stages(rom)
    custom_campaigns()
    invincible_and_life_limit()
    region_fill_budget()
    desktop_score_entry()
    print(f"Compared {frames} frame submissions, timers, states, audio requests and score records.")
    print("Verified 105 firmware images and 9 SMAF/PCM pairs.")
    print("Verified custom starts on all ten stages, all starting items, and regular stage transitions.")
    print(f"Verified invincibility, the 0-{MAX_LIVES} life limit, the score editor cursor and fill budget.")
    print("Verified desktop score-name typing, the name limit and key mapping.")


if __name__ == "__main__":
    main()
