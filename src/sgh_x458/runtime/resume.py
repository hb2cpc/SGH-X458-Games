"""Desktop suspend slots for games whose firmware only saves high scores."""

import heapq
import json
import sys
import zlib

from .desktop import write_record
from .score_editor import SCORE_ENTRY
from .session import FRAME_BYTES, AudioRequest
from .translated_runtime import RAM_SIZE


VERSION = 1
MAX_SIZE = RAM_SIZE + FRAME_BYTES + 8192
ACTIVE_SCREENS = (1, SCORE_ENTRY)


class ResumeSlot:
    def __init__(self, path, profile):
        self.path = path
        self.profile = list(profile)
        self.snapshot = self.load()
        self.resumed = False

    @property
    def available(self):
        return self.snapshot is not None

    def load(self):
        try:
            with self.path.open("rb") as source:
                encoded = source.read(MAX_SIZE + 1)
        except FileNotFoundError:
            return None
        try:
            inflater = zlib.decompressobj()
            data = inflater.decompress(encoded, MAX_SIZE + 1)
            if len(data) > MAX_SIZE or not inflater.eof or inflater.unused_data:
                raise ValueError("Invalid compressed snapshot")
            header, _, memory = data.partition(b"\n")
            metadata = json.loads(header)
            if len(memory) != RAM_SIZE + FRAME_BYTES or not isinstance(metadata, dict):
                raise ValueError("Invalid snapshot layout")
        except (ValueError, zlib.error) as error:
            print(f"Cannot read resume slot {self.path}: {error}", file=sys.stderr)
            return None
        if metadata.get("version") == VERSION and metadata.get("profile") == self.profile:
            return metadata, memory
        return None

    def suspend(self, game, sound, *, pending_equipment=False):
        if game.ui_state not in ACTIVE_SCREENS:
            return
        request = sound.active_request()
        metadata = {
            "version": VERSION,
            "profile": self.profile,
            "registers": game.r,
            "flags": [game.n, game.z, game.c, game.v],
            "time": game.time_units,
            "sequence": game.timer_sequence,
            "repeat_floor": game.main_timer_repeat_floor,
            "timers": [entry for entry in game.pending if game.timers.get(entry[2]) == entry[1]],
            "audio": [request.address, request.caller] if request else None,
            "pending_equipment": pending_equipment,
        }
        data = json.dumps(metadata).encode("ascii") + b"\n" + game.ram + game.frame
        write_record(self.path, zlib.compress(data))

    def resume(self, game, sound):
        metadata, memory = self.snapshot
        game.ram[:] = memory[:RAM_SIZE]
        game.frame = memory[RAM_SIZE:]
        game.frame_number += 1
        game.r[:] = metadata["registers"]
        game.n, game.z, game.c, game.v = metadata["flags"]
        game.time_units = metadata["time"]
        game.timer_sequence = metadata["sequence"]
        game.main_timer_repeat_floor = metadata["repeat_floor"]
        game.pending = [tuple(entry) for entry in metadata["timers"]]
        heapq.heapify(game.pending)
        game.timers = {slot: sequence for _, sequence, slot, _, _ in game.pending}

        sound.play(None)
        if game.ui_state == 1 and not game.timers:
            game.key(4)
        if metadata["audio"] is not None:
            sound.play(AudioRequest(*metadata["audio"]))
        self.snapshot = None
        self.resumed = True
        return metadata["pending_equipment"]

    def discard(self):
        if self.available or self.resumed:
            self.path.unlink(missing_ok=True)
            self.snapshot = None
            self.resumed = False

    def update(self, game):
        if self.resumed and game.ui_state not in ACTIVE_SCREENS:
            self.discard()
