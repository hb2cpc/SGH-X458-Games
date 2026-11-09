"""Desktop entry point for the X-Fighter source port."""

import argparse
import json
from collections import deque
from functools import partial

import pygame

from sgh_x458.runtime.desktop import (
    DEFAULT_SPEED, WINDOW_SIZES, KeyControls, Sound, add_play_options, data_directory, load_record,
    open_game_display, run_game_loop, style_start_menu,
)
from sgh_x458.runtime.keys import DIGITS, WASD, score_entry_key
from sgh_x458.runtime.resume import ResumeSlot
from sgh_x458.runtime.score_editor import SCORE_ENTRY

from .audio_mix import load_game_clip
from .game import ENTER_BATTLE, Game
from .layout import ASSETS, DEFAULT_BOMBS, MAX_BOMBS
from .practice import SCENES, start_scene


SAVE_PATH = data_directory() / "X-Fighter" / "scores.bin"
PRACTICE_SAVE = SAVE_PATH.with_name("practice-scores.bin")
AUDIO_PATH = ASSETS / "audio"
REPEATABLE = {1, 4, 5, 6, 7}


def phone_key(key, game):
    key = WASD.get(key, key)
    if key in DIGITS:
        return DIGITS[key]
    if key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
        return 23
    if game.ui_state == 0:
        return {pygame.K_RETURN: 1, pygame.K_SPACE: 1}.get(key)
    if game.ui_state in (3, 4):
        return {pygame.K_RETURN: 30, pygame.K_SPACE: 30,
                pygame.K_UP: 1, pygame.K_DOWN: 7, pygame.K_LEFT: 4, pygame.K_RIGHT: 5}.get(key)
    if game.state == 2:
        return {pygame.K_UP: 1, pygame.K_DOWN: 7, pygame.K_RETURN: 9, pygame.K_SPACE: 9}.get(key)
    if game.state == 4:
        return {pygame.K_UP: 1, pygame.K_LEFT: 4, pygame.K_RIGHT: 5, pygame.K_DOWN: 7,
                pygame.K_SPACE: 6, pygame.K_z: 6, pygame.K_x: 9, pygame.K_RETURN: 6}.get(key)
    return {pygame.K_RETURN: 1, pygame.K_SPACE: 1}.get(key)


class BattleControls(KeyControls):
    """X-Fighter input: held movement keys, queued weapons, manual fire and the resume slot.

    The firmware reads one key per battle update, so key presses during battle are
    collected here and handed to Game.advance() instead of being sent immediately.
    """

    def __init__(self, slot, sound):
        self.slot = slot
        self.sound = sound
        self.held = {}
        self.pending_actions = deque()
        self.fire_held = False

    def stop_firing(self, game):
        self.fire_held = game.primary_fire_requested = False

    def handle_event(self, event, game):
        if event.type == pygame.WINDOWFOCUSLOST:
            self.held.clear()
            self.pending_actions.clear()
            self.stop_firing(game)
        elif event.type == pygame.KEYUP:
            self.held.pop(event.key, None)
            if event.key == pygame.K_j:
                self.fire_held = False
        elif event.type == pygame.KEYDOWN:
            return self.key_down(event.key, game)
        return False

    def key_down(self, key, game):
        if game.ui_state == SCORE_ENTRY:
            score_entry_key(key, game)
            return False
        in_battle = game.ui_state == 1 and game.state == 4 and bool(game.timers)
        if key == pygame.K_j:
            if in_battle:
                self.fire_held = game.primary_fire_requested = True
            return False
        code = phone_key(key, game)
        slot = self.slot
        can_continue = slot is not None and slot.available
        if game.ui_state == 0 and code == 4:
            if can_continue and not slot.resume(game, self.sound):
                game.rules.pop(ENTER_BATTLE, None)
            return False
        if code is None:
            return False
        starting = game.ui_state == 0 and code == 1 and can_continue
        closing = False
        if in_battle and code in (6, 9):
            if code not in self.pending_actions:
                self.pending_actions.append(code)
        elif game.key(code) == 1:
            closing = True
        if starting and game.ui_state == 1:
            slot.discard()
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


def run(args):
    clips = json.loads((AUDIO_PATH / "playback.json").read_text(encoding="utf-8"))["clips"]
    # A normal menu start already grants three bombs and uses the standard leaderboard.
    bombs = args.bombs if args.scene != "menu" or args.bombs != DEFAULT_BOMBS else None
    practice = (args.scene != "menu" or args.invincible or args.manual_fire
                or args.upgraded or args.shield or bombs is not None or args.speed != DEFAULT_SPEED)
    save_path = PRACTICE_SAVE if practice else SAVE_PATH
    slot = None
    if args.scene == "menu":
        slot = ResumeSlot(save_path.with_name("practice-resume.bin" if practice else "resume.bin"),
                          (args.language, args.scene, args.speed, args.invincible,
                           args.manual_fire, args.upgraded, args.shield, bombs))
    scores = load_record(save_path, "X-Fighter score")
    saved = bytes(scores)
    startup_audio = []
    game = Game(language=args.language, on_audio=startup_audio.append, save=scores, handset_timing=True)

    try:
        start_scene(game, args.scene, args.stage, args.aircraft, args.progress)
        game.configure_practice(invincible=args.invincible, auto_fire=not args.manual_fire,
                                upgraded=args.upgraded, shield=args.shield, bombs=bombs)
        screen = open_game_display(WINDOW_SIZES[args.size])
        pygame.display.set_caption("X-战机")
        sound = Sound(lambda request: AUDIO_PATH / clips[f"{request.address:06X}"]["file"], not args.mute,
                      load_clip=partial(load_game_clip, gain=args.volume / 100))
        game.on_audio = sound.play
        for event in startup_audio:
            sound.play(event)

        def suspend():
            if slot is not None:
                slot.suspend(game, sound, pending_equipment=ENTER_BATTLE in game.rules)

        run_game_loop(game, screen, args.speed, BattleControls(slot, sound), save_path, saved,
                      on_close=suspend, resume_slot=slot)
    finally:
        game.close()
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_play_options(parser, language_help="0 English, 1 Simplified Chinese, 2 Traditional Chinese")
    parser.add_argument("--scene", choices=SCENES, default="menu")
    parser.add_argument("--stage", choices=(1, 2, 3), type=int, default=1)
    parser.add_argument("--aircraft", choices=(1, 2, 3), type=int, default=1)
    parser.add_argument("--progress", type=float, default=0)
    parser.add_argument("--invincible", action="store_true")
    parser.add_argument("--manual-fire", action="store_true")
    parser.add_argument("--upgraded", action="store_true")
    parser.add_argument("--shield", choices=("off", "full"))
    parser.add_argument("--bombs", type=int, default=DEFAULT_BOMBS)
    args = parser.parse_args()
    for name, limit in (("progress", 100), ("bombs", MAX_BOMBS)):
        if not 0 <= getattr(args, name) <= limit:
            parser.error(f"--{name} must be between 0 and {limit}")
    run(args)


if __name__ == "__main__":
    main()
