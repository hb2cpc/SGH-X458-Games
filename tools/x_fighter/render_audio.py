"""Render the extracted MMF files with an external Yamaha MA-3 engine (offline)."""

import argparse
import ctypes as ct
import json
import wave
from hashlib import sha256
from pathlib import Path
from struct import unpack
from time import monotonic, sleep

from tools import X_FIGHTER_DIR


ASSETS = X_FIGHTER_DIR / "assets"
WORD = ct.c_uint32
PREROLL_MS = 80


class Ma3Renderer:
    def __init__(self, library):
        if ct.sizeof(ct.c_void_p) != 4:
            raise RuntimeError("The Yamaha MA-3 engine requires 32-bit Windows Python")
        self.ma3 = ct.CDLL(str(library.resolve()))
        self.winmm = ct.WinDLL("winmm")
        self.protect = ct.WinDLL("kernel32").VirtualProtect
        self.protect.argtypes = [ct.c_void_p, ct.c_size_t, WORD, ct.POINTER(WORD)]
        self.protect.restype = ct.c_int
        self.hooks = []
        self.buffers = []
        self.format = None
        try:
            self.intercept("waveOutOpen", self.open_output, 6)
            self.intercept("waveOutWrite", self.write_output, 3)
            self.check("Initialize")
        except Exception:
            self.restore_imports()
            raise

    def import_slot(self, name):
        base = self.ma3._handle
        pe_offset = WORD.from_address(base + 0x3C).value
        optional = base + pe_offset + 24
        imports = WORD.from_address(optional + 104).value
        descriptor = base + imports
        while True:
            names, _, _, dll_name, slots = unpack("<5I", ct.string_at(descriptor, 20))
            if not dll_name:
                break
            if ct.string_at(base + dll_name).lower() == b"winmm.dll":
                index = 0
                while (entry := WORD.from_address(base + names + index * 4).value):
                    if entry < 0x80000000 and ct.string_at(base + entry + 2) == name.encode("ascii"):
                        return base + slots + index * 4
                    index += 1
            descriptor += 20
        raise RuntimeError(f"The Yamaha engine has no {name} import")

    def replace_pointer(self, address, value):
        old = WORD()
        if not self.protect(address, 4, 4, ct.byref(old)):
            raise ct.WinError()
        WORD.from_address(address).value = value
        self.protect(address, 4, old.value, ct.byref(WORD()))

    def intercept(self, name, handler, argument_count):
        signature = [WORD] * argument_count
        original = getattr(self.winmm, name)
        original.argtypes = signature
        original.restype = WORD
        callback = ct.WINFUNCTYPE(WORD, *signature)(lambda *args: handler(original, *args))
        slot = self.import_slot(name)
        value = WORD.from_address(slot).value
        self.replace_pointer(slot, ct.cast(callback, ct.c_void_p).value)
        self.hooks.append((slot, value, callback))

    def restore_imports(self):
        for slot, value, _ in reversed(self.hooks):
            self.replace_pointer(slot, value)
        self.hooks.clear()

    def open_output(self, original, handle, device, wfx, callback, instance, flags):
        self.format = unpack("<HHIIHH", ct.string_at(wfx, 16))
        return original(handle, device, wfx, callback, instance, flags)

    def write_output(self, original, device, header, header_size):
        address, length = unpack("<II", ct.string_at(header, 8))
        self.buffers.append(ct.string_at(address, length))
        ct.memset(address, 0, length)  # Keep the live Windows output silent during the offline capture.
        return original(device, header, header_size)

    def call(self, name, *arguments):
        return getattr(self.ma3, "MaSound_" + name)(*arguments)

    def check(self, name, *arguments):
        result = self.call(name, *arguments)
        if result != 0:
            raise RuntimeError(f"MaSound_{name} returned {result}")

    def render(self, data, path):
        self.format = None
        self.buffers.clear()
        format_id = self.call("Create", 1)
        if format_id < 1:
            raise RuntimeError(f"Could not create SMAF format ({format_id})")
        source = ct.create_string_buffer(data)
        sound_id = self.call("Load", format_id, ct.addressof(source), len(data), 0, 0, 0)
        if sound_id < 1:
            self.call("Delete", format_id)
            raise RuntimeError(f"Could not load SMAF sequence ({sound_id})")
        try:
            self.check("Open", format_id, sound_id, 0, 0)
            self.check("Standby", format_id, sound_id, 0)
            self.check("Start", format_id, sound_id, 1, 0)
            deadline = monotonic() + 40
            while self.call("Control", format_id, sound_id, 6, 0, 0) == 4:
                if monotonic() >= deadline:
                    raise RuntimeError("SMAF sequence exceeded the rendering time limit")
                sleep(0.01)
            # Let WinMM submit the last queued block after the sequencer stops.
            sleep(0.2)
        finally:
            self.call("Stop", format_id, sound_id, 0)
            self.call("Close", format_id, sound_id, 0)
            self.call("Unload", format_id, sound_id, 0)
            self.call("Delete", format_id)
        pcm = b"".join(self.buffers)
        if not self.format or not any(pcm):
            raise RuntimeError("Yamaha MA-3 produced no audio")
        tag, channels, rate, _, frame_size, bits = self.format
        if tag != 1 or bits != 16 or frame_size != channels * 2 or len(pcm) % frame_size:
            raise RuntimeError("Unexpected Yamaha PCM format")
        preroll = rate * PREROLL_MS // 1000 * frame_size
        if any(pcm[:preroll]):
            raise RuntimeError("Yamaha output started before the expected silent pre-roll ended")
        pcm = pcm[preroll:]
        # Some sampled effects pad the sequence with exact digital silence.
        end = (len(pcm.rstrip(b"\0")) + frame_size - 1) // frame_size * frame_size
        pcm = pcm[:end]
        with wave.open(str(path), "wb") as wav:
            wav.setparams((channels, bits // 8, rate, 0, "NONE", "not compressed"))
            wav.writeframes(pcm)
        return len(pcm) / (frame_size * rate)

    def close(self):
        self.call("End")
        self.restore_imports()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", type=Path, help="Path to the separately obtained ma3smwemu.dll")
    parser.add_argument("--assets", type=Path, default=ASSETS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.assets / "audio/firmware_wav"
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((args.assets / "manifest.json").read_text(encoding="utf-8"))
    renderer = Ma3Renderer(args.engine)
    try:
        for asset in manifest["audio"]:
            raw = (args.assets / asset["file"]).read_bytes()
            if sha256(raw).hexdigest() != asset["sha256"]:
                raise ValueError(f"Unexpected input bytes in {asset['file']}")
            path = output / f"{asset['address'][2:]}.wav"
            duration = renderer.render(raw, path)
            print(f"{path.name} {duration:.3f} s", flush=True)
    finally:
        renderer.close()


if __name__ == "__main__":
    main()
