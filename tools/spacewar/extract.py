"""Extract SpaceWar resources and convert firmware control flow offline."""

import argparse
import json
from pathlib import Path

from SpaceWar.layout import ASSETS, GAME_ENTRY, INITIAL_DATA, MANIFEST, ROOT
from handset.word_ops import MATH_RULES
from tools.x_fighter.extract_assets import export_game_banks
from tools.x_fighter.firmware import ROM_SHA256, image_record, load_rom
from tools.x_fighter.lift import HAND_WRITTEN, Lowering as ThumbLowering


IMAGE_START, AUDIO_START, AUDIO_END = 0x5ADDD8, 0x6123E5, 0x61A8E3
DATA_END = 0x61ABB8


class Lowering(ThumbLowering):
    hand_written = {
        address for address in HAND_WRITTEN if not 0x22FE50 <= address < 0x235BFC
    } | MATH_RULES.keys()

    def __init__(self, rom, trace):
        super().__init__(rom, trace)
        self.entries = {0x20D1F6, 0x20D7AC, GAME_ENTRY & ~1}
        self.entries.update(address for address, _, thumb in trace["blocks"] if thumb)

    def in_code(self, address):
        return (0x235BFC <= address < 0x237E40 or address == 0x235928
                or super().in_code(address))


def save_data(port, trace):
    for start, end in (
        (0x5860F0, 0x588F80),  # Shared menu images.
        (0x5995B0, 0x59DCD0),  # Registry and common palettes.
        (IMAGE_START, AUDIO_START), (AUDIO_END, DATA_END),
        (0x22B310, 0x22B3C4),  # Score editor characters.
        (0x22B7D0, 0x22B7F8),  # Scoreboard format strings.
        (0x22BB50, 0x22BB60),  # Blank string appended when the editor cursor moves right.
        INITIAL_DATA[0][:2],
    ):
        port.mark(start, end - start)
    for address in trace["images"]:
        port.mark(address, image_record(port.image, address)[5] - address)
    port.write_runtime_data(ASSETS / "runtime-data.bin")


def save_manifest(rom):
    images, audio = export_game_banks(rom, ASSETS, IMAGE_START, AUDIO_START, AUDIO_END, "SpaceWar")
    manifest = dict(firmware_sha256=ROM_SHA256, images=images, audio=audio)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, default=Path(__file__).with_name("trace.json"))
    args = parser.parse_args()
    trace = json.loads(args.trace.read_text(encoding="utf-8"))
    rom = load_rom()
    port = Lowering(rom, trace)
    unknown = port.build()
    port.emit(ROOT / "game_flow.py", note="Static translation of G94 SpaceWar and its shared UI.")
    save_manifest(rom)
    save_data(port, trace)
    print(f"Translated {len(port.translated)} instructions")
    print("Unresolved static paths", " ".join(f"{address:X}" for address in sorted(unknown)))


if __name__ == "__main__":
    main()
