"""Regenerate X-Fighter's game_flow.py and runtime-data.bin from the firmware trace."""

import argparse
import json
from pathlib import Path

from sgh_x458.x_fighter.layout import ASSETS, DATA_END, GAME_ENTRY, MANIFEST, ROOT
from tools.firmware import load_rom
from tools.lift import HAND_WRITTEN, Lowering as ThumbLowering


TRACE = Path(__file__).with_name("trace.json")
# Battle routines that sgh_x458.x_fighter.game_rules implements by name.
GAME_RULES = {0x22FE50, 0x22FF54, 0x22FFFC, 0x230744, 0x230768, 0x234480, 0x234724, 0x235600, 0x235ABA}


class Lowering(ThumbLowering):
    game_entry = GAME_ENTRY
    hand_written = HAND_WRITTEN | GAME_RULES
    # Firmware routines that game_rules.py calls back into.
    extra_entries = frozenset({0x232B30, 0x231478, 0x232BAC, 0x22FE50, 0x2335F0, 0x235636, 0x235BE2})
    # Player destruction is wrapped by Game.destroy_player().
    extra_leaders = frozenset({0x2302C4})
    # Read the launcher's reserve-life setting instead of the firmware constant.
    patched_ops = {0x23470A: "r[1] = nz(p, p->reserve_lives);"}

    def save_data(self):
        # Leave only observed data reads, switch tables, and separately identified resources.
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for item in manifest["images"] + manifest["shared_images"]:
            self.mark(int(item["address"], 16), item["size"])
        for start, end in ((0x5995B0, 0x59DCD0), (0x5ABDF5, DATA_END), (0x6AD00C, 0x6AD064)):
            self.mark(start, end - start)
        self.mark(0x6AD064, 45 * 4)  # Score editor character pointers copied to RAM at startup.
        self.mark(0x22B310, 45 * 4)  # The null-terminated characters those pointers reference.
        self.mark(0x22BB50, 0x10)  # Blank string appended when the editor cursor moves right.
        self.mark(0x6AD6BC, 2 * 36 * 4)  # Initialized vertical and horizontal pickup tables.
        self.write_runtime_data(ASSETS / "runtime-data.bin")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, nargs="?", default=TRACE)
    args = parser.parse_args()
    trace = json.loads(args.trace.read_text(encoding="utf-8"))
    lowering = Lowering(load_rom(), trace)
    unknown = lowering.build()
    lowering.emit(ROOT / "game_flow.py", note="Editable gameplay rules are in game_rules.py.")
    lowering.save_data()
    print(f"Translated {len(lowering.translated)} instruction sites into Python control flow")
    print("Unresolved static paths", " ".join(f"{address:X}" for address in sorted(unknown)))


if __name__ == "__main__":
    main()
