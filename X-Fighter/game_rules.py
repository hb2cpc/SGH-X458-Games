"""Named X-Fighter rules extracted from the firmware's game callbacks."""

from struct import pack, unpack

from handset.session import HEIGHT, PICKUP_COPY, WIDTH
from handset.word_ops import MASK, signed

from .layout import BATTLE_KEY, STATE


PLAYER = 0x12DAC20
PICKUPS = 0x12DABF8
PICKUP_STEPS = PICKUP_COPY[2]
PICKUP_STEP_COUNT = 36
RESERVES = STATE + 0x68


def restore_player_health(game):
    aircraft = game.word(STATE + 0x60)
    game.store(PLAYER + 4, game.word(0x5AD8B4 + aircraft * 24 + 4))


def move_player(game, vertical):
    position = PLAYER + (0x20 if vertical else 0x1C)
    extent = game.word(PLAYER + (0x0C if vertical else 0x08))
    delta = signed(game.r[0])
    if abs(delta) == 10:
        delta = -game.movement_step if delta < 0 else game.movement_step
    limit = (HEIGHT if vertical else WIDTH) - extent
    game.store(position, min(limit, max(0, signed(game.word(position)) + delta)))


def collect_power_up(game, kind):
    if kind == 2:
        aircraft = game.word(STATE + 0x60)
        default_shot = game.word(0x5AD8B4 + aircraft * 24 + 16)
        game.store(STATE + 0x80, 200)
        game.store(PLAYER + 0x10, default_shot + 1)
    elif kind == 3:
        game.store(STATE + 0x84, 100)
        game.store(STATE + 0x4C, 0)
    elif kind == 4:
        game.store(STATE + 0x6C, game.word(STATE + 0x6C) + 1)


def update_pickups(game):
    for slot in range(2):
        address = PICKUPS + slot * 20
        active, kind, x, y, phase = unpack("<5i", game.read(address, 20))
        if active != 1:
            continue
        y += signed(game.word(PICKUP_STEPS + phase * 4)) + 1
        x += signed(game.word(PICKUP_STEPS + (PICKUP_STEP_COUNT + phase) * 4))
        if y >= HEIGHT:
            game.write(address, bytes(20))
            continue
        game.write(address + 8, pack("<3i", x, y, (phase + 1) % PICKUP_STEP_COUNT))
        if game.word(STATE + 0x64) != 1:
            continue
        ship_x, ship_y = unpack("<2i", game.read(PLAYER + 0x1C, 8))
        aircraft = game.word(STATE + 0x60)
        hitbox = 0x5AD854 + 32 * aircraft
        width = 9 if kind == 4 else 11
        for offset in (0, 16):
            left, top, right, bottom = unpack("<4i", game.read(hitbox + offset, 16))
            if ship_x + right < x or ship_x + left > x + width:
                continue
            if ship_y + bottom < y or ship_y + top > y + 11:
                continue
            if not game.word(STATE + 0x14):
                game.play_audio(0x5A6FA8, 0xBE, 0, 0x2300D6)
            collect_power_up(game, kind)
            game.write(address, bytes(20))
            break


def activate_nuclear_attack(game):
    stock = signed(game.word(STATE + 0x6C))
    if stock <= 0 or game.word(STATE + 0x14):
        return
    game.store(STATE + 0x6C, stock - 1)
    game.store(STATE + 0x14, 1)
    game.store(STATE + 0x48, 0)
    half_width = game.word(PLAYER + 8) // 2
    game.store(STATE + 0x70, game.word(PLAYER + 0x1C) + half_width - 4)
    game.store(STATE + 0x74, game.word(PLAYER + 0x20) - 14)
    game.play_audio(0x5A800D, 0x47C, 0, 0x22FE8E)


def handle_combat_key(game):
    key = game.word(BATTLE_KEY)
    if key in (1, 4, 5, 7):
        game.r[0] = (-10 if key in (1, 4) else 10) & MASK
        move_player(game, key in (1, 7))
    elif key == 6:
        game.call_rule(0x2335F0)
    elif key == 9:
        activate_nuclear_attack(game)
    game.r[0] = 0
    game.store(BATTLE_KEY, 0)


def scroll_and_spawn(game):
    game.r[0] += game.word(STATE + 0x5C)
    game.store(STATE + 0x5C, game.r[0])
    game.call_rule(0x232B30)
    if signed(game.word(STATE + 0x5C)) <= 20:
        return
    game.store(STATE + 0x5C, 1)
    wave = signed(game.word(STATE + 0x38))
    if wave > 57:
        return
    wave += 1
    game.store(STATE + 0x38, wave)
    stage = game.word(STATE + 0x34)
    row = 0x5ABFC8 + stage * 57 * 9 * 4 + (50 - wave) * 9 * 4 - 0x800
    formation = game.r[0] = game.word(row + 7 * 4)
    if formation in (1, 3):
        game.call_rule(0x231478)
    if formation in (2, 3):
        game.call_rule(0x232BAC)


def finish_player_explosion(game):
    game.r[7] = STATE
    if game.word(STATE + 0x64):
        return
    reserves = signed(game.word(RESERVES))
    if game.state == 4:
        reserves -= 1
        game.store(RESERVES, reserves)
    game.store(STATE, 5 if reserves < 0 else 3)
    if reserves < 0:
        game.play_audio(0x5A7066, 0xDE0, 0, 0x235636)


def update_battle(game):
    if game.word(BATTLE_KEY):
        handle_combat_key(game)
    game.r[0] = 1
    scroll_and_spawn(game)
    if not (game.word(STATE + 0x1C) or game.word(STATE + 0x20)):
        game.call_rule(0x2305D8)  # Automatic fire.
    game.call_rule(0x2304E0)  # Bullets.
    game.call_rule(0x233514)  # Missiles.
    game.call_rule(0x2313A8)  # Enemy formations.
    if game.word(STATE + 0x18) == 1:
        if not game.word(STATE + 0x1C):
            game.call_rule(0x234370)
        if game.word(STATE + 0x18) == 1 and game.word(STATE + 0x1C) == 1:
            game.call_rule(0x2343A0)
    update_pickups(game)
    if game.invincible:
        restore_player_health(game)
    game.call_rule(0x23589C)  # Compose and submit the frame.
