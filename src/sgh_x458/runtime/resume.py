"""Desktop suspend slot for games whose firmware only saves high scores.

Each game keeps one slot, whatever the launcher options were. Options that act
while playing (invincibility, speed, manual fire) apply to a resumed game as set
in the current launch; starting options only shape new games. A game that was
ever played with launcher features stays a practice game, so its high score goes
to the practice leaderboard.
"""

import heapq
import json
import sys
import zlib

from .desktop import write_record
from .score_editor import LOAD_SCORES, SCORE_ENTRY
from .session import FRAME_BYTES, AudioRequest
from .translated_runtime import RAM_SIZE


VERSION = 1
MAX_SIZE = RAM_SIZE + FRAME_BYTES + 8192
ACTIVE_SCREENS = (1, SCORE_ENTRY)
LEGACY_PRACTICE_NAME = "practice-resume.bin"


class ResumeSlot:
    def __init__(self, directory, language, scores):
        self.path = directory / "resume.bin"
        # Earlier versions kept practice games in a second slot.
        self.legacy_path = directory / LEGACY_PRACTICE_NAME
        self.language = language
        self.scores = scores
        self.launch_practice = scores.practice
        self.snapshot = self.load()
        self.resumed = False

    @property
    def available(self):
        return self.snapshot is not None

    def load(self):
        found = []
        for path, practice in ((self.path, False), (self.legacy_path, True)):
            snapshot = self.read(path)
            if snapshot is not None:
                snapshot[0].setdefault("practice", practice)
                found.append((path.stat().st_mtime, snapshot))
        return max(found, key=lambda item: item[0])[1] if found else None

    def read(self, path):
        try:
            with path.open("rb") as source:
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
            print(f"Cannot read resume slot {path}: {error}", file=sys.stderr)
            return None
        profile = metadata.get("profile")
        # The profile starts with the menu language; launcher options no longer matter.
        if metadata.get("version") == VERSION and isinstance(profile, list) and profile[:1] == [self.language]:
            return metadata, memory
        return None

    def suspend(self, game, sound, **extra):
        if game.ui_state not in ACTIVE_SCREENS:
            return
        request = sound.active_request()
        metadata = {
            "version": VERSION,
            "profile": [self.language],
            "practice": self.scores.practice,
            "registers": game.r,
            "flags": [game.n, game.z, game.c, game.v],
            "time": game.time_units,
            "sequence": game.timer_sequence,
            "repeat_floor": game.main_timer_repeat_floor,
            "timers": [entry for entry in game.pending if game.timers.get(entry[2]) == entry[1]],
            "audio": [request.address, request.caller] if request else None,
            **extra,
        }
        data = json.dumps(metadata).encode("ascii") + b"\n" + game.ram + game.frame
        write_record(self.path, zlib.compress(data))
        self.legacy_path.unlink(missing_ok=True)

    def resume(self, game, sound):
        """Restore the saved game and return its metadata."""
        metadata, memory = self.snapshot
        game.ram[:] = memory[:RAM_SIZE]
        game.frame = memory[RAM_SIZE:]
        game.frame_number += 1
        if game.ui_state == SCORE_ENTRY:
            # The score was earned under the saved game's options and is already in the table.
            self.scores.use(game, metadata["practice"])
        else:
            self.scores.use(game, self.launch_practice or metadata["practice"])
            # The snapshot holds the leaderboard as it was then; read the file it now belongs to.
            game.call(LOAD_SCORES)
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
        return metadata

    def start_new_game(self, game):
        """A new game from the title menu replaces the saved one and uses this launch's options."""
        self.discard()
        if self.scores.use(game, self.launch_practice):
            game.call(LOAD_SCORES)

    def discard(self):
        if self.available or self.resumed:
            self.path.unlink(missing_ok=True)
            self.legacy_path.unlink(missing_ok=True)
            self.snapshot = None
            self.resumed = False

    def update(self, game):
        if self.resumed and game.ui_state not in ACTIVE_SCREENS:
            self.discard()
