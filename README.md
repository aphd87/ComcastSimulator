# The Slate — Media Portfolio Simulation

A Streamlit business simulation that teaches media portfolio economics through Comcast/NBCUniversal's networks (**TV / Streaming**: Oxygen → Bravo → Peacock) and Universal Pictures (**Movies**: a five-film slate). Each TV network runs its own calendar era (2012 onward); Movies runs on two-year production cycles.

Full design intent, mechanics, and session history: see `DESIGN_NOTES.md`.

## Course materials (`docs/`)

| File | For | What it is |
|---|---|---|
| `The_Slate_Student_Guide_TV_Streaming.docx` | Students | Step-by-step walkthrough of the TV simulation |
| `The_Slate_Student_Guide_Movies.docx` | Students | Step-by-step walkthrough of the Movies simulation |
| `The_Slate_Instructor_Plan_Movies_Week_85min.docx` | Instructors | Board reference for opening Movie Week with the Movies simulation (85-minute class, 60 minutes of play) |

The Word files are generated: edit `docs/build_student_guides.py` or `docs/build_instructor_plan.py` and re-run them (`python docs/build_student_guides.py`) rather than editing the .docx by hand, so the guides never drift from the app.

**Typical course flow:** students play **Oxygen as homework** and submit; in class, teams play **Bravo or Peacock** (any network can be opened directly from the Choose Your Network screen). The next session opens Movie Week with the **Universal Pictures** simulation. Teams use the same University / School / Class / Team Name every time so their scores sit together on the Leaderboard.

## Deployment note — for Darden and adopting schools

This tool ships as a business case used by many schools. Every school's scores, Pitch Board posts, and leaderboards are kept separate by **school + class section**, so one hosted copy can serve many schools, or each school can run its own.

- **No AI features and no API keys.** AI pitch feedback was removed on 2026-10-01 in favor of the **Peer Pitch Board** (below).
- **Settings live in the deployment's Streamlit Secrets** (Settings → Secrets on Streamlit Cloud, or `.streamlit/secrets.toml` locally — **never commit that file**).

## Saving scores — the database (`DATABASE_URL`)

**Without a database, everything is wiped when the app restarts.** Streamlit Community Cloud erases the app's disk on every reboot, every redeploy (any push to `main`), and when an idle app sleeps and wakes. Without a database, the app saves scores, team state, and Pitch Board posts to that disk, and they're lost. With homework played over several days, that matters.

Set up a free database once (about 5 minutes):

1. Create a free Postgres project at [Neon](https://neon.tech) (no credit card on the Free plan; 0.5 GB is far more than a class uses).
2. On the project dashboard click **Connect** and copy the connection string (`postgresql://…?sslmode=require…`).
3. In Streamlit Cloud: the app's **⋮ → Settings → Secrets**, add this line, and **Save**:
   ```toml
   DATABASE_URL = "postgresql://user:password@host/dbname?sslmode=require"
   ```
   Keep the straight double quotes around the whole string.
4. **⋮ → Reboot app**, then open the **Leaderboard**. Near the bottom it should say *"💾 Scores are saved to this deployment's database."* A ⚠️ "local disk" warning means the setting isn't being read.

The app creates its tables automatically: `slate_leaderboard`, `slate_team_state`, `slate_pitches`. It connects with the `psycopg2` driver (pinned in code, because newer SQLAlchemy versions default to a different driver). Treat the connection string like a password; if it's ever shared, reset the database role's password in Neon and update the secret.

**Status (2026-10-01):** the Darden pilot deployment is connected to a Neon project (`the-slate`, AWS US East 2, Free plan) owned by the instructor's Google account, pending a move to a Darden-owned account.

**After any push, reboot once.** Streamlit Cloud has occasionally kept an old copy of a changed file in memory after a redeploy, causing an error until a reboot (**⋮ → Reboot app**).

## What students do

### TV / Streaming
- **Choose Your Network:** Oxygen, Bravo, or Peacock, each with its own era, starting budget (~$95M / ~$220M / ~$150M), and OCF-margin target (12% / 15% / 10%).
- **Each year, one scrolling page:** Financing (marketing) → Renewal (renew/cancel, premiere months, primetime slots) → Sports Rights (Peacock: bid on NFL, Premier League, or Olympics packages, 5–7 year contracts) → Greenlighting → Simulate.
- **Scheduling is genre-aware:** most genres peak Tue 8PM; Reality and Drama peak on weekend nights.
- **Greenlighting:** up to 3 new shows a year, shared across three paths:
  - acquire a pitch from the marketplace (some have a **rival network bidding**: +25% fee now, or a 50% chance each year the rival signs it);
  - build your own show, which **requires a written pitch**;
  - switching networks or restarting a level undoes that level's added shows, so slots can't be refilled that way.
- **"📊 Why?" boxes:** optional, collapsed charts sit under the decision each one explains.
- **Scoring:** OCF margin 35%, show ROI 25%, genre mix 15%, marketing efficiency 15%, renewal quality 10%. Pass = level OCF margin at or above the network's target.

### Movies (Universal Pictures)
- **Five films, one per two-year cycle** (Year 1 greenlight & produce = the *t* = 0 investment; Year 2 release).
- **A logline is required** before a film can be simulated.
- **Budget buys quality:** each genre has a typical budget (shown to students); P&A and screens saturate past a genre-sized point.
- **Release strategy** (from Film 3): Wide suits tentpoles, Platform suits drama and awards titles, Day-and-Date suits horror and comedy.
- **Financing:** tax incentive, or presale, which works as insurance and pays off for high-variance films.
- **Pay-1 window:** keep it on Peacock, take a flat license, or shop it to competitive bid. Students can accept any bid (shorter terms return the film sooner), or reject all bids and go back to market once.
- **Scoring:** risk-adjusted NPV 45%, capital efficiency 20%, strategic fit 20%, diversification 15%. Each film's graded NPV is **75% decisions + 25% luck** (what it actually earned). Pass = the **decisions-only** (risk-adjusted) NPV averages above $0, so luck moves the score but can't pass a slate; a team that changes nothing always fails.

### Peer Pitch Board
Every pitch a team commits is shared with the other teams in **its own school + class section**: TV shows greenlit from a team's own pitch, and every film a team makes (logline, numbers, and how it actually did). Students see it on the Leaderboard page (**📋 Pitch Board**) and in a "👀 See what other teams in your class have pitched" box beside each pitch form.

### Leaderboard
Official scores are each team's **first submission**. Views by class, school, or all schools; a school-vs-school comparison; and a CSV download of all submissions for grading.

## Instructor settings — per-deployment Secrets

**`YEARS_PER_LEVEL`** — how many in-game years each TV network level runs. Defaults to **4**; any whole number from 2–8 is accepted (out-of-range values are clamped). Every network's era shifts together, e.g. at 4 years: Oxygen 2012–2015, Bravo 2016–2019, Peacock 2020–2023.

```toml
YEARS_PER_LEVEL = 4
```

**`FREE_NAVIGATION`** — lets teams open any network directly. **On by default** (instructor-directed use; all slates are seeded at registration, so jumping ahead is safe). To require passing each level first:

```toml
FREE_NAVIGATION = false
```

Both are read when the app starts: reboot after changing them.

## Playing as a team across multiple laptops (Driver / Follow Along)

At registration each teammate picks a role. **🎮 Driver** makes every decision (one per team); **👀 Follow Along** watches the Driver's choices read-only on their own screen, refreshing automatically every few seconds. Everyone registers with the *identical* University / School / Class / Team Name; that's the whole link (no accounts, FERPA-safe). TV / Streaming only: in Movies, teams share one laptop.

## Development

- Run the tests with the same Python the app uses locally: `python -m pytest -q` (about 520 tests).
- **Changing Movies economics?** Re-run the engine balance check (random-strategy sweep, one-lever sensitivities, greedy hill-climb, slate scores) — not just the tests. See `DESIGN_NOTES.md`.
- All random draws use `utils/seeding.stable_seed` (deterministic across server restarts); never seed with Python's built-in `hash()`.

## Changes on 2026-10-01

- **Student guides** (TV and Movies) and an **instructor board reference** for opening Movie Week, in `docs/`.
- **Choose Your Network** screen; rating and pitch-card definitions; all grey text made white; readable help tooltips.
- **Storage made safe for a full class:** locking + atomic writes (the old code kept 2 of 200 simultaneous submissions), plus optional `DATABASE_URL`; the Postgres driver is pinned to psycopg2.
- **TV:** required pitch for your own shows; rival bids on marketplace pitches; closed a network-switch loophole that refilled slots; "Why?" boxes moved under each decision; genre-aware scheduling.
- **Movies:** required logline; engine rebalanced after QA (budget buys quality, saturating P&A and screens, genre-specific release strategies, presale as insurance); Pay-1 bid terms, accept-any-bid, and re-shop; 25% luck in the grade; year labels explained.
- **AI features removed** and replaced by the **Peer Pitch Board**.
- **Stable random seeding** everywhere, so a server restart no longer re-rolls teams' draws.
