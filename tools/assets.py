"""Bitmap, PNG and SMAF export helpers shared by the per-game extractors."""

import zlib
from hashlib import sha256
from struct import pack

from sgh_x458.runtime.bitmap_draw import rgb565

from .firmware import audio_record, image_record


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
