"""Render the README screenshots by driving each game headlessly.

Every image is a frame the game itself produced, scaled 2x with nearest-neighbour
filtering, exactly as the desktop window shows it. Run from the project root:

    python -m tools.screenshots [--output docs/images]
"""

import argparse
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from sgh_x458.mypet.game import Game as MyPet
from sgh_x458.runtime.desktop import rgb565_surface, style_start_menu
from sgh_x458.runtime.session import GAME_CONTROLLER, HEIGHT, TIMER_ARGUMENT, WIDTH
from sgh_x458.spacewar.game import Game as SpaceWar
from sgh_x458.x_fighter.game import Game as XFighter
from tools import PROJECT_ROOT


SCALE = 2
# SpaceWar keypad codes while playing.
UP, LEFT, RIGHT, DOWN = 2, 4, 6, 8


def save(game, path):
    frame = style_start_menu(game.frame) if game.ui_state == 0 else game.frame
    surface = rgb565_surface(frame, (WIDTH, HEIGHT))
    pygame.image.save(pygame.transform.scale(surface, (WIDTH * SCALE, HEIGHT * SCALE)), str(path))
    print(f"wrote {path}")


def x_fighter(output):
    from sgh_x458.x_fighter.practice import start_scene

    game = XFighter(handset_timing=True)
    game.boot()
    game.advance(1500)
    save(game, output / "x_fighter-1-menu.png")

    game = XFighter(handset_timing=True)
    start_scene(game, "battle", 2, 2, 35)
    game.invincible = True
    game.advance(3000)
    save(game, output / "x_fighter-2-battle.png")

    game = XFighter(handset_timing=True)
    start_scene(game, "battle", 1, 1, 100)
    game.invincible = True
    game.advance(10500)
    save(game, output / "x_fighter-3-boss.png")


def spacewar(output):
    game = SpaceWar()
    game.boot()
    game.advance(1200)
    save(game, output / "spacewar-1-menu.png")

    # Stage 1: cut a small corner off the map; it uncovers a slow-down item.
    game = SpaceWar()
    game.boot()
    game.key(1)
    game.advance(600)
    game.key(30)
    game.advance(1500)
    for code, milliseconds in ((DOWN, 1500), (RIGHT, 1500), (UP, 1500)):
        game.key(code)
        game.advance(milliseconds)
    save(game, output / "spacewar-2-play.png")

    # Stage 5: enclose a larger area to show more of the hidden picture.
    game = SpaceWar()
    game.configure_campaign(5, 3, "none", invincible=True)
    game.boot()
    game.key(1)
    game.key(30)
    game.advance(1700)
    for code, milliseconds in ((DOWN, 3000), (RIGHT, 3800), (UP, 3000), (LEFT, 600)):
        game.key(code)
        game.advance(milliseconds)
    game.key(5)  # Stop, and let the item banner fade.
    game.advance(2500)
    save(game, output / "spacewar-3-stage5.png")


def mypet(output):
    game = MyPet()
    game.boot()
    game.call(GAME_CONTROLLER, 1, TIMER_ARGUMENT[0])
    game.advance(1200)
    save(game, output / "mypet-1-menu.png")

    game = MyPet()
    game.boot()
    game.key(1)
    game.advance(1500)
    game.key(30)
    game.advance(2500)
    save(game, output / "mypet-2-room.png")
    # Select the third icon (medical care) and use it.
    game.key(27)
    game.advance(400)
    game.key(27)
    game.advance(400)
    game.key(30)
    game.advance(1500)
    save(game, output / "mypet-3-doctor.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "docs" / "images")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for render in (x_fighter, spacewar, mypet):
        render(args.output)


if __name__ == "__main__":
    main()
