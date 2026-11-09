"""Export the game's ROM resource bank with addresses and hashes."""

import argparse
import json
import zlib
from hashlib import sha256
from pathlib import Path
from struct import pack, unpack_from

from handset.bitmap_draw import rgb565
from tools import PROJECT_ROOT

from .firmware import (
    AUDIO_END, AUDIO_START, IMAGE_START, PALETTE, PALETTE_SIZE, PALETTE_VARIANTS,
    ROM_SHA256, X_FIGHTER_DATA_END,
    audio_record, image_record, load_rom, palette,
)


# Common menu/score graphics used by the ROM dispatcher in the three languages.
SHARED_IMAGES = (
    0x5860F0, 0x586B55, 0x586CBE, 0x586DDD, 0x587040, 0x5872AD, 0x587743,
    0x58796C, 0x587BD9, 0x587E46, 0x588328, 0x58858B, 0x5887A2, 0x588A17, 0x588F15,
)
STAGE_MAP = 0x5ABFC8
MAP_ROWS, MAP_COLUMNS, STAGES = 57, 9, 3


def rgba_palette(colors):
    return [bytes((*rgb565(color), 0 if index == 4 else 255)) for index, color in enumerate(colors)]


def chunk(tag, data):
    return pack(">I", len(data)) + tag + data + pack(">I", zlib.crc32(tag + data))


def png(record, colors):
    width, height, _, _, bits, _, remap, data = record
    mask = (1 << bits) - 1
    # The bitmap stream is continuous across rows, MSB first, padded to 16 bits.
    indices = [remap[(data[i // 8] >> (8 - bits - i % 8)) & mask]
               for i in range(0, width * height * bits, bits)]
    scanlines = b"".join(b"\0" + b"".join(colors[c] for c in indices[y:y + width])
                         for y in range(0, len(indices), width))
    header = pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b"")


def entry(output, name, address, data):
    path = output / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"address": f"0x{address:06X}", "size": len(data), "file": name,
            "sha256": sha256(data).hexdigest()}


def export_image(rom, output, address, colors, group):
    record = image_record(rom, address)
    width, height, x, y, bits, end, _, _ = record
    name = f"{address:06X}"
    item = entry(output, f"{group}/indexed/{name}.bin", address, rom[address:end])
    preview = entry(output, f"{group}/png/{name}.png", address, png(record, colors))
    item.update(width=width, height=height, anchor=[x, y], bits=bits, png=preview["file"],
                png_sha256=preview["sha256"])
    return end, item


def export_stage_map(rom, output):
    stride = MAP_COLUMNS * 4
    stages = []
    for stage in range(STAGES):
        start = STAGE_MAP + stage * MAP_ROWS * stride
        rows = [unpack_from(f"<{MAP_COLUMNS}i", rom, start + row * stride) for row in range(MAP_ROWS)]
        stages.append({"stage": stage + 1, "address": f"0x{start:06X}", "rows_in_rom_order": rows})
    data = (json.dumps(stages, separators=(",", ":")) + "\n").encode()
    item = entry(output, "tables/stage_maps.json", STAGE_MAP, data)
    item["rom_size"] = STAGES * MAP_ROWS * stride
    return item


def extract(rom, output, theme, variant):
    colors = rgba_palette(palette(rom, theme, variant))
    images, audio = [], []
    address = IMAGE_START
    while address < AUDIO_START:
        address, item = export_image(rom, output, address, colors, "graphics")
        images.append(item)
    if address != AUDIO_START:
        raise ValueError("Graphics bank does not end at the first SMAF header")
    shared = [export_image(rom, output, address, colors, "graphics/shared")[1]
              for address in SHARED_IMAGES]
    address = AUDIO_START
    while address < AUDIO_END:
        end, data = audio_record(rom, address)
        item = entry(output, f"audio/original/{address:06X}.mmf", address, data)
        item["tracks"] = smaf_tracks(data)
        pointer = pack("<I", address)
        item["thumb_literal_addresses"] = [f"0x{pos:06X}" for pos in range(0x228000, 0x235BFC, 4)
                                           if rom[pos:pos + 4] == pointer]
        audio.append(item)
        address = end
    if address != AUDIO_END:
        raise ValueError("SMAF bank did not end at the expected boundary")
    palette_end = PALETTE + 7 * PALETTE_VARIANTS * PALETTE_SIZE
    palettes = entry(output, "graphics/palette_rgb565.bin", PALETTE, rom[PALETTE:palette_end])
    tables = entry(output, "tables/5ABDF5-5ADDD7.bin", AUDIO_END, rom[AUDIO_END:X_FIGHTER_DATA_END])
    manifest = {"firmware_sha256": ROM_SHA256, "png_palette": {"theme": theme, "variant": variant},
                "images": images, "shared_images": shared, "audio": audio, "table_region": tables,
                "palette_bank": palettes, "stage_maps": export_stage_map(rom, output)}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return len(images), len(shared), len(audio)


def smaf_tracks(data):
    names = []
    cursor = 8
    while cursor < len(data) - 2:
        name = data[cursor:cursor + 4]
        size = int.from_bytes(data[cursor + 4:cursor + 8], "big")
        cursor += 8 + size
        if cursor > len(data) - 2:
            raise ValueError("SMAF chunk overlaps the checksum")
        names.append(name.rstrip(b"\0").decode("ascii", errors="backslashreplace"))
    if cursor != len(data) - 2:
        raise ValueError("SMAF track chunks do not end at the checksum")
    return names


def export_game_banks(rom, output, image_start, audio_start, audio_end, game):
    """Export image metadata and original audio for games that pack the image bank."""
    images, audio = [], []
    address = image_start
    while address < audio_start:
        width, height, x, y, bits, end, _, _ = image_record(rom, address)
        images.append(dict(address=f"0x{address:06X}", size=end - address, width=width,
                           height=height, anchor=[x, y], bits=bits))
        address = end
    if address != audio_start:
        raise ValueError(f"Unexpected end of the {game} image bank")

    while address < audio_end:
        end, data = audio_record(rom, address)
        asset = entry(output, f"audio/original/{address:06X}.mmf", address, data)
        asset["tracks"] = smaf_tracks(data)
        audio.append(asset)
        address = end
    if address != audio_end:
        raise ValueError(f"Unexpected end of the {game} audio bank")
    return images, audio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / ".local" / "x-fighter-extract",
                        help="export directory (default: .local/x-fighter-extract)")
    parser.add_argument("--theme", type=int, choices=range(7), default=3)
    parser.add_argument("--variant", type=int, choices=range(6), default=0)
    args = parser.parse_args()
    images, shared, audio = extract(load_rom(), args.output, args.theme, args.variant)
    print(f"Exported {images} game graphics, {shared} shared graphics and {audio} original SMAF files"
          f" to {args.output.resolve()}")


if __name__ == "__main__":
    main()
