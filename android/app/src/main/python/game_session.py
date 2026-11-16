"""Lifecycle, handset input and frame delivery for the Android launcher."""

import json
from pathlib import Path

from sgh_x458.runtime.desktop import DEFAULT_SPEED, MAX_FRAME_MS, SPEED_QUARTERS, ScoreFile, style_start_menu
from sgh_x458.runtime.resume import ACTIVE_SCREENS, ResumeSlot
from sgh_x458.runtime.score_editor import SCORE_ENTRY
from sgh_x458.runtime.session import GAME_CONTROLLER, TIMER_ARGUMENT


NAV = {"up": 28, "down": 29, "left": 26, "right": 27, "ok": 30, "back": 23}
MOVEMENT = {"up": 2, "down": 8, "left": 4, "right": 6}
MIDP_KEYS = {"up": -1, "down": -2, "left": -3, "right": -4, "ok": -5, "back": -8}
JAVA_GAMES = ("bubble_smile", "fun2link", "ultimate_golf")
PACKAGES = Path(__file__).parent / "sgh_x458"


class Sound:
    def __init__(self, player):
        self.player = player
        self.request = None

    def play(self, request, *, loops=0):
        if request == "pause":
            self.player.pauseGame()
        elif request == "resume":
            self.player.resumeGame()
        elif request is None:
            self.player.stop()
            self.request = None
        else:
            name = request if isinstance(request, str) else f"{request.address:06X}"
            self.player.play(name, loops)
            self.request = request

    def active_request(self):
        return self.request if self.player.active() else None


class GameSession:
    def __init__(self, game_id, saves, player, config):
        self.game_id = game_id
        self.saves = Path(saves)
        self.sound = Sound(player)
        self.options = json.loads(config)
        self.speed = self.options.get("speed", DEFAULT_SPEED)
        self.remainder = 0
        self.displayed = -1
        self.closed = False
        self.slot = None
        self.checkpointed = False
        self.scores = None
        self.controls = None
        self.on_close = None
        self.java = game_id in JAVA_GAMES
        if self.java:
            import raster
            from sgh_x458.runtime.midp import Midlet

            self.game = Midlet(PACKAGES / game_id / "assets", self.saves / game_id / "rms",
                               drawing=raster, sound=self.sound)
            self.game.boot()
            self.on_close = self.game.shutdown
        elif game_id == "x_fighter":
            self.start_fighter()
        elif game_id == "spacewar":
            self.start_spacewar()
        elif game_id == "mypet":
            from sgh_x458.mypet.game import Game

            self.scores = ScoreFile(self.saves / "MyPet" / "save.bin", "MyPet save")
            self.game = Game(on_audio=self.sound.play, save=self.scores.record)
            self.game.boot()
            self.game.call(GAME_CONTROLLER, 1, TIMER_ARGUMENT[0])
            self.on_close = self.game.save_on_close
        else:
            raise ValueError(f"Unknown game {game_id}")

    def score_slot(self, directory, practice, scene):
        path = self.saves / directory
        self.scores = ScoreFile(path / "scores.bin", directory, path / "practice-scores.bin", practice=practice)
        if scene == "menu":
            self.slot = ResumeSlot(path, 1, self.scores)

    def start_fighter(self):
        from fighter_input import FighterInput
        from sgh_x458.x_fighter.game import Game
        from sgh_x458.x_fighter.layout import DEFAULT_BOMBS
        from sgh_x458.x_fighter.practice import start_scene

        options = self.options
        scene = options.get("scene", "menu")
        stage = options.get("stage", 1)
        bombs = options.get("bombs", DEFAULT_BOMBS)
        if scene == "menu" and bombs == DEFAULT_BOMBS:
            bombs = None
        upgraded = options.get("upgraded", False)
        shield = options.get("shield") or ("off" if scene != "menu" else None)
        invincible = options.get("invincible", False)
        equipment = upgraded, shield, bombs
        practice = scene != "menu" or any((upgraded, shield, invincible, bombs is not None, self.speed != DEFAULT_SPEED))
        self.score_slot("X-Fighter", practice, scene)
        self.game = Game(on_audio=self.sound.play, save=self.scores.record, handset_timing=True)
        progress = 100 if scene == "boss" else options.get("progress", 0)
        start_scene(self.game, "battle" if scene == "boss" else scene, stage, options.get("aircraft", 1), progress,
                    self.saves / "X-Fighter")
        self.game.configure_practice(invincible=invincible, auto_fire=True, upgraded=upgraded, shield=shield, bombs=bombs)
        self.controls = FighterInput(self.slot, self.sound, equipment)
        self.on_close = self.game.close

    def start_spacewar(self):
        from sgh_x458.spacewar.game import Game
        from sgh_x458.spacewar.layout import DEFAULT_LIVES

        options = self.options
        scene = options.get("scene", "menu")
        stage = options.get("stage", 1)
        lives = options.get("lives", DEFAULT_LIVES)
        item = options.get("item", "none")
        invincible = options.get("invincible", False)
        practice = (scene != "menu" or stage != 1 or lives != DEFAULT_LIVES
                    or item != "none" or invincible or self.speed != DEFAULT_SPEED)
        self.score_slot("SpaceWar", practice, scene)
        self.game = Game(on_audio=self.sound.play if scene == "menu" else None, save=self.scores.record)
        self.game.configure_campaign(stage, lives, item, invincible=invincible)
        self.game.boot()
        if scene == "stage":
            self.game.key(1)
            self.game.key(30)
            self.game.advance(204)
            self.game.on_audio = self.sound.play

    def key(self, key, pressed):
        if self.closed:
            return
        game = self.game
        digit = int(key) if len(key) == 1 and key in "0123456789" else None
        if self.java:
            code = ord(key) if digit is not None or key in ("*", "#") else MIDP_KEYS.get(key)
            if code is not None:
                game.key(code, released=not pressed)
            return
        if not pressed:
            if self.controls is not None:
                self.controls.release(key, fire=key == "fire")
            return
        if self.score_entry():
            if digit is not None:
                game.type_score_character(key)
            elif key in ("left", "right", "ok", "back") or (self.controls is None and key in NAV):
                game.key(NAV[key])
        elif self.controls is not None:
            from sgh_x458.x_fighter.controls import phone_code

            self.closed = self.controls.press(game, key, phone_code(key if digit is None else digit, game),
                                              fire=key == "fire")
        else:
            self.native_key(key, digit)
        self.sync()

    def native_key(self, key, digit):
        game = self.game
        code = NAV.get(key) if digit is None else digit
        at_menu = game.ui_state == 0
        if key == "ok":
            code = 1 if at_menu else 30
            if self.game_id == "spacewar" and game.ui_state == 1 and not game.timers:
                code = 4
        elif self.game_id == "spacewar":
            if game.ui_state == 1 and key in MOVEMENT:
                code = MOVEMENT[key]
            elif at_menu and key in MOVEMENT:
                code = None
        if at_menu and code == 4 and self.slot is not None:
            if self.slot.available:
                self.slot.resume(game, self.sound)
        elif code is not None:
            self.closed = game.key(code) == 1
            if at_menu and code == 1 and self.slot is not None and game.ui_state == 1:
                self.slot.start_new_game(game)

    def score_entry(self):
        return self.game_id in ("x_fighter", "spacewar") and self.game.ui_state == SCORE_ENTRY

    def type_score(self, text):
        if self.score_entry():
            for character in text.upper():
                if character in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ":
                    self.game.type_score_character(character)

    def in_battle(self):
        return self.game_id == "x_fighter" and self.game.ui_state == 1 and self.game.state == 4

    def is_closed(self):
        return self.closed or (self.java and self.game.closed)

    def tick(self, elapsed):
        if self.is_closed():
            return None
        elapsed, self.remainder = divmod(min(elapsed, MAX_FRAME_MS) * SPEED_QUARTERS[self.speed]
                                         + self.remainder, 4)
        game = self.game
        if self.controls is not None:
            self.controls.advance(game, elapsed)
        else:
            game.advance(elapsed)
        self.sync()
        return self.take_frame()

    def take_frame(self):
        game = self.game
        if game.frame_number == self.displayed:
            return None
        self.displayed = game.frame_number
        if self.java:
            return game.surface.frame()
        if game.ui_state != 0:
            return game.frame
        if self.controls is not None:
            return self.controls.style_menu(game.frame)
        available = self.slot is not None and self.slot.available
        return style_start_menu(game.frame, disable_continue=self.slot is not None and not available,
                                enable_continue=available)

    def sync(self):
        if self.scores is not None:
            self.scores.sync(self.game)
        if self.slot is not None:
            if self.checkpointed and self.game.ui_state not in ACTIVE_SCREENS:
                self.slot.path.unlink(missing_ok=True)
                self.checkpointed = False
            self.slot.update(self.game)

    def suspend(self):
        if self.controls is not None:
            self.controls.release_all(self.game)
        if self.slot is not None and self.game.ui_state in ACTIVE_SCREENS:
            extra = {"equipment": self.game.equipment} if self.controls is not None else {}
            self.slot.suspend(self.game, self.sound, **extra)
            self.checkpointed = True
        if self.game_id == "mypet":
            self.game.checkpoint()
        self.sync()

    def close(self):
        self.suspend()
        if self.on_close is not None:
            self.on_close()
        self.sync()
        self.sound.play(None)
