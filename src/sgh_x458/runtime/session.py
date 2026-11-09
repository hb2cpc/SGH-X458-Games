"""Display, clock, save storage and device events for SGH-X458 games."""

import heapq
import json
from dataclasses import dataclass
from datetime import datetime
from struct import pack, unpack


WIDTH, HEIGHT = 128, 160
FRAME_BYTES = WIDTH * HEIGHT * 2
BOOT_DISPLAY = 0x20D1F7
GAME_CONTROLLER = 0x20D7AD
UI_STATE = 0x012995C4
SAVE_SIZE = 0x4C
TIMER_ARGUMENT = (0, 2, 3)
PICKUP_COPY = (0x6AD6BC, 0x6AD7DC, 0x0103F570)
INITIAL_DATA = ((0x6AD00C, 0x6AD118, 0x0103EEC0), PICKUP_COPY)


def timer_interval(milliseconds):
    """Firmware 0x228174: (13*ms + 59) // 60 system ticks, 60 units per tick."""
    return max(1, (13 * milliseconds + 59) // 60) * 60


@dataclass(frozen=True)
class AudioRequest:
    address: int
    caller: int


class Session:
    initial_data = INITIAL_DATA
    battle_key_address = None

    def __init__(self, language=1, on_audio=None, save=None):
        self.language = language
        self.on_audio = on_audio
        self.save = save if save is not None else bytearray(SAVE_SIZE)
        if len(self.save) != SAVE_SIZE:
            raise ValueError(f"The save record must contain {SAVE_SIZE} bytes")
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.audio_sizes = {int(item["address"], 16): item["size"] for item in manifest["audio"]}
        self.frame = bytes(FRAME_BYTES)
        self.frame_number = 0
        self.time_units = 0  # 13 units per millisecond, 60 units per phone timer tick.
        self.timers = {}
        self.pending = []
        self.timer_sequence = 0
        self.main_timer_repeat_floor = 0
        self.audio_events = []
        self.devices = {
            0x22808E: self.paint,
            0x2280D8: self.play_audio,
            0x228134: self.stop_audio,
            0x22813E: self.pause_audio,
            0x228148: self.resume_audio,
            0x228174: self.start_timer,
            0x2281F0: self.stop_timer,
            0x228224: self.load_save,
            0x2282C4: self.write_save,
        }

    def initialize_ram(self):
        for start, end, target in self.initial_data:
            self.write(target, self.read(start, end - start))

    def sync_clock(self):
        date = datetime.now()
        self.write(0x1195DEC, bytes((date.second, date.minute, date.hour, 0, date.day, date.month))
                   + pack("<H", date.year))

    def boot(self):
        self.sync_clock()
        self.call(BOOT_DISPLAY)
        self.open_menu()

    def open_menu(self):
        self.call(GAME_CONTROLLER, 0, 10 * self.language + self.game_index)

    def word(self, address):
        return unpack("<I", self.read(address, 4))[0]

    @property
    def state(self):
        return self.word(self.state_address)

    @property
    def ui_state(self):
        return self.word(UI_STATE + self.game_index * 4)

    def advance(self, milliseconds, held=None, pending_actions=None):
        end = self.time_units + milliseconds * 13
        while self.pending and self.pending[0][0] <= end:
            due, sequence, slot, interval, repeat = heapq.heappop(self.pending)
            if self.timers.get(slot) != sequence:
                continue
            self.time_units = due
            if not repeat:
                self.timers.pop(slot)
            if slot == 0:
                self.main_timer_repeat_floor = 0
            if (slot == 0 and self.battle_key_address is not None
                    and (pending_actions or held is not None) and self.ui_state == 1 and self.state == 4):
                # The firmware reads one key per battle update. A weapon press
                # takes precedence over movement or a repeated held key.
                if pending_actions:
                    self.key(pending_actions.popleft())
                elif held is not None and not self.word(self.battle_key_address):
                    self.key(held)
            self.call(GAME_CONTROLLER, 1, TIMER_ARGUMENT[slot])
            if repeat and self.timers.get(slot) == sequence:
                delay = max(interval, self.main_timer_repeat_floor) if slot == 0 else interval
                heapq.heappush(self.pending, (due + delay, sequence, slot, interval, repeat))
        self.time_units = end

    def key(self, code):
        return self.call(GAME_CONTROLLER, 2, code)

    def start_timer(self, slot, milliseconds, repeat, _):
        if slot not in range(len(TIMER_ARGUMENT)):
            raise RuntimeError(f"Unknown game timer slot {slot}")
        self.timer_sequence += 1
        self.timers[slot] = self.timer_sequence
        interval = timer_interval(milliseconds)
        heapq.heappush(self.pending, (self.time_units + interval, self.timer_sequence, slot, interval, repeat))
        return 0

    def stop_timer(self, slot, *_):
        self.timers.pop(slot, None)
        return 0

    def paint(self, address, *_):
        self.frame = self.read(address, FRAME_BYTES)
        self.frame_number += 1
        return 0

    def play_audio(self, address, length, _, caller):
        if self.audio_sizes.get(address) != length:
            raise RuntimeError(f"Unknown sound record at {address:#x} with size {length}")
        self.audio_events.append((self.time_units // 13, address))
        self.send_audio(AudioRequest(address, caller & ~1))
        return 1

    def send_audio(self, event):
        if self.on_audio:
            self.on_audio(event)

    def stop_audio(self, *_):
        self.send_audio(None)
        return 0

    def pause_audio(self, *_):
        self.send_audio("pause")
        return 0

    def resume_audio(self, *_):
        self.send_audio("resume")
        return 0

    def load_save(self, _handle, address, *_):
        self.write(address, bytes(self.save))
        return 0

    def write_save(self, _handle, address, *_):
        self.save[:] = self.read(address, len(self.save))
        return 0
