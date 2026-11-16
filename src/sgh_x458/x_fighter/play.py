"""Desktop entry point for the X-Fighter source port."""

import argparse
import json
from functools import partial

import pygame

from sgh_x458.runtime.desktop import (
    DEFAULT_SPEED, WINDOW_SIZES, ScoreFile, Sound, add_play_options, data_directory,
    open_game_display, run_game_loop,
)
from sgh_x458.runtime.keys import DIGITS, WASD, score_entry_key
from sgh_x458.runtime.resume import ResumeSlot
from sgh_x458.runtime.score_editor import SCORE_ENTRY

from .audio_mix import load_game_clip
from .controls import BattleInput, phone_code
from .game import Game
from .layout import ASSETS, DEFAULT_BOMBS, MAX_BOMBS
from .practice import SCENES, start_scene


SAVE_PATH = data_directory() / "X-Fighter" / "scores.bin"
PRACTICE_SAVE = SAVE_PATH.with_name("practice-scores.bin")
AUDIO_PATH = ASSETS / "audio"
KEYS = {
    pygame.K_UP: "up", pygame.K_DOWN: "down", pygame.K_LEFT: "left", pygame.K_RIGHT: "right",
    pygame.K_RETURN: "ok", pygame.K_SPACE: "ok", pygame.K_ESCAPE: "back", pygame.K_BACKSPACE: "back",
    pygame.K_z: "missile", pygame.K_x: "bomb",
}


class BattleControls(BattleInput):
    def handle_event(self, event, game):
        if event.type == pygame.WINDOWFOCUSLOST:
            self.release_all(game)
        elif event.type == pygame.KEYUP:
            self.release(event.key, fire=event.key == pygame.K_j)
        elif event.type == pygame.KEYDOWN:
            key = event.key
            if game.ui_state == SCORE_ENTRY:
                score_entry_key(key, game)
            else:
                mapped = WASD.get(key, key)
                code = phone_code(DIGITS.get(mapped, KEYS.get(mapped)), game)
                return self.press(game, key, code, fire=key == pygame.K_j)
        return False


def run(args):
    clips = json.loads((AUDIO_PATH / "playback.json").read_text(encoding="utf-8"))["clips"]
    # A normal menu start already grants three bombs and uses the standard leaderboard.
    bombs = args.bombs if args.scene != "menu" or args.bombs != DEFAULT_BOMBS else None
    practice = (args.scene != "menu" or args.invincible or args.manual_fire
                or args.upgraded or args.shield or bombs is not None or args.speed != DEFAULT_SPEED)
    scores = ScoreFile(SAVE_PATH, "X-Fighter score", PRACTICE_SAVE, practice=practice)
    slot = ResumeSlot(SAVE_PATH.parent, args.language, scores) if args.scene == "menu" else None
    equipment = (args.upgraded, args.shield, bombs)
    startup_audio = []
    game = Game(language=args.language, on_audio=startup_audio.append, save=scores.record, handset_timing=True)

    try:
        start_scene(game, args.scene, args.stage, args.aircraft, args.progress, SAVE_PATH.parent)
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
                slot.suspend(game, sound, equipment=game.equipment)

        run_game_loop(game, screen, args.speed, BattleControls(slot, sound, equipment), scores,
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
