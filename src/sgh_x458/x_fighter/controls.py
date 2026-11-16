"""Shared handset input, weapon queue and continuation for X-Fighter."""

from collections import deque

from sgh_x458.runtime.desktop import style_start_menu


REPEATABLE = {1, 4, 5, 6, 7}
MOVEMENT = {"up": 1, "down": 7, "left": 4, "right": 5}


def phone_code(key, game):
    if isinstance(key, int):
        return key
    if key == "back":
        return 23
    if game.ui_state == 0:
        return 1 if key == "ok" else None
    if game.ui_state in (3, 4):
        return 30 if key == "ok" else MOVEMENT.get(key)
    if game.state == 2:
        return {"up": 1, "down": 7, "ok": 9}.get(key)
    if game.state == 4:
        return (MOVEMENT | {"ok": 6, "missile": 6, "bomb": 9}).get(key)
    return 1 if key == "ok" else None


def saved_equipment(metadata):
    if "equipment" in metadata:
        return metadata["equipment"] or ()
    return metadata["profile"][5:8] if metadata.get("pending_equipment") else ()


class BattleInput:
    def __init__(self, slot, sound, equipment):
        self.slot = slot
        self.sound = sound
        self.equipment = equipment
        self.held = {}
        self.pending_actions = deque()
        self.fire_held = False

    def stop_firing(self, game):
        self.fire_held = game.primary_fire_requested = False

    def release_all(self, game):
        self.held.clear()
        self.pending_actions.clear()
        self.stop_firing(game)

    def release(self, key, *, fire=False):
        self.held.pop(key, None)
        if fire:
            self.fire_held = False

    def press(self, game, key, code, *, fire=False):
        in_battle = game.ui_state == 1 and game.state == 4 and bool(game.timers)
        if fire:
            if in_battle:
                self.fire_held = game.primary_fire_requested = True
            return False
        slot = self.slot
        if game.ui_state == 0 and code == 4:
            if slot is not None and slot.available:
                game.prepare_equipment(*saved_equipment(slot.resume(game, self.sound)))
            return False
        if code is None:
            return False
        starting = game.ui_state == 0 and code == 1
        closing = False
        if in_battle and code in (6, 9):
            if code not in self.pending_actions:
                self.pending_actions.append(code)
        elif game.key(code) == 1:
            closing = True
        if starting and game.ui_state == 1 and slot is not None:
            slot.start_new_game(game)
            game.prepare_equipment(*self.equipment)
        if code == 23:
            self.pending_actions.clear()
            self.stop_firing(game)
        if in_battle and code in REPEATABLE:
            self.held[key] = code
        return closing

    def advance(self, game, elapsed):
        if self.fire_held:
            game.primary_fire_requested = True
        game.advance(elapsed, next(reversed(self.held.values()), None), self.pending_actions)
        if game.ui_state != 1 or game.state != 4:
            self.pending_actions.clear()
            self.stop_firing(game)

    def style_menu(self, frame):
        return style_start_menu(frame, disable_continue=self.slot is None or not self.slot.available)
