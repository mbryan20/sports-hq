"""docs/lib/core.js rules that run in the browser, checked through Node (skipped when Node isn't installed)."""
import json
import os
import shutil
import subprocess
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Enough of a browser for core.js to load: it only registers listeners at load time.
LOAD = ("const fs=require('fs'),vm=require('vm');const noop=()=>{};"
        "const document={currentScript:{src:'https://x/docs/lib/core.js'},addEventListener:noop,querySelectorAll:()=>[],"
        "getElementById:()=>null,documentElement:{dataset:{}},body:{dataset:{}}};"
        "const ctx=vm.createContext({document,URL,console,localStorage:{getItem:()=>null,setItem:noop},location:{hash:''},navigator:{}});"
        "ctx.window=ctx;ctx.open=noop;ctx.addEventListener=noop;"
        "vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);"
        "console.log(JSON.stringify(vm.runInContext(process.argv[2],ctx)))")


def ms(y, mo, d, h, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() * 1000)


class PicksStale(unittest.TestCase):
    """The footer's "Picks cards" job is amber only when a Wed 9pm / Thu 8pm / Fri 9pm / Sat 8am CT build was missed."""

    def js(self, expr):
        node = os.environ.get("NODE") or shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        out = subprocess.run([node, "-e", LOAD, os.path.join(ROOT, "docs", "lib", "core.js"), expr],
                             check=True, capture_output=True, text=True, cwd=ROOT)
        return json.loads(out.stdout)

    def stale(self, last, now):
        return self.js(f"SHQ.picksStale({json.dumps(last)}, {now})")

    def test_tuesday_after_saturday_refresh_is_not_stale(self):
        sat = "2026-11-07T14:06:07.001235+00:00"                       # Sat 8:06am CT
        self.assertFalse(self.stale(sat, ms(2026, 11, 10, 22)))        # Tue 4pm CT
        self.assertFalse(self.stale(sat, ms(2026, 11, 12, 4)))         # Wed 10pm CT: the 9pm slot is under 3h old

    def test_missed_slots_are_stale(self):
        sat = "2026-11-07T14:06:07+00:00"
        self.assertTrue(self.stale(sat, ms(2026, 11, 12, 16)))         # Thu 10am CT, no Wed 9pm draft
        fri = "2026-11-07T03:30:00+00:00"                              # Fri 9:30pm CT
        self.assertFalse(self.stale(fri, ms(2026, 11, 7, 16)))         # Sat 10am CT: Sat 8am slot still in grace
        self.assertTrue(self.stale(fri, ms(2026, 11, 7, 18)))          # Sat noon CT: Sat 8am build missed
        self.assertTrue(self.stale(None, ms(2026, 11, 10, 22)))

    def test_central_daylight_time(self):
        # Sat Oct 31 is still CDT (UTC-5): the 8am slot is 13:00 UTC, fresh from 11:00 UTC
        self.assertFalse(self.stale("2026-10-31T11:30:00+00:00", ms(2026, 10, 31, 17)))
        self.assertTrue(self.stale("2026-10-31T10:30:00+00:00", ms(2026, 10, 31, 17)))


class TryMoveBox(PicksStale):
    """Every league page carries the Try a move / Ask Claude box (Q-054); lib/move.js mounts it when it shows."""

    def test_box_on_the_league_page(self):
        d = {"lineups": {"leagues": {"Stempak": {"sport": "nfl", "starters": [], "bench": [], "advice": {}}}}}
        html = self.js(f"SHQ.detail('Stempak', {json.dumps(d)})")
        self.assertIn('class="mv-host" data-mv="Stempak"', html)
        self.assertIn("Try a move · Ask Claude", html)


if __name__ == "__main__":
    unittest.main()
