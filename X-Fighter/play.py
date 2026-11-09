"""Desktop entry point for the X-Fighter source port."""

import argparse
import json
import sys
from collections import deque
from functools import partial
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "X-Fighter"

from handset.desktop import (
    DEFAULT_SPEED, SPEED_QUARTERS, WINDOW_SIZES,
    Sound, add_play_options, data_directory, draw_frame, open_game_display, style_start_menu, write_record,
)
from handset.keys import DIGITS, WASD, score_entry_key
from handset.resume import ResumeSlot
from handset.score_editor import SCORE_ENTRY
from handset.session import SAVE_SIZE
import pygame

from .audio_mix import load_game_clip
from .layout import ASSETS, DEFAULT_BOMBS, MAX_BOMBS, ROOT
from .practice import SCENES, start_scene
from .x_fighter import ENTER_BATTLE, Game


SAVE_PATH = data_directory(ROOT.parent) / "X-Fighter" / "scores.bin"
PRACTICE_SAVE = SAVE_PATH.with_name("practice-scores.bin")
LEGACY_SAVE = ROOT / ".local" / "scores.bin"
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


def load_scores(save_path):
    paths = (SAVE_PATH, LEGACY_SAVE) if save_path == SAVE_PATH else (save_path,)
    for path in paths:
        if path.is_file():
            return bytearray(path.read_bytes())
    return bytearray(SAVE_SIZE)


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
    scores = load_scores(save_path)
    saved = bytes(scores)
    startup_audio = []
    game = Game(language=args.language, on_audio=startup_audio.append, save=scores, handset_timing=True)

    try:
        start_scene(game, args.scene, args.stage, args.aircraft, args.progress)
        game.configure_practice(invincible=args.invincible, auto_fire=not args.manual_fire,
                                upgraded=args.upgraded, shield=args.shield, bombs=bombs)
        screen = open_game_display(WINDOW_SIZES[args.size])
        pygame.display.set_caption("X-Fighter  |  Anycall SGH-X458")
        sound = Sound(lambda request: AUDIO_PATH / clips[f"{request.address:06X}"]["file"],
                      not args.mute, sample_rate=48000,
                      load_clip=partial(load_game_clip, gain=args.volume / 100))
        game.on_audio = sound.play
        for event in startup_audio:
            sound.play(event)
        clock = pygame.time.Clock()
        clock.tick()
        held = {}
        pending_actions = deque()
        fire_held = False
        displayed = -1
        active = True
        speed_quarters = SPEED_QUARTERS[args.speed]
        remainder = 0
        while active:
            elapsed, remainder = divmod(clock.tick(60) * speed_quarters + remainder, 4)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    if slot is not None:
                        slot.suspend(game, sound, pending_equipment=ENTER_BATTLE in game.rules)
                    active = False
                    break
                elif event.type == pygame.WINDOWFOCUSLOST:
                    held.clear()
                    pending_actions.clear()
                    fire_held = game.primary_fire_requested = False
                elif event.type == pygame.WINDOWFOCUSGAINED:
                    pygame.key.stop_text_input()
                elif event.type == pygame.KEYUP:
                    held.pop(event.key, None)
                    if event.key == pygame.K_j:
                        fire_held = False
                elif event.type == pygame.KEYDOWN:
                    if game.ui_state == SCORE_ENTRY:
                        score_entry_key(event.key, game)
                        continue
                    in_battle = game.ui_state == 1 and game.state == 4 and bool(game.timers)
                    if event.key == pygame.K_j:
                        if in_battle:
                            fire_held = game.primary_fire_requested = True
                        continue
                    code = phone_key(event.key, game)
                    can_continue = slot is not None and slot.available
                    if game.ui_state == 0 and code == 4:
                        if can_continue and not slot.resume(game, sound):
                            game.rules.pop(ENTER_BATTLE, None)
                        continue
                    starting = game.ui_state == 0 and code == 1 and can_continue
                    if code is not None:
                        if in_battle and code in (6, 9):
                            if code not in pending_actions:
                                pending_actions.append(code)
                        elif game.key(code) == 1:
                            active = False
                        if starting and game.ui_state == 1:
                            slot.discard()
                        if code == 23:
                            pending_actions.clear()
                            fire_held = game.primary_fire_requested = False
                        if in_battle and code in REPEATABLE:
                            held[event.key] = code
            if not active:
                break
            if fire_held:
                game.primary_fire_requested = True
            game.advance(elapsed, next(reversed(held.values()), None), pending_actions)
            if game.ui_state != 1 or game.state != 4:
                pending_actions.clear()
                fire_held = game.primary_fire_requested = False
            if displayed != game.frame_number:
                pixels = game.frame
                if game.ui_state == 0:
                    pixels = style_start_menu(pixels, disable_continue=slot is None or not slot.available)
                draw_frame(screen, pixels)
                displayed = game.frame_number
            if scores != saved:
                write_record(save_path, scores)
                saved = bytes(scores)
            if slot is not None:
                slot.update(game)
        if scores != saved:
            write_record(save_path, scores)
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
    for name, limit in (("volume", 100), ("progress", 100), ("bombs", MAX_BOMBS)):
        value = getattr(args, name)
        if value is not None and not 0 <= value <= limit:
            parser.error(f"--{name} must be between 0 and {limit}")
    run(args)


if __name__ == "__main__":
    main()
