"""Enter a requested scene through the extracted game callbacks."""

from .game_rules import restore_player_health
from .layout import STATE


SCENES = ("menu", "select", "stage", "battle")
BOSS_WAVE = 49
BOSS_LEAD_IN_MS = 2000
UPDATES_PER_WAVE = 20
MAIN_TICK_MS = 254
TERRAIN_CACHE_VALID = STATE + 0x8C
BOSS_OPENING_REGIONS = (
    (0x12DA7C0, 0x12DBE24 - 0x12DA7C0),  # Battle objects, pickups, effects and player record.
    (STATE + 0x4C, 4),  # Shield hit effect.
    (STATE + 0x6C, 4),  # Bomb inventory.
    (STATE + 0x78, 4),  # Score.
    (STATE + 0x7C, 16),  # Fire cooldown and equipment timers.
)


def start_scene(game, scene, stage, aircraft, progress):
    game.boot()
    if scene == "menu":
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
        game.advance(seek_ms - MAIN_TICK_MS)
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
