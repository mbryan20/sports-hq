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
