"""Yahoo Fantasy API (XML flavour — far more regular than its JSON).

Since July 2026 Yahoo answers 403 "This application is not authorized" for apps that haven't been
approved through sports.yahoo.com/developer/access. Reads raise YahooPending in that state, writes
raise YahooWriteDenied, so the rest of the app degrades to "push me the swap" instead of failing.
"""
import os
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from cryptography.fernet import Fernet

from .common import STATE, session

API = "https://fantasysports.yahooapis.com/fantasy/v2"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
TOKEN_FILE = STATE / "yahoo_token.enc"  # Fernet-encrypted with the TOKEN_KEY secret
REDIRECT = "oob"


class YahooPending(Exception):
    """API access not (yet) granted to this app."""


class YahooWriteDenied(Exception):
    """Token can read but not change lineups."""


def _strip_ns(root):
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _err(r):
    m = re.search(r'"description":\s*"([^"]+)"|<description>([^<]+)', r.text or "")
    return f"HTTP {r.status_code}: " + ((m.group(1) or m.group(2)) if m else (r.text or "")[:200])


def _fernet():
    key = os.environ.get("TOKEN_KEY")
    return Fernet(key.encode()) if key else None


def load_refresh_token():
    f = _fernet()
    if f and TOKEN_FILE.exists():
        return f.decrypt(TOKEN_FILE.read_bytes()).decode()
    return os.environ.get("YAHOO_REFRESH_TOKEN")


def save_refresh_token(token):
    f = _fernet()
    if not f:
        return False
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_bytes(f.encrypt(token.encode()))
    return True


def token_request(**body):
    r = session.post(TOKEN_URL, data={**body, "redirect_uri": REDIRECT},
                     auth=(os.environ["YAHOO_CLIENT_ID"], os.environ["YAHOO_CLIENT_SECRET"]), timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"Yahoo token endpoint {r.status_code}: {r.text[:200]}")
    return r.json()


def lineup_xml(week, moves):
    rows = "".join(f"<player><player_key>{escape(k)}</player_key><position>{escape(pos)}</position></player>"
                   for k, pos in moves)
    return ('<?xml version="1.0"?><fantasy_content><roster><coverage_type>week</coverage_type>'
            f"<week>{int(week)}</week><players>{rows}</players></roster></fantasy_content>")


def parse_player(p):
    sel = p.find("selected_position")
    return {
        "key": p.findtext("player_key"),
        "yahoo_id": p.findtext("player_id"),
        "name": p.findtext("name/full"),
        "team": (p.findtext("editorial_team_abbr") or "").upper(),
        "pos": p.findtext("display_position"),
        "eligible": [e.text for e in p.findall("eligible_positions/position")],
        "slot": sel.findtext("position") if sel is not None else None,
        "status": p.findtext("status"),
    }


class Yahoo:
    def __init__(self):
        if not os.environ.get("YAHOO_CLIENT_ID"):
            raise YahooPending("Yahoo credentials not configured")
        self.refresh_token = load_refresh_token()
        if not self.refresh_token:
            raise YahooPending("No Yahoo refresh token configured")
        self.refresh()

    def refresh(self):
        tok = token_request(grant_type="refresh_token", refresh_token=self.refresh_token)
        self.access = tok["access_token"]
        new = tok.get("refresh_token")
        if new and new != self.refresh_token:
            self.refresh_token = new
            save_refresh_token(new)

    def _call(self, method, path, body=None, retry=True):
        headers = {"Authorization": f"Bearer {self.access}"}
        if body:
            headers["Content-Type"] = "application/xml"
        r = session.request(method, f"{API}/{path}", data=body, headers=headers, timeout=30)
        if r.status_code == 401 and retry:
            self.refresh()
            return self._call(method, path, body, False)
        if r.status_code == 403:
            raise (YahooPending if method == "GET" else YahooWriteDenied)(_err(r))
        if r.status_code >= 400:
            raise RuntimeError(f"Yahoo {method} {path}: {_err(r)}")
        return _strip_ns(ET.fromstring(r.content)) if r.content.strip() else None

    def get(self, path):
        return self._call("GET", path)

    def my_team(self, league_name, season):
        root = self.get(f"users;use_login=1/games;game_codes=nfl;seasons={season}/leagues")
        lk = next((lg.findtext("league_key") for lg in root.iter("league")
                   if (lg.findtext("name") or "").strip().lower() == league_name.lower()), None)
        if not lk:
            raise RuntimeError(f"Yahoo league '{league_name}' not found for {season}")
        for t in self.get(f"league/{lk}/teams").iter("team"):
            if t.findtext("is_owned_by_current_login") == "1":
                return lk, t.findtext("team_key"), t.findtext("name")
        raise RuntimeError("Could not find your team in the Yahoo league")

    def roster_slots(self, lk):
        root = self.get(f"league/{lk}/settings")
        return [(rp.findtext("position"), int(rp.findtext("count") or 1)) for rp in root.iter("roster_position")]

    def roster(self, tk, week):
        return [parse_player(p) for p in self.get(f"team/{tk}/roster;week={week}").iter("player")]

    def opponent(self, tk, week):
        for m in self.get(f"team/{tk}/matchups;weeks={week}").iter("matchup"):
            for t in m.iter("team"):
                if t.findtext("team_key") != tk:
                    return t.findtext("name")
        return None

    def free_agents(self, lk, position, count=25):
        root = self.get(f"league/{lk}/players;status=A;position={position};sort=AR;count={count}")
        return [parse_player(p) for p in root.iter("player")]

    def set_positions(self, tk, week, moves):
        """moves: [(player_key, position)]. Raises YahooWriteDenied without write scope."""
        self._call("PUT", f"team/{tk}/roster", lineup_xml(week, moves))
