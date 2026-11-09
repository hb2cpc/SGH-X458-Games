"""Address-preserving reader for the SGH-X458 X458ZCEK1 ROM."""

from hashlib import sha256
from pathlib import Path
from struct import unpack_from


from tools import PROJECT_ROOT


ROM_PATH = PROJECT_ROOT / "firmware" / "X458ZCEK1.s3"
ROM_SHA256 = "2e39ad4672c708498419aaca63843e500f6798f2d94171cd890b9ef86f1e9fad"
ROM_END = 0xD63DD8
PALETTE = 0x599D70
PALETTE_SIZE = 182 * 2
PALETTE_VARIANTS = 6
GAME_ENTRY = 0x235A35
IMAGE_START = 0x59DCD0
AUDIO_START = 0x5A4FEC
AUDIO_END = 0x5ABDF5
X_FIGHTER_DATA_END = 0x5ADDD8


def load_rom(path=ROM_PATH):
    encoded = Path(path).read_bytes()
    if sha256(encoded).hexdigest() != ROM_SHA256:
        raise ValueError("Expected the X458ZCEK1 firmware with the documented SHA-256")
    image = bytearray(b"\xff" * ROM_END)
    for number, line in enumerate(encoded.splitlines(), 1):
        record = bytes.fromhex(line[2:].decode("ascii"))
        if record[0] != len(record) - 1 or sum(record) & 255 != 255:
            raise ValueError(f"Invalid S-record at line {number}")
        if line.startswith(b"S3"):
            address = int.from_bytes(record[1:5], "big")
            payload = record[5:-1]
            if address + len(payload) > ROM_END:
                raise ValueError(f"Invalid load address at line {number}")
            image[address:address + len(payload)] = payload
    return bytes(image)


def palette(rom, theme, variant=0):
    address = PALETTE + (theme * PALETTE_VARIANTS + variant) * PALETTE_SIZE
    return unpack_from("<182H", rom, address)


def image_record(rom, address):
    kind, width, height, anchor_x, anchor_y = unpack_from("<BBBbb", rom, address)
    if kind not in range(5, 9) or not width or not height:
        raise ValueError(f"Unexpected X-Fighter image at {address:#x}")
    bits = 1 << (kind - 5)
    table_size = 0 if bits == 8 else 1 << bits
    start = address + 5 + table_size
    end = start + ((width * height * bits + 15) // 16) * 2
    remap = rom[address + 5:start] if table_size else bytes(range(256))
    return width, height, anchor_x, anchor_y, bits, end, remap, rom[start:end]


def audio_record(rom, address):
    if rom[address:address + 4] != b"MMMD":
        raise ValueError(f"Missing SMAF container at {address:#x}")
    end = address + 8 + unpack_from(">I", rom, address + 4)[0]
    if end > len(rom) or end < address + 10:
        raise ValueError(f"Invalid SMAF length at {address:#x}")
    return end, rom[address:end]
