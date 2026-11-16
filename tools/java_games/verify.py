"""Exercise the three Java game ports through their original input handlers."""

from contextlib import contextmanager
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import wave

from sgh_x458.runtime.midp import Midlet
from tools import PROJECT_ROOT

import pygame


GAMES_ROOT = PROJECT_ROOT / "src/sgh_x458"
EPOCH = 1_200_000_000_000
BACK = -8


@contextmanager
def play(game, saves):
    app = Midlet(GAMES_ROOT / game / "assets", saves / game, epoch=EPOCH)
    try:
        app.boot()
        assert wait_for(app, lambda: app.frame_number > 0), game
        yield app
        assert not app.diagnostics, app.diagnostics
    finally:
        app.shutdown()


def wait_for(app, ready, limit=20_000):
    """Run the handset until ``ready()`` holds; the phone's CPU time paces each step."""
    for _ in range(0, limit, 16):
        if ready():
            return True
        app.advance(16)
    return ready()


def advance(app, milliseconds):
    while milliseconds:
        frame = min(16, milliseconds)
        app.advance(frame)
        milliseconds -= frame


def press(app, key, delay=336):
    app.key(ord(key) if isinstance(key, str) else key)
    advance(app, delay)


def field(app, receiver, name, desc):
    key = app.vm.field(receiver.name, name, desc, False)
    return receiver.fields.get(key, app.vm.fields[key])


def bubble_score(app):
    score = field(app, app.current, "m_sp", "LScorePool;")
    return field(app, score, "m_tot_score", "I")


def bubble_controller(app):
    stack = app.vm.statics.get(("BubbleController", "m_controller_stack", "Ljava/util/Stack;"))
    return stack.data[-1].name if stack is not None and stack.data else None


def bubble_board(app):
    pool = field(app, field(app, app.current, "m_pool", "LBubblePool;"), "m_pool", "[[LBubble;")
    return [[field(app, bubble, "m_num", "B") for bubble in row] for row in pool]


def bubble_idle(app):
    return app.current.name == "BubbleGame" and bubble_controller(app) == "BubbleControllerNormal"


def verify_bubble_smile(saves):
    with play("bubble_smile", saves) as app:
        assert app.current.name == "BubbleLogo"
        advance(app, 1440)
        for key in "555":
            press(app, key)
        # The opening fill and any chained clears run at the handset's paint speed.
        assert wait_for(app, lambda: bubble_idle(app))
        for key in "242631":
            press(app, key, 0)
            assert wait_for(app, lambda: bubble_idle(app))
        score, board = bubble_score(app), bubble_board(app)
        # Closing the desktop game goes through the original save-and-return action.
    with play("bubble_smile", saves) as app:
        advance(app, 1440)
        press(app, "8")
        press(app, "5", 0)
        assert wait_for(app, lambda: bubble_idle(app))
        advance(app, 1000)  # The game thread loads the saved board after the canvas appears.
        assert bubble_score(app) == score and bubble_board(app) == board


def verify_fun2link(saves):
    with play("fun2link", saves) as app:
        canvas = app.current
        press(app, "5", 200)  # Mission briefing.
        press(app, "5", 9600)
        assert field(app, canvas, "stage", "B") == 1
        board = field(app, canvas, "board", "LBoard;")
        cursor = field(app, canvas, "cursor", "LCursor;")
        before = field(app, cursor, "currentX", "B")
        press(app, "6", 50)
        assert field(app, cursor, "currentX", "B") == before + 1
        press(app, "5", 250)
        assert field(app, canvas, "totalScore", "I") == 1
        press(app, BACK)
        assert field(app, canvas, "mode", "B") == 1
        press(app, "8")
        press(app, "5")
        assert field(app, canvas, "mode", "B") == 2
        assert field(app, canvas, "totalScore", "I") == 1
        press(app, "*", 8500)
        assert field(app, canvas, "mode", "B") == 5  # Unfinished pipeline.
        assert all(app.resource(f"data/stage.{stage}") for stage in range(21))
    with play("fun2link", saves) as app:
        press(app, "5", 200)
        press(app, "5", 9600)
        canvas = app.current
        board = field(app, canvas, "board", "LBoard;")
        layout = field(app, board, "map", "[[B")
        # Place a known solution to cover the original link, flow and clear routines.
        for x, y, pipe in ((3, 3, 4), (3, 2, 2), (2, 2, 3), (2, 1, 1), (3, 1, 5),
                           (4, 1, 2), (4, 2, 6), (4, 3, 6), (4, 4, 6), (4, 5, 3)):
            layout[y][x] = pipe
        check = field(app, canvas, "linkCheck", "LLinkCheck;")
        app.clock.spawn(app.vm.event(check, "startLinkCheck", "()V"))
        assert wait_for(app, lambda: field(app, check, "linkCount", "I") == 10, 2000)
        press(app, "*", 11000)
        assert field(app, canvas, "mode", "B") == 3
        press(app, "5", 1100)
        assert field(app, canvas, "stage", "B") == 2


def verify_ultimate_golf(saves):
    with play("ultimate_golf", saves) as app:
        advance(app, 3500)
        for key in "55555":
            press(app, key, 500)
        state = app.vm.statics["golfCanvas", "gv", "[I"]
        assert wait_for(app, lambda: (state[0], state[27]) == (5, 2))  # Active hole, swing view.
        press(app, "5", 0)
        assert wait_for(app, lambda: abs(state[20]) >= 49, 5000)
        press(app, "5", 0)  # Lock power once the event thread delivers the key.
        assert wait_for(app, lambda: abs(state[21]) >= 40, 2000), state[20:22]
        press(app, "5", 0)  # Strike, then wait for the ball to settle.
        assert wait_for(app, lambda: state[46] > 0)
        # The original saves the shot once the ball has settled.
        assert wait_for(app, lambda: any(app.record_stores.get("golfData", ())))
        landing = state[43:45]
        assert all(len(app.resource(f"golf/res/map/{hole}.zio")) == 2010 for hole in range(1, 19))
    with play("ultimate_golf", saves) as app:
        advance(app, 3500)
        for key in "585":
            press(app, key, 500)
        state = app.vm.statics["golfCanvas", "gv", "[I"]
        assert wait_for(app, lambda: state[0] == 5 and state[43:45] == landing)


def verify_audio(game):
    assets = GAMES_ROOT / game / "assets"
    manifest = json.loads((assets / "manifest.json").read_bytes())
    for clip in manifest["audio"]:
        path = assets / "audio/firmware_wav" / (clip["address"][2:] + ".wav")
        with wave.open(str(path), "rb") as wav:
            assert wav.getnframes() > 0 and wav.getsampwidth() == 2, path


def main():
    pygame.font.init()
    try:
        with TemporaryDirectory(prefix="sgh-x458-java-") as tmp:
            for game, verify in (
                ("bubble_smile", verify_bubble_smile),
                ("fun2link", verify_fun2link),
                ("ultimate_golf", verify_ultimate_golf),
            ):
                verify(Path(tmp))
                verify_audio(game)
                print(f"{game}: gameplay, original audio assets and save flow verified")
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()

