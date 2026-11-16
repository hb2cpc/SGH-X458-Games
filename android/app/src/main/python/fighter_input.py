"""Responsive combat controls for the Android version of X-Fighter."""

from sgh_x458.x_fighter.controls import BattleInput, REPEATABLE
from sgh_x458.x_fighter.practice import MAIN_TICK_MS


COMBAT_KEYS = REPEATABLE | {9}


class FighterInput(BattleInput):
    def __init__(self, slot, sound, equipment):
        super().__init__(slot, sound, equipment)
        self.repeat_due = {}

    @staticmethod
    def can_control(game):
        return game.ui_state == 1 and game.state == 4 and 0 in game.timers

    def press(self, game, key, code, *, fire=False):
        if not self.can_control(game) or code not in COMBAT_KEYS:
            return super().press(game, key, code, fire=fire)
        if code in REPEATABLE:
            self.held[key] = code
            self.repeat_due[key] = game.time_units + MAIN_TICK_MS * 13
        game.apply_battle_key(code)
        return False

    def release(self, key, *, fire=False):
        super().release(key, fire=fire)
        self.repeat_due.pop(key, None)

    def release_all(self, game):
        super().release_all(game)
        self.repeat_due.clear()

    def advance(self, game, elapsed):
        game.advance(elapsed)
        if not self.can_control(game):
            self.release_all(game)
        elif self.held:
            key = next(reversed(self.held))
            if game.time_units >= self.repeat_due[key]:
                self.repeat_due[key] = game.time_units + MAIN_TICK_MS * 13
                game.apply_battle_key(self.held[key])
