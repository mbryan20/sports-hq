"""Open-Meteo kickoff weather and a modest scoring adjustment (wind, rain, cold). Domes skipped."""
from datetime import datetime, timedelta
from functools import lru_cache
from .http import cfbd, get_json


@lru_cache(None)
def venues():
    return {v["id"]: v for v in cfbd("/venues")}


def kickoff_weather(game):
    v = venues().get(game.get("venueId"))
    if not v or v.get("dome") or v.get("latitude") is None:
        return None
    t = datetime.fromisoformat(game["startDate"].replace("Z", "+00:00"))
    if t - datetime.now(t.tzinfo) > timedelta(days=15):
        return None
    d = get_json("weather", "https://api.open-meteo.com/v1/forecast", max_age_h=6,
                 latitude=v["latitude"], longitude=v["longitude"],
                 hourly="temperature_2m,precipitation,wind_speed_10m",
                 wind_speed_unit="mph", temperature_unit="fahrenheit", timezone="UTC",
                 start_date=t.date().isoformat(), end_date=(t + timedelta(hours=4)).date().isoformat())
    hrs = d["hourly"]["time"]
    key = t.strftime("%Y-%m-%dT%H:00")
    if key not in hrs:
        return None
    i = hrs.index(key)
    win = range(i, min(i + 4, len(hrs)))
    return {
        "wind": max(d["hourly"]["wind_speed_10m"][j] for j in win),
        "precip": sum(d["hourly"]["precipitation"][j] for j in win),
        "temp": d["hourly"]["temperature_2m"][i],
        "city": v.get("city"),
    }


def total_adjustment(w):
    """Points off the game total (negative), split evenly between teams by the caller."""
    if not w:
        return 0.0
    adj = -0.4 * max(0.0, w["wind"] - 12)
    if w["precip"] >= 8:
        adj -= 2.0
    elif w["precip"] >= 3:
        adj -= 1.0
    if w["temp"] < 25:
        adj -= 1.5
    return max(adj, -7.0)
