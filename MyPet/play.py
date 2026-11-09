"""Desktop entry point for the SGH-X458 MyPet port."""

import argparse
import sys
from pathlib import Path


if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "MyPet"

from handset.desktop import (
    WINDOW_SIZES, add_play_options, data_directory, firmware_sound, load_record, open_game_display, run_game_loop,
)
from handset.keys import DIGITS, DIRECTIONS, WASD
from handset.session import GAME_CONTROLLER, TIMER_ARGUMENT
import pygame

from .layout import ASSETS, ROOT
from .mypet import Game


SAVE_PATH = data_directory(ROOT.parent) / "MyPet" / "save.bin"


def phone_key(key, game):
    if key in DIGITS:
        return DIGITS[key]
    if key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
        return 23
    if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
        return 1 if game.ui_state == 0 else 30
    return DIRECTIONS.get(WASD.get(key, key))


def handle_key(key, game):
    code = phone_key(key, game)
    if code is not None:
        return game.key(code)
    return None


def run(args):
    save = load_record(SAVE_PATH, "MyPet save")
    saved = bytes(save)
    try:
        sound = firmware_sound(ASSETS, args)
        game = Game(on_audio=sound.play, save=save, language=args.language)
        game.boot()
        # The firmware starts with a blank logo frame. Draw its first animation frame before showing the window.
        game.call(GAME_CONTROLLER, 1, TIMER_ARGUMENT[0])
        screen = open_game_display(WINDOW_SIZES[args.size])
        pygame.display.set_caption("我的宠物  |  Anycall SGH-X458")
        run_game_loop(game, screen, args.speed, handle_key, SAVE_PATH, saved, on_close=game.save_on_close)
    finally:
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_play_options(parser)
    args = parser.parse_args()
    if not 0 <= args.volume <= 100:
        parser.error("--volume must be between 0 and 100")
    run(args)


if __name__ == "__main__":
    main()
