"""Offline Unicorn probe for G133 MyPet.

Runs the original ARM callback and records the events, bitmap draws, audio
requests, timers and save traffic. It is an analysis tool: the desktop game
does not import it.
"""

import argparse
import json
import zlib
from pathlib import Path
from struct import pack

from unicorn import UC_HOOK_BLOCK, UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2

from sgh_x458.runtime.bitmap_draw import rgb565
from sgh_x458.runtime.session import HEIGHT, WIDTH
from sgh_x458.mypet.layout import CALLBACK
from tools import PROJECT_ROOT
from tools.assets import chunk
from tools.firmware import load_rom

from .oracle import Oracle

BITMAP_DRAWS = (0x22B100, 0x22B174)
STATIC_END = 0x700000


class Probe(Oracle):
    def __init__(self, rom=None, language=1, save=None, *, trace=False, frames=False):
        self.events = []
        self.bitmaps = []
        self.audio = []
        self.timer_events = []
        self.saves = []
        self.snapshots = []
        self.blocks = set()
        self.reads = set()
        self.trace = trace
        self.frames = frames
        super().__init__(rom=rom, language=language, save=save)
        self.cpu.hook_add(UC_HOOK_CODE, self.observe_event, begin=CALLBACK, end=CALLBACK)
        for address in BITMAP_DRAWS:
            self.cpu.hook_add(UC_HOOK_CODE, self.observe_bitmap, begin=address, end=address)
        if trace:
            self.cpu.hook_add(UC_HOOK_BLOCK, self.observe_block)
            self.cpu.hook_add(UC_HOOK_MEM_READ, self.observe_read)

    def observe_event(self, cpu, address, _size, _user):
        self.events.append((cpu.reg_read(UC_ARM_REG_R0), cpu.reg_read(UC_ARM_REG_R1),
                            cpu.reg_read(UC_ARM_REG_R2), self.frame_number, len(self.audio)))

    def observe_bitmap(self, cpu, address, _size, _user):
        self.bitmaps.append((cpu.reg_read(UC_ARM_REG_R0), cpu.reg_read(UC_ARM_REG_R1),
                             cpu.reg_read(UC_ARM_REG_R2), address))

    def observe_block(self, _cpu, address, size, _user):
        self.blocks.add((address & ~1, size))

    def observe_read(self, _cpu, _access, address, size, _value, _user):
        if address < STATIC_END:
            self.reads.add((address, size))

    def play_audio(self, address, length, _, caller):
        self.audio.append((hex(address), length, hex(caller & ~1), self.frame_number))
        return 1

    def start_timer(self, slot, milliseconds, repeat, caller):
        self.timer_events.append(("start", slot, milliseconds, repeat, self.frame_number))
        return super().start_timer(slot, milliseconds, repeat, caller)

    def stop_timer(self, slot, *_):
        self.timer_events.append(("stop", slot, self.frame_number))
        return super().stop_timer(slot, *_)

    def load_save(self, handle, address, *_):
        self.saves.append(("load", hex(handle), hex(address), self.frame_number))
        return super().load_save(handle, address, *_)

    def write_save(self, handle, address, *_):
        self.saves.append(("write", hex(handle), hex(address), self.frame_number))
        return super().write_save(handle, address, *_)

    def paint(self, address, *_):
        result = super().paint(address, *_)
        if self.frames:
            self.snapshots.append((self.frame_number, self.frame))
        return result

    def report(self, label):
        print(f"[{label}] frames={self.frame_number} events={len(self.events)} "
              f"bitmaps={len(self.bitmaps)} audio={len(self.audio)} timers={len(self.timer_events)} "
              f"saves={len(self.saves)} ui={self.ui_state}")


def png(path, frame, scale=1):
    rows = []
    words = [int.from_bytes(frame[i:i + 2], "little") for i in range(0, len(frame), 2)]
    for y in range(HEIGHT):
        pixels = bytearray()
        for value in words[y * WIDTH:(y + 1) * WIDTH]:
            pixels += bytes(rgb565(value)) * scale
        line = b"\0" + pixels
        for _ in range(scale):
            rows.append(line)
    header = pack(">IIBBBBB", WIDTH * scale, HEIGHT * scale, 8, 2, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                     + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", type=int, default=1)
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--png", type=Path, help="directory for frame snapshots")
    parser.add_argument("--keys", default="", help="comma separated key codes after the menu")
    parser.add_argument("--ticks", type=int, default=0)
    args = parser.parse_args()
    rom = load_rom()
    game = Probe(rom=rom, language=args.language, trace=args.trace, frames=bool(args.png))
    game.boot()
    game.report("menu")
    for text in filter(None, args.keys.split(",")):
        code = int(text, 0)
        result = game.key(code)
        game.report(f"key {code} -> {result}")
    for _ in range(args.ticks):
        game.advance(204)
    if args.ticks:
        game.report(f"ticks x{args.ticks}")
    print("events:", game.events[:40])
    print("bitmaps:", [hex(b[0]) for b in game.bitmaps[:40]])
    print("audio:", game.audio[:20])
    print("timers:", game.timer_events[:20])
    print("saves:", game.saves[:20])
    if args.png:
        args.png.mkdir(parents=True, exist_ok=True)
        for number, frame in game.snapshots[-12:]:
            png(args.png / f"frame-{number:05d}.png", frame)
        print("wrote", len(game.snapshots[-12:]), "snapshots")
    if args.trace:
        trace = {"blocks": [[a, s, True] for a, s in sorted(game.blocks)],
                 "reads": [[a, s] for a, s in sorted(game.reads)],
                 "images": sorted({b[0] for b in game.bitmaps})}
        # Never overwrite the full trace.json produced by trace.py.
        path = PROJECT_ROOT / ".local" / "mypet" / "probe-trace.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(trace, separators=(",", ":")) + "\n", encoding="ascii")
        print("trace:", len(trace["blocks"]), "blocks,", len(trace["reads"]), "reads,",
              len(trace["images"]), "images")


if __name__ == "__main__":
    main()
