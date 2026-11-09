"""Verify ROM asset exports and exercise original code paths without opening a window."""

import argparse
import json
import wave
from contextlib import closing
from hashlib import sha256
from struct import pack, unpack

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R3

from sgh_x458.runtime.session import FRAME_BYTES, HEIGHT, WIDTH
from sgh_x458.x_fighter.game import Game as SourceGame
from sgh_x458.x_fighter.layout import ASSETS, AUDIO_START, IMAGE_START, STATE
from tools.assets import png, rgba_palette
from tools.firmware import image_record, load_rom, palette

from .extract_assets import SHARED_IMAGES
from .oracle import Oracle as Game


def check_assets(rom):
    root = ASSETS
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    graphics = manifest["images"] + manifest["shared_images"]
    assert len(manifest["images"]) == 182
    assert len(manifest["shared_images"]) == len(SHARED_IMAGES)
    assert len(manifest["audio"]) == 15
    with closing(SourceGame()) as source:
        for item in graphics + [manifest["table_region"], manifest["palette_bank"]]:
            address = int(item["address"], 16)
            expected = rom[address:address + item["size"]]
            assert sha256(expected).hexdigest() == item["sha256"], item["file"]
            assert source.read(address, item["size"]) == expected, item["file"]
    for item in manifest["audio"]:
        address = int(item["address"], 16)
        smaf = (root / item["file"]).read_bytes()
        assert smaf == rom[address:address + item["size"]]
        assert sha256(smaf).hexdigest() == item["sha256"]
        with wave.open(str(root / "audio" / "firmware_wav" / (item["address"][2:] + ".wav"))) as clip:
            assert clip.getnframes() > 0 and clip.getsampwidth() == 2
            assert any(clip.readframes(clip.getnframes()))
    return graphics, manifest["png_palette"]


def compare_draws(rom, graphics, selection):
    game = Game(rom)
    game.boot()
    game.call(0x22A30D, selection["theme"])
    game.call(0x22A2C1, selection["variant"])
    colors = palette(rom, **selection)
    clear = next(c for c in range(65536) if c not in colors)
    buffer = game.word(0x0103EE78 + 8)
    rgba = rgba_palette(colors)
    for item in graphics:
        address = int(item["address"], 16)
        record = image_record(rom, address)
        width, height, x, y, bits, _, remap, data = record
        assert sha256(png(record, rgba)).hexdigest() == item["png_sha256"], item["png"]
        game.cpu.mem_write(buffer, pack("<H", clear) * (WIDTH * HEIGHT))
        game.call(0x22B101, address, x, y)
        actual = unpack(f"<{WIDTH * HEIGHT}H", game.cpu.mem_read(buffer, FRAME_BYTES))
        expected = [clear] * (WIDTH * HEIGHT)
        for i in range(width * height):
            bit = i * bits
            index = remap[(data[bit // 8] >> (8 - bits - bit % 8)) & ((1 << bits) - 1)]
            if index != 4:
                expected[(i // width) * WIDTH + (i % width)] = colors[index]
        assert actual == tuple(expected), item["address"]


def compare_source_draws(rom, graphics, selection):
    oracle = Game(rom)
    with closing(SourceGame()) as source:
        for game in (source, oracle):
            game.boot()
            game.call(0x22A30D, selection["theme"])
            game.call(0x22A2C1, selection["variant"])
        clear = b"\xef\xbe" * (WIDTH * HEIGHT)
        buffer = oracle.word(0x103EE78 + 8)
        assert buffer == source.word(0x103EE78 + 8)
        for item in graphics:
            address = int(item["address"], 16)
            for x, y, mirror in ((64, 80, 0), (2, 4, 0), (126, 154, 1), (4, 2, 1)):
                for game in (source, oracle):
                    game.write(buffer, clear)
                source.r[3] = mirror
                oracle.cpu.reg_write(UC_ARM_REG_R3, mirror)
                source.call(0x22B175, address, x, y)
                oracle.call(0x22B175, address, x, y)
                assert source.read(buffer, FRAME_BYTES) == oracle.read(buffer, FRAME_BYTES), (hex(address), x, y, mirror)


def begin_game(game, aircraft=1):
    game.key(1)
    game.advance(300)
    game.key(1)
    game.advance(300)
    assert game.state == 2
    for _ in range(aircraft - 1):
        game.key(7)
    game.key(9)
    game.advance(2800)
    assert game.state == 4 and game.word(STATE + 0x34) == 1


def play_until_score(rom):
    audio = []
    game = Game(rom, on_audio=audio.append)
    game.boot()
    menu = game.frame
    game.key(3)
    assert game.ui_state == 4 and game.frame != menu
    game.key(30)
    game.key(2)
    assert game.ui_state == 3 and game.frame != menu
    game.key(30)
    begin_game(game)
    game.key(23)
    paused = game.frame
    game.advance(5000)
    assert game.frame == paused and not game.timers
    game.key(23)
    game.advance(500)
    assert game.frame != paused and game.timers
    assert "pause" in audio and "resume" in audio
    game.key(9)
    game.advance(500)
    assert any(address == 0x5A800D for _, address in game.audio_events)
    for _ in range(100):
        game.advance(5000)
        if game.ui_state != 1:
            break
    assert game.state == 5 and game.ui_state == 2
    score = game.word(STATE + 0x78)
    assert score > 0 and any(address == 0x5A7066 for _, address in game.audio_events)
    for key in (2, 3, 4, 30):
        game.key(key)
        game.advance(1000)
    assert game.ui_state == 0 and game.save[0] == 0x99
    loaded = Game(rom, save=bytearray(game.save))
    loaded.boot()
    loaded.key(2)
    assert loaded.ui_state == 3 and loaded.save == game.save


def play_all_stages(rom):
    game = Game(rom)
    # Verification probe only. Suppress player destruction and keep boss damage in ROM.
    game.hooks[0x2302C4] = game.no_device_action
    game.cpu.hook_add(UC_HOOK_CODE, game.dispatch_hook, begin=0x2302C4, end=0x2302C4)
    game.boot()
    begin_game(game, aircraft=2)
    boss_health = {}
    for step in range(8000):
        game.advance(254, 9 if step % 11 == 0 else None)
        stage = game.word(STATE + 0x34)
        if game.word(STATE + 0x18) == 1:
            boss_health.setdefault(stage, game.word(0x012DBB34))
        if game.ui_state != 1:
            break
    assert boss_health == {1: 900, 2: 2000, 3: 3000}, boss_health
    assert game.word(0x012DBB34) == 0 and game.state == 5 and game.ui_state == 2
    print(f"All three bosses cleared in ROM under the player-destruction probe ({game.time_units // 13000}s)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-stages", action="store_true")
    args = parser.parse_args()
    rom = load_rom()
    graphics, selection = check_assets(rom)
    assert int(graphics[0]["address"], 16) == IMAGE_START
    assert int(graphics[181]["address"], 16) + graphics[181]["size"] == AUDIO_START
    compare_draws(rom, graphics, selection)
    compare_source_draws(rom, graphics, selection)
    play_until_score(rom)
    print(f"Verified {len(graphics)} bitmaps against ROM drawing, 15 SMAF files and game-over score save")
    if args.all_stages:
        play_all_stages(rom)


if __name__ == "__main__":
    main()
