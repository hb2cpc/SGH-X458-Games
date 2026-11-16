"""Extract the three Java games and decode their classes from X458ZCEK1."""

from hashlib import sha256
from io import BytesIO
import json
from struct import unpack_from
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from tools import PROJECT_ROOT
from tools.assets import entry, smaf_tracks
from tools.firmware import load_rom
from tools.java_games.classfile import read_class
from tools.java_games.fonts import midp_fonts


# The file table supplies each JAR's length and ROM address.
GAMES = {
    "bubble_smile": (0x6818CC, "BubbleSmile"),
    "fun2link": (0x681EEC, "Fun2Link"),
    "ultimate_golf": (0x68250C, "MIDPUGC"),
}


def extract(rom, game, table, main):
    output = PROJECT_ROOT / "src" / "sgh_x458" / game / "assets"
    output.mkdir(parents=True, exist_ok=True)
    size, start = unpack_from("<II", rom, table)
    original = rom[start:start + size]
    manifest = {"midlet": main, "jar_rom": f"0x{start:06X}", "jar_size": size,
                "jar_sha256": sha256(original).hexdigest(), "audio": []}
    classes = {}
    with ZipFile(BytesIO(original)) as jar, ZipFile(output / "runtime-data.bin", "w") as runtime:
        if jar.testzip() is not None:
            raise ValueError(f"Corrupt JAR for {game}")
        for info in jar.infolist():
            if info.is_dir() or info.filename.startswith("META-INF/"):
                continue
            path = info.filename
            data = jar.read(info)
            if path.endswith(".class"):
                name, cls = read_class(data)
                classes[name] = cls
            elif path.endswith(".mmf"):
                address = start + info.header_offset
                asset = entry(output, f"audio/original/{address:06X}.mmf", address, data)
                asset.update(resource="/" + path, tracks=smaf_tracks(data))
                manifest["audio"].append(asset)
            else:
                runtime.writestr(ZipInfo(path), data, ZIP_DEFLATED)
        if main not in classes:
            raise ValueError(f"Missing MIDlet entry point {main}")
        runtime.writestr(ZipInfo("classes.json"), json.dumps(classes, separators=(",", ":")),
                         ZIP_DEFLATED)
        # The handset's own MIDP font glyphs, decoded from the firmware font list.
        runtime.writestr(ZipInfo("fonts.json"), json.dumps(midp_fonts(rom), separators=(",", ":")),
                         ZIP_DEFLATED)
    (output / "manifest.json").write_bytes((json.dumps(manifest, indent=2) + "\n").encode())
    print(f"{game}: {len(classes)} classes, {len(manifest['audio'])} audio clips")


def main():
    rom = load_rom()
    for game, (table, name) in GAMES.items():
        extract(rom, game, table, name)


if __name__ == "__main__":
    main()

