"""Desktop entry point for the SGH-X458 SpaceWar port."""

import argparse
from functools import partial

import pygame

from sgh_x458.runtime.desktop import (
    DEFAULT_SPEED, WINDOW_SIZES, KeyControls, add_play_options, data_directory, firmware_sound,
    load_record, open_game_display, run_game_loop,
)
from sgh_x458.runtime.keys import DIGITS, DIRECTIONS, WASD, score_entry_key as handset_score_entry_key
from sgh_x458.runtime.resume import ResumeSlot
from sgh_x458.runtime.score_editor import SCORE_ENTRY

from .game import Game
from .layout import ASSETS, DEFAULT_LIVES, ITEMS, MAX_LIVES, SCENES, STAGES


SAVE_PATH = data_directory() / "SpaceWar" / "scores.bin"
PRACTICE_SAVE = SAVE_PATH.with_name("practice-scores.bin")
FIRST_UPDATE_MS = 204
ARROWS = {pygame.K_UP: 2, pygame.K_LEFT: 4, pygame.K_RIGHT: 6, pygame.K_DOWN: 8}


def phone_key(key, game):
    if key in DIGITS:
        return DIGITS[key]
    if key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
        return 23
    if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
        if game.ui_state == 0:
            return 1
        if game.ui_state == 1 and not game.timers:
            return 4
        return 30
    key = WASD.get(key, key)
    if game.ui_state == 1:
        return ARROWS.get(key)
    if game.ui_state == 2:
        return DIRECTIONS.get(key)
    return None


def score_entry_key(key, game):
    return handset_score_entry_key(key, game, vertical=True)


def handle_key(key, game):
    if game.ui_state == SCORE_ENTRY:
        return score_entry_key(key, game)
    code = phone_key(key, game)
    if code is not None:
        return game.key(code)
    return None


def run(args):
    customized = (args.scene != "menu" or args.stage != 1 or args.lives != DEFAULT_LIVES
                  or args.start_item != "none" or args.speed != DEFAULT_SPEED or args.invincible)
    save_path = PRACTICE_SAVE if customized else SAVE_PATH
    slot = None
    if args.scene == "menu":
        slot = ResumeSlot(save_path.with_name("practice-resume.bin" if customized else "resume.bin"),
                          (args.language, args.scene, args.stage, args.lives, args.start_item,
                           args.speed, args.invincible))
    scores = load_record(save_path, "SpaceWar score")
    saved = bytes(scores)
    try:
        screen = open_game_display(WINDOW_SIZES[args.size])
        pygame.display.set_caption("空间大战")
        sound = firmware_sound(ASSETS, args)
        jump_to_stage = args.scene == "stage"
        game = Game(on_audio=None if jump_to_stage else sound.play,
                    save=scores, language=args.language)
        game.configure_campaign(args.stage, args.lives, args.start_item, invincible=args.invincible)
        game.boot()

        if jump_to_stage:
            game.key(1)
            game.key(30)
            game.advance(FIRST_UPDATE_MS)
            game.on_audio = sound.play

        def desktop_key(key, game):
            if game.ui_state == 0 and slot is not None and slot.available:
                code = phone_key(key, game)
                if code == 4:
                    slot.resume(game, sound)
                    return None
                if code == 1:
                    result = handle_key(key, game)
                    if game.ui_state == 1:
                        slot.discard()
                    return result
            return handle_key(key, game)

        on_close = partial(slot.suspend, game, sound) if slot is not None else None
        run_game_loop(game, screen, args.speed, KeyControls(desktop_key), save_path, saved,
                      on_close=on_close, resume_slot=slot)
    finally:
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_play_options(parser)
    parser.add_argument("--scene", choices=SCENES, default="menu")
    parser.add_argument("--stage", type=int, choices=STAGES, default=1)
    parser.add_argument("--lives", type=int, default=DEFAULT_LIVES, metavar=f"0-{MAX_LIVES}")
    parser.add_argument("--start-item", choices=ITEMS, default="none")
    parser.add_argument("--invincible", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.lives <= MAX_LIVES:
        parser.error(f"--lives must be between 0 and {MAX_LIVES}")
    run(args)


if __name__ == "__main__":
    main()
