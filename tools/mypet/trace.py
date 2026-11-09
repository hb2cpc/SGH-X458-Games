"""Collect the ARM execution trace used to lift G133 MyPet offline.

Each scenario drives the original firmware callback through Unicorn. The
observed translation blocks, ROM data reads and bitmap addresses are merged
into trace.json, which extract.py consumes.
"""

import argparse
import json
from pathlib import Path

from tools.firmware import load_rom

from .probe import Probe, png


TRACE = Path(__file__).with_name("trace.json")

MENU_KEYS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 0, 23, 26, 27, 28, 29, 30)
PLAY_KEYS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 0, 23, 26, 27, 28, 29, 30)
ALL_CODES = tuple(range(0, 31))


class Collector:
    def __init__(self, rom, *, shots=None, verbose=False):
        self.rom = rom
        self.blocks = set()
        self.reads = set()
        self.images = set()
        self.shots = shots
        self.verbose = verbose
        self.scenarios = 0
        self.frames = 0
        if shots:
            shots.mkdir(parents=True, exist_ok=True)

    def scenario(self, name, steps, *, language=1, save=None):
        game = Probe(rom=self.rom, language=language, save=save, trace=True, frames=bool(self.shots))
        game.boot()
        for step in steps:
            kind, value = step
            try:
                if kind == "key":
                    game.key(value)
                elif kind == "tick":
                    for _ in range(value):
                        game.advance(600)
                elif kind == "keys":
                    for code in value:
                        game.key(code)
                        game.advance(600)
                elif kind == "icons":
                    # Select each bottom-row icon and confirm it, then exercise
                    # the resulting sub-screen with every key code.
                    for index in range(value):
                        for _ in range(index):
                            game.key(27)
                        game.key(30)
                        for code in ALL_CODES:
                            fresh = Probe(rom=self.rom, language=language, save=save,
                                          trace=True, frames=False)
                            fresh.boot()
                            fresh.key(1)
                            fresh.key(30)
                            for _ in range(index):
                                fresh.key(27)
                            fresh.key(30)
                            fresh.key(code)
                            fresh.advance(600)
                            fresh.advance(600)
                            self._merge(fresh)
                        game.advance(600)
                        game.advance(600)
                else:
                    raise ValueError(f"Unknown step {kind}")
            except Exception as error:
                print(f"  {name}: {kind} {value if kind != 'icons' else ''}: {type(error).__name__}: {error}")
        self._merge(game)
        self.scenarios += 1
        self.frames += game.frame_number
        if self.verbose:
            print(f"  {name}: frames={game.frame_number}, events={len(game.events)}, "
                  f"audio={len(game.audio)}, saves={len(game.saves)}")
        if self.shots and game.snapshots:
            png(self.shots / f"{name}-f{game.frame_number}.png", game.snapshots[-1][1], 2)
        return game.save

    def _merge(self, game):
        self.blocks.update(game.blocks)
        self.reads.update(game.reads)
        self.images.update(bitmap[0] for bitmap in game.bitmaps)

    def write(self):
        trace = {
            "blocks": [[address, size, True] for address, size in sorted(self.blocks)],
            "reads": [[address, size] for address, size in sorted(self.reads)],
            "images": sorted(self.images),
        }
        TRACE.write_text(json.dumps(trace, separators=(",", ":")) + "\n", encoding="ascii")
        return trace


def build(collector, *, full=True):
    print("Collecting MyPet firmware trace")
    # Menus in all three languages, including the animated title and every key.
    for language in range(3):
        collector.scenario(f"menu-{language}", [("keys", MENU_KEYS), ("tick", 4)],
                           language=language)
        collector.scenario(f"menu-start-{language}", [("key", 1), ("tick", 3),
                                                      ("keys", MENU_KEYS)], language=language)
    # Help: automatic page timer, manual paging and exit.
    collector.scenario("help", [("key", 3), ("tick", 8), ("keys", (26, 27, 30, 23)),
                                ("tick", 4)])
    collector.scenario("help-pages", [("key", 3), ("keys", (27,) * 6),
                                      ("keys", (26,) * 6), ("key", 30)])
    # Intro animation and the transition into the pet room.
    collector.scenario("intro", [("key", 1), ("tick", 6), ("keys", MENU_KEYS)])
    collector.scenario("intro-confirm", [("key", 1), ("tick", 2), ("key", 30),
                                         ("tick", 6), ("keys", PLAY_KEYS)])
    # Main room: every key on its own, long-running timers and all icons.
    collector.scenario("play-keys", [("key", 1), ("key", 30), ("keys", PLAY_KEYS)])
    collector.scenario("play-long", [("key", 1), ("key", 30), ("tick", 30 if full else 6)])
    collector.scenario("play-icons", [("key", 1), ("key", 30), ("icons", 7 if full else 2)])
    # Exit saves the pet; restarting from that save exercises the continue path.
    save = collector.scenario("exit", [("key", 1), ("key", 30), ("tick", 3), ("key", 23)])
    collector.scenario("continue", [("key", 4), ("tick", 4), ("keys", PLAY_KEYS)],
                       save=bytearray(save))
    collector.scenario("continue-exit", [("key", 4), ("key", 30), ("tick", 2),
                                         ("key", 23)], save=bytearray(save))
    trace = collector.write()
    print(f"Scenarios={collector.scenarios} frames={collector.frames} "
          f"blocks={len(trace['blocks'])} reads={len(trace['reads'])} images={len(trace['images'])}")
    if trace["blocks"]:
        print(f"Code span {trace['blocks'][0][0]:#x} .. "
              f"{max(a + s for a, s, _ in trace['blocks']):#x}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="shorter scenarios for iteration")
    parser.add_argument("--shots", type=Path, help="directory for frame snapshots")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    collector = Collector(load_rom(), shots=args.shots, verbose=args.verbose)
    build(collector, full=not args.quick)


if __name__ == "__main__":
    main()
