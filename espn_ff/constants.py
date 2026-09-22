"""Magic numbers the ESPN v3 API uses, decoded.

Gathered the hard way; kept here so no script has to rediscover them.
"""

# team['roster']['entries'][i]['lineupSlotId']
SLOT_CODES = {
    0: "QB",
    1: "QB",
    2: "RB",
    3: "RB",
    4: "WR",
    5: "WR",
    6: "TE",
    7: "TE",
    16: "D/ST",
    17: "K",
    20: "Bench",
    21: "IR",
    23: "Flex",
}

# player['defaultPositionId'] -- the player's real position, independent of
# whatever slot their manager happened to play them in that week.
POSITION_CODES = {
    1: "QB",
    2: "RB",
    3: "WR",
    4: "TE",
    5: "K",
    16: "D/ST",
}

# Slots that count toward the score in a given week.
STARTER_SLOTS = {s for s, pos in SLOT_CODES.items() if pos not in ("Bench", "IR")}

# player['proTeamId'] -- current through the 2025 season.
PRO_TEAM_CODES = {
    -1: "Bye",
    0: "FA",
    1: "ATL",
    2: "BUF",
    3: "CHI",
    4: "CIN",
    5: "CLE",
    6: "DAL",
    7: "DEN",
    8: "DET",
    9: "GB",
    10: "TEN",
    11: "IND",
    12: "KC",
    13: "LV",   # was OAK through 2019
    14: "LAR",
    15: "MIA",
    16: "MIN",
    17: "NE",
    18: "NO",
    19: "NYG",
    20: "NYJ",
    21: "PHI",
    22: "ARI",
    23: "PIT",
    24: "LAC",
    25: "SF",
    26: "SEA",
    27: "TB",
    28: "WSH",
    29: "CAR",
    30: "JAX",
    33: "BAL",
    34: "HOU",
}

# player['stats'][i]['statSourceId']
STAT_ACTUAL = 0
STAT_PROJECTED = 1

# schedule[i]['winner']
WINNER_HOME = "HOME"
WINNER_AWAY = "AWAY"
WINNER_TIE = "TIE"
WINNER_UNDECIDED = "UNDECIDED"
