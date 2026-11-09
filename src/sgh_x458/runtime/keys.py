"""Desktop mappings for the SGH-X458 keypad and score editor."""

import pygame


DIGITS = {key: digit for digit in range(10) for key in
          (getattr(pygame, f"K_{digit}"), getattr(pygame, f"K_KP{digit}"))}
WASD = {pygame.K_w: pygame.K_UP, pygame.K_a: pygame.K_LEFT,
        pygame.K_s: pygame.K_DOWN, pygame.K_d: pygame.K_RIGHT}
DIRECTIONS = {pygame.K_UP: 28, pygame.K_LEFT: 26, pygame.K_RIGHT: 27, pygame.K_DOWN: 29}
EDITOR_KEYS = {pygame.K_LEFT: 26, pygame.K_RIGHT: 27, pygame.K_BACKSPACE: 23,
               pygame.K_ESCAPE: 23, pygame.K_RETURN: 30, pygame.K_KP_ENTER: 30}


def score_entry_key(key, game, *, vertical=False):
    if key in DIGITS:
        game.type_score_character(str(DIGITS[key]))
    elif pygame.K_a <= key <= pygame.K_z:
        game.type_score_character(chr(ord("A") + key - pygame.K_a))
    elif key == pygame.K_SPACE:
        game.type_score_character(" ")
    elif (code := EDITOR_KEYS.get(key, DIRECTIONS.get(key) if vertical else None)) is not None:
        return game.key(code)
    return None
