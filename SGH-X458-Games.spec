# Build from the project root with Windows x64 Python 3.12.
from lzma import FILTER_DELTA, FILTER_LZMA2, PRESET_EXTREME, compress
from pathlib import Path

root = Path(SPECPATH).resolve()
src = root / "src"
games = ("x_fighter", "spacewar", "mypet")
packed_dir = root / ".local" / "package-assets"
datas = []
for game in games:
    # Bundle paths mirror the package so layout.ASSETS resolves inside the EXE.
    assets = Path("sgh_x458") / game / "assets"
    for name in ("manifest.json", "runtime-data.bin"):
        datas.append((str(src / assets / name), assets.as_posix()))
    audio = assets / "audio"
    if game == "x_fighter":
        datas.append((str(src / audio / "playback.json"), audio.as_posix()))
    wav_dir = audio / "firmware_wav"
    packed_wav_dir = packed_dir / wav_dir
    packed_wav_dir.mkdir(parents=True, exist_ok=True)
    for wav in sorted((src / wav_dir).glob("*.wav")):
        pcm_file = wav.read_bytes()
        lzma2 = {"id": FILTER_LZMA2, "preset": 9 | PRESET_EXTREME, "dict_size": 4 * 1024 * 1024}
        packed = packed_wav_dir / f"{wav.name}.xz"
        packed.write_bytes(min(
            compress(pcm_file, filters=[lzma2]),
            compress(pcm_file, filters=[{"id": FILTER_DELTA, "dist": 4}, lzma2]),
            key=len,
        ))
        datas.append((str(packed), wav_dir.as_posix()))

a = Analysis(
    [str(src / "sgh_x458" / "__main__.py")],
    pathex=[str(src)],
    datas=datas,
    hiddenimports=[f"sgh_x458.{game}.play" for game in games],
    excludes=["_hashlib", "statistics", "pygame._freetype", "pygame.font", "pygame.imageext", "pygame.pypm"],
    optimize=1,
)

# Rendering uses RGB buffers and playback uses PCM WAV. Keep SDL and its mixer.
unused_sdl = {
    "freetype.dll", "libjpeg-62.dll", "libogg-0.dll", "libopus-0.dll",
    "libopusfile-0.dll", "libpng16-16.dll", "libtiff-5.dll", "libwavpack-1.dll",
    "libwebp-7.dll", "libwebpdemux-2.dll", "libxmp.dll", "portmidi.dll",
    "sdl2_image.dll", "sdl2_ttf.dll",
}
# pygame's hook already places the required SDL DLLs at the bundle root.
duplicate_sdl = {"pygame/sdl2.dll", "pygame/sdl2_mixer.dll"}
a.binaries = [
    entry for entry in a.binaries
    if Path(entry[0]).name.lower() not in unused_sdl and Path(entry[0]).as_posix().lower() not in duplicate_sdl
]
a.datas = [entry for entry in a.datas if Path(entry[0]).as_posix() != "pygame/freesansbold.ttf"]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="SGH-X458-Games",
    console=False,
    upx=False,
    icon="NONE",
)
