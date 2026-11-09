"""Extract MyPet resources and lift the firmware control flow offline.

Run after trace.py. The desktop game only reads the assets produced here.
"""

import argparse
import json
from pathlib import Path

from MyPet.layout import (
    ASSETS, AUDIO_END, AUDIO_START, DATA_END, GAME_ENTRY, IMAGE_START, MANIFEST,
    ROOT, SHARED_IMAGE_START,
)
from handset.translated_runtime import STATIC_END
from handset.word_ops import MATH_RULES
from tools.x_fighter.extract_assets import export_game_banks
from tools.x_fighter.firmware import ROM_SHA256, image_record, load_rom
from tools.x_fighter.lift import HAND_WRITTEN, Lowering as ThumbLowering


# Thumb-to-ARM stubs served by MyPet/mypet.py. The ARM library behind them is
# not Thumb code and must never be decoded as such.
FLOAT_STUBS = {0x14B9A0, 0x14BB4C, 0x14C174, 0x14BD60}
ARM_LIBRARY = (0x14B900, 0x14C800)


class Lowering(ThumbLowering):
    hand_written = {
        address for address in HAND_WRITTEN if not 0x22FE50 <= address < 0x235BFC
    } | MATH_RULES.keys() | FLOAT_STUBS

    def __init__(self, rom, trace):
        super().__init__(rom, trace)
        self.entries = {0x20D1F6, 0x20D7AC, GAME_ENTRY & ~1}
        self.entries.update(address for address, _, thumb in trace["blocks"]
                            if thumb and not ARM_LIBRARY[0] <= address < ARM_LIBRARY[1])

    def in_code(self, address):
        if ARM_LIBRARY[0] <= address < ARM_LIBRARY[1]:
            return False
        # G133 MyPet follows the SpaceWar block in ROM, past 0x237E40.
        return (0x237E40 <= address < 0x23B000
                or 0x235000 <= address < 0x237E40
                or super().in_code(address))


# Whole banks are packed: the ARM code reads literal pools, shared menu art,
# indexed bitmaps and small legacy bitmaps that a single trace may miss.
DATA_RANGES = (
    (0x14B000, 0x14D200), (0x20D000, 0x20E000), (0x228000, 0x23B000),
    (0x262000, 0x263000), (SHARED_IMAGE_START, DATA_END),
    (0x6A0000, 0x6B0000),
)


def save_data(port, trace):
    for start, end in DATA_RANGES:
        port.mark(start, end - start)
    for address, size in trace["reads"]:
        port.mark(address, size)
    for address in trace["images"]:
        try:
            end = image_record(port.image, address)[5]
        except ValueError:
            continue
        port.mark(address, end - address)
    port.write_runtime_data(ASSETS / "runtime-data.bin", end_address=STATIC_END)


def save_manifest(rom, trace):
    images, audio = export_game_banks(rom, ASSETS, IMAGE_START, AUDIO_START, AUDIO_END, "MyPet")
    shared = []
    for value in trace["images"]:
        if SHARED_IMAGE_START <= value < IMAGE_START:
            try:
                end = image_record(rom, value)[5]
            except ValueError:
                continue
            if not any(item["address"] == hex(value) for item in shared):
                shared.append(dict(address=hex(value), size=end - value))
    manifest = dict(firmware_sha256=ROM_SHA256, images=images,
                    shared_images=shared, audio=audio)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return len(images), len(audio), len(shared)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, default=Path(__file__).with_name("trace.json"))
    args = parser.parse_args()
    trace = json.loads(args.trace.read_text(encoding="utf-8"))
    rom = load_rom()
    port = Lowering(rom, trace)
    unknown = port.build()
    port.emit(ROOT / "game_flow.py", note="Static translation of G133 MyPet and its shared UI.")
    counts = save_manifest(rom, trace)
    save_data(port, trace)
    print(f"Translated {len(port.translated)} instructions")
    print(f"Resources: {counts[0]} game images, {counts[1]} SMAF clips, {counts[2]} shared images")
    outside = [address for address in sorted(unknown)
               if not ARM_LIBRARY[0] <= address < ARM_LIBRARY[1]]
    print("Unresolved static paths", " ".join(f"{address:X}" for address in outside) or "none",
          f"({len(unknown) - len(outside)} ARM library stubs ignored)")


if __name__ == "__main__":
    main()
