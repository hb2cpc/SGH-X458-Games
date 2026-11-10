"""The handset score editor shared by X-Fighter and SpaceWar."""

SCORE_ENTRY = 2
SCORE_NAME_CURSOR = 0x0103EFDC
SCORE_NAME_BUFFER = 0x0103EFE8
SCORE_NAME_LIMIT = 10
DRAW_SCOREBOARD = 0x22B5C6
# Reads the save record into the leaderboard at 0x12DA54C, filling defaults when it is blank.
LOAD_SCORES = 0x22B3C4


class ScoreEditor:
    def type_score_character(self, character):
        cursor = self.word(SCORE_NAME_CURSOR)
        if cursor < SCORE_NAME_LIMIT:
            self.write(self.word(SCORE_NAME_BUFFER) + cursor, character.encode("ascii"))
            self.store(SCORE_NAME_CURSOR, cursor + 1)
            self.call(DRAW_SCOREBOARD, 1)
