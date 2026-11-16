"""Enter a requested scene through the extracted game callbacks."""

import heapq
import json
import sys
import zlib
from pathlib import Path

from sgh_x458.runtime.desktop import write_record
from sgh_x458.runtime.session import FRAME_BYTES
from sgh_x458.runtime.translated_runtime import RAM_SIZE

from .game_rules import restore_player_health
from .layout import STATE


SCENES = ("menu", "select", "stage", "battle")
BOSS_WAVE = 49
BOSS_LEAD_IN_MS = 2000
UPDATES_PER_WAVE = 20
# Drawing is the costliest part of an update. The boss seek skips it, then draws this many updates so the
# warning banner and frame buffers end exactly as if every update had been drawn.
SETTLE_UPDATES = 80
MAIN_TICK_MS = 254
TERRAIN_CACHE_VALID = STATE + 0x8C
BOSS_OPENING_REGIONS = (
    (0x12DA7C0, 0x12DBE24 - 0x12DA7C0),  # Battle objects, pickups, effects and player record.
    (STATE + 0x4C, 4),  # Shield hit effect.
    (STATE + 0x6C, 4),  # Bomb inventory.
    (STATE + 0x78, 4),  # Score.
    (STATE + 0x7C, 16),  # Fire cooldown and equipment timers.
)


class SeekCache:
    """The game state after the last battle seek, so repeating the same start skips the simulation.

    The state depends only on the request and the game's code and data, apart from the clock.
    """

    VERSION = 1

    def __init__(self, directory, game, stage, aircraft, progress):
        self.path = directory / "seek.bin"
        self.key = [self.VERSION, game.language, stage, aircraft, progress, self.build()]

    @staticmethod
    def build():
        """Identify this build of the game, or return None when it cannot be told from another."""
        package = Path(__file__).parent
        files = [*package.glob("*.py*"), *package.parent.glob("runtime/*.py*"), *package.glob("assets/*.*")]
        if getattr(sys, "frozen", False):
            files.append(Path(sys.executable))
        details = [(path.name, path.stat()) for path in sorted(files)]
        return [[name, status.st_size, status.st_mtime_ns] for name, status in details] or None

    def restore(self, game):
        if self.key[-1] is None:
            return False
        try:
            header, _, memory = zlib.decompress(self.path.read_bytes()).partition(b"\n")
            state = json.loads(header)
        except (OSError, ValueError, zlib.error):
            return False
        if state.get("key") != self.key or len(memory) != RAM_SIZE + FRAME_BYTES:
            return False
        game.ram[:] = memory[:RAM_SIZE]
        game.frame = memory[RAM_SIZE:]
        game.frame_number = state["frames"]
        game.r[:] = state["registers"]
        game.n, game.z, game.c, game.v = state["flags"]
        game.time_units = state["time"]
        game.timer_sequence = state["sequence"]
        game.main_timer_repeat_floor = state["repeat_floor"]
        game.pending = [tuple(entry) for entry in state["timers"]]
        heapq.heapify(game.pending)
        game.timers = {int(slot): sequence for slot, sequence in state["slots"].items()}
        game.audio_events[:] = [tuple(event) for event in state["audio"]]
        game.sync_clock()
        return True

    def store(self, game):
        if self.key[-1] is None:
            return
        state = {
            "key": self.key,
            "frames": game.frame_number,
            "registers": game.r,
            "flags": [game.n, game.z, game.c, game.v],
            "time": game.time_units,
            "sequence": game.timer_sequence,
            "repeat_floor": game.main_timer_repeat_floor,
            "timers": game.pending,
            "slots": game.timers,
            "audio": game.audio_events,
        }
        data = json.dumps(state).encode("ascii") + b"\n" + game.ram + game.frame
        try:
            write_record(self.path, zlib.compress(data, 1))
        except OSError as error:
            print(f"Cannot save the battle seek to {self.path}: {error}", file=sys.stderr)


def start_scene(game, scene, stage, aircraft, progress, cache=None):
    """Enter the scene. `cache` is a directory that remembers the last battle seek."""
    game.boot()
    if scene == "menu":
        return
    seek = SeekCache(cache, game, stage, aircraft, progress) if cache and scene == "battle" else None
    if seek and seek.restore(game):
        return
    audio = game.on_audio
    game.on_audio = None
    try:
        game.key(1)
        game.advance(350)
        game.key(1)
        game.advance(350)
        if game.state != 2:
            raise RuntimeError("Could not open the aircraft selection")
        # The firmware increments the stage when it prepares the entry card.
        game.store(STATE + 0x34, stage - 1)
        if scene == "select":
            return
        for _ in range(aircraft - 1):
            game.key(7)
        if scene == "stage":
            game.on_audio = audio
        game.key(9)
        game.advance(MAIN_TICK_MS)
        if scene == "stage":
            return
        for _ in range(12):
            if game.state == 4:
                break
            game.advance(MAIN_TICK_MS)
        if game.state != 4 or game.word(STATE + 0x34) != stage:
            raise RuntimeError(f"Could not start stage {stage}")
        seek_battle(game, progress)
        if seek:
            seek.store(game)
    finally:
        game.on_audio = audio


def seek_battle(game, progress):
    # Simulate the actual map and enemies. Protect the player and leave targets at full HP.
    invincible, auto_fire = game.invincible, game.auto_fire
    game.invincible = True
    game.auto_fire = False
    try:
        updates = (BOSS_WAVE - 1) * UPDATES_PER_WAVE
        if progress < 100:
            for _ in range(int(updates * progress / 100)):
                game.advance(MAIN_TICK_MS)
            return
        # All three maps play the entrance music on the tick that starts wave 49.
        # The scroll counter starts at 0 and wraps to 1 after it passes 20.
        wave = game.word(STATE + 0x38)
        scroll = game.word(STATE + 0x5C)
        ticks = (BOSS_WAVE - wave) * UPDATES_PER_WAVE + 1 - scroll
        due, interval = next(
            (due, interval) for due, sequence, slot, interval, _ in game.pending
            if slot == 0 and sequence == game.timers[slot]
        )
        entrance = due + (ticks - 1) * interval
        seek_ms = (entrance - game.time_units) // 13 - BOSS_LEAD_IN_MS
        opening_state = [(address, game.read(address, size)) for address, size in BOSS_OPENING_REGIONS]
        settle_ms = min(SETTLE_UPDATES * MAIN_TICK_MS, seek_ms - MAIN_TICK_MS)
        game.drawing = False
        try:
            game.advance(seek_ms - MAIN_TICK_MS - settle_ms)
        finally:
            game.drawing = True
        game.advance(settle_ms)
        # Keep map progress and formation counters, but discard gameplay from the skipped waves.
        for address, data in opening_state:
            game.write(address, data)
        # The terrain cache includes ground enemies. Rebuild it for the first visible frame.
        game.store(TERRAIN_CACHE_VALID, 0)
        game.advance(MAIN_TICK_MS)
    finally:
        restore_player_health(game)
        game.invincible = invincible
        game.auto_fire = auto_fire
