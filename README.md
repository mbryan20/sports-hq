# Sports HQ

Phone-first fantasy football dashboard: https://mbryan20.github.io/sports-hq/
(Safari → Share → Add to Home Screen.)

Everything runs on GitHub Actions; no laptop, no paid APIs, no LLM calls.

| What | When |
|---|---|
| Lineups tab refresh | every run (hourly, every 10 min in game-day windows) |
| Injury watch | every 10 min from 2h before each kickoff until it locks (decided from ESPN kickoff times, so DST doesn't matter) |
| Weekly tab (start/sit + top FA adds) | Tuesday 7am CT |
| Failure push | any failed workflow run |

Sources: Sleeper (rosters, projections, injuries), ESPN (kickoffs, injuries), Yahoo Fantasy API.

## Alerts (ntfy)

Subscribe to the topic stored in the `NTFY_TOPIC` secret in the ntfy iPhone app (server `ntfy.sh`).

- **Yahoo**: an OUT/IR/inactive starter with a healthy same-position bench player is swapped
  automatically, read back, and you get "Swapped X → Y". Yahoo currently grants read-only access
  ("write access is not currently available"), so until that changes you get the exact swap to make.
- **Sleeper** (read-only API): you get the exact swap to make.
- No healthy bench option → best free-agent suggestion. Nothing is ever added or dropped automatically.

## Yahoo access (needed for Kosmonauts)

Since July 2026 Yahoo returns `403 This application is not authorized` for apps not approved
through its Fantasy API access program. Until then the Kosmonauts tab says "pending" and the rest works.

1. Apply at https://sports.yahoo.com/developer/access/ with the App ID shown at https://developer.yahoo.com/apps/ (Sports HQ) and sign the agreement Yahoo emails you.
2. When Yahoo says access is enabled, the next scheduled run picks it up automatically.
3. If Yahoo makes you create a new app: update the `YAHOO_CLIENT_ID` / `YAHOO_CLIENT_SECRET`
   secrets (repo → Settings → Secrets → Actions, works on a phone browser), then re-auth below.

### Re-auth from a phone

1. Open `https://api.login.yahoo.com/oauth2/request_auth?client_id=<CLIENT_ID>&redirect_uri=oob&response_type=code&scope=fspt-r`
   and tap Agree. Yahoo shows a short code.
2. GitHub → Actions → **Yahoo re-auth** → Run workflow → paste the code.

The new refresh token is stored encrypted (`state/yahoo_token.enc`, key in the `TOKEN_KEY` secret).

## Secrets

`YAHOO_CLIENT_ID`, `YAHOO_CLIENT_SECRET`, `YAHOO_REFRESH_TOKEN`, `TOKEN_KEY`, `NTFY_TOPIC`.

## Local

```
pip install -r requirements.txt
python -m unittest discover -s tests   # includes the Yahoo swap dry-run
DRY_RUN=1 python -m shq.run
```
