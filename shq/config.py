"""Static settings. Nothing secret lives here; credentials come from env (GitHub Secrets)."""
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Chicago")
SEASON = 2026
SITE_URL = "https://mbryan20.github.io/sports-hq/"

SLEEPER_USERNAME = "michaelbryan"
SLEEPER_TEAM_NAME = "Domo Arigato"
YAHOO_LEAGUE_NAME = "Kosmonauts"

# Injury watch starts this long before each kickoff and runs until lock (kickoff).
WATCH_LEAD_HOURS = 2

# Weekly tab: Tuesday 7am Central.
WEEKLY_WEEKDAY = 1  # Monday=0
WEEKLY_HOUR = 7

# Daily digest (Today tab + one push when something needs fixing): 8am Central. A digest whose run
# GitHub delays past DIGEST_PUSH_UNTIL updates the Today tab without pushing.
DIGEST_HOUR = 8
DIGEST_PUSH_UNTIL = 13

# Kosmonauts scoring in Sleeper stat keys: 0.5 PPR, 6-pt passing TD, otherwise Yahoo defaults.
YAHOO_SCORING = {
    "pass_yd": 0.04, "pass_td": 6, "pass_int": -1, "pass_2pt": 2,
    "rush_yd": 0.1, "rush_td": 6, "rush_2pt": 2,
    "rec": 0.5, "rec_yd": 0.1, "rec_td": 6, "rec_2pt": 2,
    "fum_lost": -2, "kr_td": 6, "pr_td": 6,
    "fgm_0_19": 3, "fgm_20_29": 3, "fgm_30_39": 3, "fgm_40_49": 4, "fgm_50p": 5, "xpm": 1,
    "sack": 1, "int": 2, "fum_rec": 2, "def_td": 6, "safe": 2, "blk_kick": 2,
    "pts_allow_0": 10, "pts_allow_1_6": 7, "pts_allow_7_13": 4, "pts_allow_14_20": 1,
    "pts_allow_21_27": 0, "pts_allow_28_34": -1, "pts_allow_35p": -4,
}

# Every league Sports HQ follows. "name" is the tab label and the key alerts use, so keep it stable.
# platform: yahoo (API, or the laptop's saved roster while the API is gated), sleeper (public API),
# espn (public leagues read directly; private=True ones come from the laptop's ESPN snapshot).
LEAGUES = [
    {"name": "Kosmonauts", "sport": "nfl", "platform": "yahoo"},
    {"name": "Domo Arigato", "sport": "nfl", "platform": "sleeper", "dynasty": True},
    {"name": "Guillotine", "sport": "nfl", "platform": "sleeper", "league_id": "1385516543386845184", "format": "guillotine"},
    {"name": "3-Ball FB", "sport": "nfl", "platform": "espn", "league_id": 1829431, "team_id": 10, "season": 2026, "dynasty": True},
    {"name": "Stempak", "sport": "nfl", "platform": "espn", "league_id": 1912619648, "team_id": 8, "season": 2026, "private": True},
    {"name": "Bro-vid19", "sport": "nfl", "platform": "espn", "league_id": 84829230, "team_id": 9, "season": 2026, "private": True},
    {"name": "3-Ball BB", "sport": "nba", "platform": "espn", "league_id": 184031, "team_id": 7, "season": 2027, "dynasty": True},
    {"name": "Ball is Life", "sport": "nba", "platform": "espn", "league_id": 190278, "team_id": 5, "season": 2027, "private": True},
]
ESPN_PRIVATE = [lg for lg in LEAGUES if lg["platform"] == "espn" and lg.get("private")]
