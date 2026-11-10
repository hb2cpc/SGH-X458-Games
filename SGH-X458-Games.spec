# Single-file Windows build: no console window, project icon, smallest practical size.
# Build from the project root with Windows x64 Python 3.12 and ffmpeg (with libvorbis) on PATH:
#   python -m PyInstaller --noconfirm --workpath .local\package-build SGH-X458-Games.spec
import shutil
import subprocess
from lzma import FILTER_LZMA2, PRESET_EXTREME, compress
from pathlib import Path

root = Path(SPECPATH).resolve()
src = root / "src"
games = ("x_fighter", "spacewar", "mypet")
packed_dir = root / ".local" / "package-assets"
LZMA2 = {"id": FILTER_LZMA2, "preset": 9 | PRESET_EXTREME, "dict_size": 4 * 1024 * 1024}
OGG_QUALITY = "6"  # Vorbis q6 (~190 kbit/s): audio shrinks from 9 MB of lossless WAV to about 2.5 MB.
FFMPEG = shutil.which("ffmpeg")
if FFMPEG is None:
    raise SystemExit("ffmpeg with libvorbis is required to encode the game audio")


def packed(source, target_dir):
    """xz-compress a large asset; sgh_x458.runtime.read_asset() unpacks it at run time."""
    output = packed_dir / target_dir / f"{source.name}.xz"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(compress(source.read_bytes(), filters=[LZMA2]))
    return str(output), target_dir.as_posix()


def vorbis(wav, target_dir):
    """Encode a firmware WAV to OGG Vorbis; sgh_x458.runtime.desktop.load_sound_clip() prefers it."""
    output = packed_dir / target_dir / f"{wav.stem}.ogg"
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav),
                    "-c:a", "libvorbis", "-q:a", OGG_QUALITY, "-map_metadata", "-1", str(output)], check=True)
    return str(output), target_dir.as_posix()


datas = [(str(src / "sgh_x458" / "resources" / f"icon.{ext}"), "sgh_x458/resources") for ext in ("png", "bmp")]
for game in games:
    # Bundle paths mirror the package so layout.ASSETS resolves inside the EXE.
    assets = Path("sgh_x458") / game / "assets"
    datas.append((str(src / assets / "manifest.json"), assets.as_posix()))
    datas.append(packed(src / assets / "runtime-data.bin", assets))
    if game == "x_fighter":
        datas.append((str(src / assets / "audio" / "playback.json"), (assets / "audio").as_posix()))
    wav_dir = assets / "audio" / "firmware_wav"
    for wav in sorted((src / wav_dir).glob("*.wav")):
        datas.append(vorbis(wav, wav_dir))

a = Analysis(
    [str(src / "sgh_x458" / "__main__.py")],
    pathex=[str(src)],
    datas=datas,
    hiddenimports=[f"sgh_x458.{game}.play" for game in games],
    excludes=[
        # Standard library modules the games never load (imported only lazily or behind try/except).
        "_hashlib", "statistics", "unicodedata", "tarfile", "pickle", "logging", "email",
        "importlib.metadata", "socket", "_socket", "bz2", "_bz2", "difflib", "pydoc",
        # Optional pygame modules: graphics are RGB buffers, audio is WAV on one channel.
        "pygame._freetype", "pygame.font", "pygame.ftfont", "pygame.sysfont", "pygame.imageext",
        "pygame.pypm", "pygame.midi", "pygame.camera", "pygame.pixelarray", "pygame.scrap",
        "pygame.mixer_music", "pygame._debug", "pygame.typing", "pygame.pkgdata",
    ],
    optimize=2,
)

# Rendering uses RGB buffers and playback uses PCM WAV. Keep SDL and its mixer.
unused_dlls = {
    "freetype.dll", "libjpeg-62.dll", "libogg-0.dll", "libopus-0.dll",
    "libopusfile-0.dll", "libpng16-16.dll", "libtiff-5.dll", "libwavpack-1.dll",
    "libwebp-7.dll", "libwebpdemux-2.dll", "libxmp.dll", "portmidi.dll",
    "sdl2_image.dll", "sdl2_ttf.dll",
    # The Universal C Runtime ships with Windows 10 and 11. VCRUNTIME140 stays.
    "ucrtbase.dll",
}
# pygame's hook already places the required SDL DLLs at the bundle root.
duplicate_dlls = {"pygame/sdl2.dll", "pygame/sdl2_mixer.dll"}
a.binaries = [
    entry for entry in a.binaries
    if Path(entry[0]).name.lower() not in unused_dlls
    and not Path(entry[0]).name.lower().startswith("api-ms-win-")
    and Path(entry[0]).as_posix().lower() not in duplicate_dlls
]


def needed_data(name):
    path = Path(name).as_posix()
    if path == "pygame/freesansbold.ttf":
        return False
    # The launcher needs Tcl/Tk scripts and ttk themes only: no time zones, translations,
    # demo images or obsolete packages. Keep the Windows code page encodings.
    if path.startswith(("_tcl_data/tzdata/", "_tcl_data/msgs/", "_tk_data/msgs/", "_tk_data/images/",
                        "_tcl_data/http1.0/", "_tcl_data/opt0.4/")):
        return False
    if path.startswith("_tcl_data/encoding/"):
        return Path(path).stem.startswith(("cp", "ascii", "iso8859-1"))
    return True


a.datas = [entry for entry in a.datas if needed_data(entry[0])]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="SGH-X458-Games",
    console=False,
    upx=False,
    icon=str(src / "sgh_x458" / "resources" / "icon.ico"),
)
