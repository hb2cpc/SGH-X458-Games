"""Validate standalone source execution and optionally compare it with the offline ARM oracle."""

import argparse
import json
import wave
from collections import deque
from contextlib import closing
from hashlib import sha256
from struct import pack, unpack

from sgh_x458.runtime.session import AudioRequest
from sgh_x458.x_fighter import practice
from sgh_x458.x_fighter.game import HANDSET_LASER_DEATH_MS, Game
from sgh_x458.x_fighter.game_rules import PICKUP_STEP_COUNT, PICKUP_STEPS, PICKUPS, PLAYER
from sgh_x458.x_fighter.layout import ASSETS, STATE
from sgh_x458.x_fighter.practice import start_scene


def compare(actual, reference):
    if reference is None:
        return
    assert actual.ui_state == reference.ui_state
    assert actual.state == reference.state
    assert actual.frame_number == reference.frame_number
    assert actual.frame == reference.frame, f"RGB565 mismatch at frame {actual.frame_number}"
    assert actual.audio_events == reference.audio_events, f"Audio mismatch at frame {actual.frame_number}"


def begin(game, aircraft):
    game.boot()
    cold = game.frame
    game.key(4)
    assert game.ui_state == 0 and game.frame == cold
    game.key(3)
    assert game.ui_state == 4
    game.key(30)
    game.key(2)
    assert game.ui_state == 3
    game.key(30)
    game.key(1)
    game.advance(300)
    game.key(1)
    game.advance(300)
    assert game.state == 2
    for _ in range(aircraft - 1):
        game.key(7)
    game.key(9)
    game.advance(2800)
    assert game.state == 4


def audio_profile():
    audio = ASSETS / "audio"
    profile = json.loads((audio / "playback.json").read_text(encoding="utf-8"))["clips"]
    assert len(profile) == 15
    for address, entry in profile.items():
        clip = audio / entry["file"]
        assert entry["file"] == f"firmware_wav/{address}.wav"
        assert sha256(clip.read_bytes()).hexdigest() == entry["sha256"]
        with wave.open(str(clip)) as pcm:
            assert (pcm.getframerate(), pcm.getsampwidth(), pcm.getnchannels()) == (48000, 2, 2)
            assert any(pcm.readframes(pcm.getnframes()))
    return profile


def check_audio_requests(events, profile):
    for event in events:
        if isinstance(event, AudioRequest):
            route = profile[f"{event.address:06X}"]
            assert f"{event.caller:06X}" in route["return_addresses"], event


def normal_play(factory, profile):
    frames = 0
    for language in range(3):
        events = []
        reference = factory(language) if factory else None
        with closing(Game(language, events.append)) as game:
            pair = [game, reference] if reference else [game]
            for instance in pair:
                begin(instance, language + 1)
            compare(game, reference)
            for instance in pair:
                instance.key(23)
                pause = instance.frame
                instance.advance(1200)
                assert instance.frame == pause and not instance.timers
                instance.key(23)
            assert "pause" in events and "resume" in events
            for tick in range(2100):
                key = (4, None, 5, None, 6, None, 9)[tick % 7] if tick < 30 else None
                for instance in pair:
                    instance.advance(254, key)
                compare(game, reference)
                if game.ui_state != 1:
                    break
            assert (game.ui_state, game.state) == (2, 5)
            assert game.word(STATE + 0x78) > 0
            for instance in pair:
                for key in (2, 2, 3, 4, 10, 30):
                    instance.key(key)
                    instance.advance(1000)
            assert game.save[0] == 0x99 and game.ui_state == 0
            assert game.save[5:10] == b"BDG0\0"
            if reference:
                assert game.save == reference.save
                compare(game, reference)
            check_audio_requests(events, profile)
            frames += game.frame_number
    return frames


def editable_player_rules():
    with closing(Game()) as game:
        game.set_player_rules(5, 6)
        begin(game, 1)
        assert game.word(STATE + 0x68) == 5
        previous_x = game.word(0x12DAC3C)
        game.key(5)
        game.advance(254)
        assert game.word(0x12DAC3C) == previous_x + 6


def combat_input_priority():
    with closing(Game()) as game:
        begin(game, 1)
        x = game.word(PLAYER + 0x1C)
        stock = game.word(STATE + 0x6C)
        actions = deque((6, 9))
        game.key(4)
        game.advance(254, held=4, pending_actions=actions)
        assert actions == deque((9,))
        assert game.audio_events[-1][1] == 0x5A8489
        game.advance(254, held=4, pending_actions=actions)
        assert not actions and game.word(STATE + 0x6C) == stock - 1
        assert game.audio_events[-1][1] == 0x5A800D
        assert game.word(PLAYER + 0x1C) == x
        game.advance(254, held=4, pending_actions=actions)
        assert game.word(PLAYER + 0x1C) == x - 10


def laser_explosion_cadence():
    for handset_timing, spacing in ((False, 254), (True, HANDSET_LASER_DEATH_MS)):
        with closing(Game(handset_timing=handset_timing)) as game:
            begin(game, 2)
            game.store(STATE + 0x50, 30)  # Active beam length.
            game.store(PLAYER + 4, 1)
            game.call(0x23390D, 0, game.word(PLAYER + 0x1C), 100)

            def beam_update():
                game.r[:2] = 0, 0
                game.call_rule(0x233954)
                return 0x235BE2

            game.rules[0x235ABA] = beam_update
            game.advance(254 + spacing * 2)
            times = [t for t, address in game.audio_events if address == 0x5A7E46]
            assert len(times) == 3, times
            gaps = [b - a for a, b in zip(times, times[1:])]
            if handset_timing:
                assert gaps == [spacing, spacing], gaps
            else:
                assert all(gap in (253, 254) for gap in gaps), gaps


def practice_starts(all_stages):
    with closing(Game(handset_timing=True)) as game:
        start_scene(game, "select", 2, 1, 0)
        assert game.state == 2
        game.configure_practice(invincible=True, auto_fire=False, upgraded=True, shield="off", bombs=0)
        game.key(9)
        for _ in range(12):
            if game.state == 4:
                break
            game.advance(254)
        assert (game.state, game.word(STATE + 0x34)) == (4, 2)
        assert game.word(PLAYER + 0x10) == 1
        assert game.word(STATE + 0x84) == game.word(STATE + 0x6C) == 0
        game.call(0x2305D9)
        assert not game.word(0x12DB374 + 24)
        game.primary_fire_requested = True
        game.call(0x2305D9)
        assert game.word(0x12DB374 + 24) == 1
        game.store(PLAYER + 4, 1)
        game.call(0x2302C5)
        assert game.word(PLAYER + 4) == 100 and game.word(STATE + 0x64) == 1
    if all_stages:
        for stage, health in enumerate((900, 2000, 3000), start=1):
            events = []
            with closing(Game(handset_timing=True, on_audio=events.append)) as game:
                start_scene(game, "battle", stage, stage, 100)
                assert (game.state, game.word(STATE + 0x34)) == (4, stage)
                assert not game.word(STATE + 0x18)
                assert game.read(0x12DB1E4, 10 * 40) == bytes(10 * 40)
                assert game.word(STATE + 0x78) == 0
                assert game.word(PLAYER + 0x10) == game.word(0x5AD8B4 + (stage - 1) * 24 + 16)
                assert game.word(STATE + 0x80) == 0
                first_frame = game.frame
                game.store(practice.TERRAIN_CACHE_VALID, 0)
                game.call(0x23589D)
                assert game.frame == first_frame, "Boss opening frame still contains cached sprites"
                assert all(address != 0x5A542E for _, address in game.audio_events)
                game.advance(practice.BOSS_LEAD_IN_MS - 1)
                assert not game.word(STATE + 0x18)
                game.advance(2)
                assert game.word(STATE + 0x18) == game.word(STATE + 0x20) == 1
                assert game.word(0x12DBB34) == health
                assert game.word(STATE + 0x78) == 0
                assert sum(isinstance(event, AudioRequest) and event.address == 0x5A542E
                           for event in events) == 1


def pickup_trajectory(factory):
    reference = factory(1) if factory else None
    with closing(Game()) as game:
        pair = (game, reference) if reference else (game,)
        for instance in pair:
            instance.boot()
            instance.write(PICKUPS, pack("<5i", 1, 4, 35, 20, 0))
        steps = unpack("<72i", game.read(PICKUP_STEPS, 288))
        x, y = 35, 20
        for tick in range(PICKUP_STEP_COUNT * 2):
            phase = tick % PICKUP_STEP_COUNT
            y += steps[phase] + 1
            x += steps[phase + PICKUP_STEP_COUNT]
            expected = pack("<5i", 1, 4, x, y, (phase + 1) % PICKUP_STEP_COUNT)
            for instance in pair:
                instance.call(0x22FFFD)
                assert instance.read(PICKUPS, 20) == expected
        assert (x, y) == (35, 92)
        for instance in pair:
            instance.write(PICKUPS, pack("<5i", 1, 4, 25, 158, 1))
            instance.call(0x22FFFD)
            assert instance.read(PICKUPS, 20) == bytes(20)
            instance.write(PLAYER + 0x1C, pack("<2i", 50, 110))
            instance.write(STATE + 0x64, pack("<I", 1))
            instance.write(PICKUPS, pack("<5i", 1, 4, 50, 112, 0))
            stock = instance.word(STATE + 0x6C)
            instance.call(0x22FFFD)
            assert instance.read(PICKUPS, 20) == bytes(20)
            assert instance.word(STATE + 0x6C) == stock + 1
        compare(game, reference)


def play_all_stages(factory, profile):
    reference = factory(1) if factory else None
    if reference:
        from unicorn import UC_HOOK_CODE
        reference.hooks[0x2302C4] = reference.no_device_action
        reference.cpu.hook_add(UC_HOOK_CODE, reference.dispatch_hook, begin=0x2302C4, end=0x2302C4)
    events = []
    with closing(Game(on_audio=events.append)) as game:
        game.rules[0x2302C4] = game.no_device_action
        pair = [game, reference] if reference else [game]
        for instance in pair:
            begin(instance, 2)
        boss_health = {}
        for tick in range(8000):
            for instance in pair:
                instance.advance(254, 9 if tick % 11 == 0 else None)
            compare(game, reference)
            if game.word(STATE + 0x18) == 1:
                stage = game.word(STATE + 0x34)
                boss_health.setdefault(stage, game.word(0x12DBB34))
            if game.ui_state != 1:
                break
        assert boss_health == {1: 900, 2: 2000, 3: 3000}, boss_health
        assert game.word(0x12DBB34) == 0 and (game.ui_state, game.state) == (2, 5)
        check_audio_requests(events, profile)
        print(f"Three bosses and score flow passed in {game.frame_number} frames with the destruction probe")


def score_editor_cursor():
    # The desktop score editor maps the right/left arrows to phone keys 27/26.
    # A fresh name row reads the shared UI blank string at 0x22BB54.
    with closing(Game()) as game:
        begin(game, 1)
        for tick in range(2100):
            key = (4, None, 5, None, 6, None, 9)[tick % 7] if tick < 30 else None
            game.advance(254, key)
            if game.ui_state != 1:
                break
        assert (game.ui_state, game.state) == (2, 5)
        game.key(27)
        game.key(26)
        assert game.ui_state == 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare-rom", action="store_true")
    parser.add_argument("--all-stages", action="store_true")
    args = parser.parse_args()
    factory = None
    if args.compare_rom:
        from tools.firmware import load_rom

        from .oracle import Oracle as Reference
        rom = load_rom()

        def factory(language):
            return Reference(rom, language=language)

    profile = audio_profile()
    pickup_trajectory(factory)
    editable_player_rules()
    combat_input_priority()
    laser_explosion_cadence()
    practice_starts(args.all_stages)
    score_editor_cursor()
    frames = normal_play(factory, profile)
    print(f"Source execution passed in three languages ({frames} frames), pickup trajectory, audio routes and player rules checked")
    if args.all_stages:
        play_all_stages(factory, profile)


if __name__ == "__main__":
    main()
