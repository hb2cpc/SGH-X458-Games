"""Run a bundled Java game with the desktop window and keyboard adapters."""

import argparse
from pathlib import Path

from .desktop import (
    SPEED_QUARTERS, WINDOW_SIZES, add_play_options, data_directory, frame_time, open_game_display,
)

import pygame

from .keys import DIGITS, WASD
from .midp import Midlet


# The arrow keys and Enter are the handset's navigation pad and OK key (-1..-5 in the ROM's
# key table); Escape and Backspace are the C key. Digits, * and # send their own codes.
KEYS = {
    pygame.K_UP: -1, pygame.K_DOWN: -2, pygame.K_LEFT: -3, pygame.K_RIGHT: -4,
    pygame.K_RETURN: -5, pygame.K_KP_ENTER: -5, pygame.K_SPACE: -5,
    pygame.K_ESCAPE: -8, pygame.K_BACKSPACE: -8, pygame.K_HASH: ord("#"),
    pygame.K_ASTERISK: ord("*"), pygame.K_KP_MULTIPLY: ord("*"),
}


def phone_key(key, unicode=""):
    if unicode in ("#", "*"):
        return ord(unicode)
    if key in DIGITS:
        return ord("0") + DIGITS[key]
    return KEYS.get(WASD.get(key, key))


def main(package_file, title):
    parser = argparse.ArgumentParser(description=title)
    add_play_options(parser, language=False)
    args = parser.parse_args()
    package = Path(package_file).parent
    game = None
    try:
        screen = open_game_display(WINDOW_SIZES[args.size])
        pygame.display.set_caption(title)
        pygame.font.init()
        game = Midlet(package / "assets", data_directory() / package.name / "rms",
                      0 if args.mute else args.volume)
        game.boot()
        clock = pygame.time.Clock()
        remainder = 0
        displayed = -1
        speed = SPEED_QUARTERS[args.speed]
        while not game.closed:
            elapsed, remainder = frame_time(clock, speed, remainder)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type in (pygame.KEYDOWN, pygame.KEYUP):
                    code = phone_key(event.key, getattr(event, "unicode", ""))
                    if code is not None:
                        game.key(code, released=event.type == pygame.KEYUP)
            game.advance(elapsed)
            if displayed != game.frame_number:
                screen.blit(pygame.transform.scale(game.surface, screen.get_size()), (0, 0))
                pygame.display.flip()
                displayed = game.frame_number
    finally:
        try:
            if game is not None:
                game.shutdown()
        finally:
            pygame.quit()

