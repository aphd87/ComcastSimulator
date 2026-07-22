# CableOS — Design Notes

A Streamlit business simulation for teaching cable/streaming portfolio economics through the lens of Comcast/NBCUniversal's networks. Set in 2012, at the start of the cord-cutting shift. FERPA-safe: students register with a pseudonym team name only, no PII is stored (see `app.py`, `utils/game_state.py`).

This doc captures the original design intent (from Zach's mechanics brief) reconciled against what's actually implemented, so the two don't drift apart as the codebase evolves.

## Premise

It's 2012. Linear TV's growth era is ending — subscribers are cutting the cord, Netflix is spending aggressively, and every network still runs its own siloed P&L. The student is the General Manager of a network, responsible for the show slate, the budget, and Operating Cash Flow (OCF) — with the long game being survival into the streaming transition.

## Jobs To Be Done

**Student (player)**
- When I'm handed a portfolio of shows I didn't choose, I want to quickly tell cash cows from dogs, so I can decide what to renew, cancel, or fund without re-deriving the whole P&L by hand.
- When I have to decide whether a new show goes on linear or streaming, I want a side-by-side P&L (ad revenue/CPM vs. subscriber LTV) built for me from a few inputs, so I can reason about the actual tradeoff instead of guessing.
- When I schedule a show's premiere date, I want to see the cash-timing consequence of a late-month launch, so I understand why amortization timing — not just total cost — matters.
- When I clear a network, I want a transparent score breakdown (not just pass/fail), so I know which specific decisions helped or hurt.
- When I fail a level, I want a bounded number of practice retries before advancing anyway, so one bad first attempt doesn't block the rest of the course.

**Instructor**
- When I run this in a live class, I want zero student PII stored anywhere, so I stay FERPA-compliant without having to vet the tool myself.
- When multiple teams play at once, I want a shared, tamper-resistant leaderboard keyed to the *first* attempt, so grading reflects real decisions, not the best of unlimited retries.
- When I teach a concept (BCG matrix, HHI diversification, amortization timing, LTV/CAC), I want it available as in-app reference content, not just something I lecture separately, so students can check the theory against their own numbers mid-game.
- When a level's difficulty needs tuning, I want the pass thresholds and scoring weights centralized in one place, so I'm not hunting through UI code to rebalance the game.

## Core financial mechanics

Grounded in `utils/models.py` (constants and formulas) and `utils/game_state.py` (progression/scoring).

### Amortization — the central teaching mechanic
Content cost is spread over an amortization window, paid monthly starting the month a show airs (ASC 926-style):
- **Oxygen**: 3-year (36-month) curve, ~$250–400K/episode — cheaper content, more breathing room.
- **Bravo**: 12-month curve, ~$650–900K/episode (reality) — costs hit harder each year, 5% escalation on renewal.
- **Peacock (SVOD)**: 36-month curve — spend upfront for deferred subscriber LTV instead of ad revenue.

**The premiere-day cash trough** (`Show.premiere_day_analysis()`, `pages/schedule.py`): a show launching March 30 absorbs a full month's amortization payment against only ~2 days of ad revenue. This is implemented essentially verbatim from the original spec, down to the March 30 example.

### Revenue model
- **Ad revenue**: `rating × $7M/rating-point × marketing lift × cord-cutting decay` (`Show.ad_revenue`).
- **Distribution (affiliate) revenue**: `cable subscribers (eroding 3%/yr) × $0.35/sub/month × 12 × escalation (capped Y5)` (`distribution_revenue()`) — the "dummy distribution revenue off subscriber count" from the original spec, now a real formula.
- **Marketing ROI**: each $1M of marketing spend lifts rating by ~1.5% (`MKT_ROI_PER_M`), split evenly across active shows.

### Green Light model (`pages/greenlight.py`, `greenlight_linear`/`greenlight_svod`)
The core strategic decision from the original spec — "do you put this show on linear or Peacock?" — fully built out:
- Side-by-side P&L: linear (cost, ad revenue, marketing, OCF, 12-month amortization) vs. SVOD (cost, subscriber lift, 3-year LTV, 36-month amortization).
- A crossover chart showing the month cumulative SVOD LTV overtakes linear's cumulative ad revenue.
- A rating × episode-cost sensitivity table (profitable vs. cancel, color-coded).
- Marketing-spend ROI comparison across both platforms.
- In 2012 (low year), linear wins on immediate cash; by year 7+, SVOD LTV starts winning — matches the original "should change over time" note.

### Scheduling / forecasting
An hourly viewership index (`HOURLY_INDEX`, 24 buckets peaking 8–10pm) simplifies the "every hour gets a forecast" idea from the original spec into a ratio system tractable for students, used in `pages/schedule.py` and `pages/forecast.py`.

### 10-year full-portfolio simulation (`pages/forecast.py`, `ten_year_sim()`)
Models the full arc: Oxygen alone (Y1–3) → + Bravo (Y4–7) → + Peacock (Y8+), tracking ad revenue, distribution revenue, cost, G&A, OCF, and cable sub erosion year over year.

## Progression & scoring

Three sequential levels — **Oxygen → Bravo → Peacock** — each independently scored:

| Network | Pass threshold (OCF margin) | Note |
|---|---|---|
| Oxygen | 12% | Cheaper content, longer amortization — more forgiving |
| Bravo | 15% | Core cash-cow economics, tighter budget |
| Peacock | 10% | SVOD early days — thinner margins accepted |

Score is a weighted composite (`compute_score`, `SCORE_WEIGHTS`), not just OCF:
- OCF margin — 35%
- Average show ROI — 25%
- Genre diversification (inverse HHI) — 15%
- Marketing efficiency — 15%
- Sound renewal decisions — 10%

**Attempts**: first attempt is locked as the official leaderboard score. Up to `MAX_ATTEMPTS` (3) total; a team can advance past a failed level once they've passed on any attempt *or* completed at least one retry — no free pass on a single first-try fail, but no permanent block either.

## Deliberate simplification vs. the original spec

The original brief described continuous multi-year play — "prove yourself over 3–5 years, then earn a second network; launch streaming in year 6, 8, or 10." The built game instead uses **pass/fail attempts** to gate advancement between networks, rather than a single unbroken 10-year playthrough. This is an intentional compression for classroom time constraints, not a missed requirement — the 10-year full-portfolio arc still exists as a standalone forecasting exercise (`pages/forecast.py`), just decoupled from the level-gating mechanic itself.

## App structure

| Tab | File | Purpose |
|---|---|---|
| Simulation | `pages/simulation.py` | Quarterly turn engine — Decisions → Results × 4 quarters, then submit for score. Current main gameplay loop (replaced `portfolio_v2.py`). |
| P&L / OCF | `pages/finance.py` | Full income statement, revenue decomposition, distribution model. |
| Schedule & Amortization | `pages/schedule.py` | Premiere-day cash trough, monthly amortization grid. |
| Green Light | `pages/greenlight.py` | Linear vs. SVOD P&L builder for a new show concept. |
| Renewal | `pages/renewal.py` | Renew/cancel decisions, cost escalation, budget impact. |
| 10-Year Forecast | `pages/forecast.py` | Full portfolio simulation across all three networks. |
| Leaderboard | `pages/leaderboard.py` | Per-network rankings, official-attempt-only, FERPA-safe. |
| Theory | (in `app.py`, `THEORY_CONTENT`) | BCG matrix, HHI diversification, cord-cutting S-curve, amortization, LTV/CAC. |

`pages/portfolio_v2.py` is superseded by `simulation.py`'s quarterly engine (per commit `24ce9c9`) — likely safe to remove once confirmed nothing else imports it.

## Open direction: a movie/theatrical component

Floated 2026-07-22, not yet scoped or built. Universal Pictures is a real NBCUniversal division, and theatrical economics (box office exhibitor splits, marketing spend front-loaded relative to production cost, PVOD windows, home entertainment, and the Peacock exclusive-window strategy) are a genuinely different financial model than the TV amortization curves this simulator already teaches — good pedagogical contrast, not a redundant reskin.

**Recommendation**: treat as a 4th/bonus level built *after* the core Oxygen → Bravo → Peacock arc, not bolted onto the existing three. It needs its own revenue engine (box office attendance/splits, theatrical-window-to-PVOD-to-streaming timing) rather than reusing `Show`'s ad-revenue/amortization model as-is. Worth a real scoping conversation before implementation — what's the pass/fail metric (box office ROI? total windowed revenue? Peacock exclusivity value?), and does it plug into the existing leaderboard/attempt system or stand alone.

## Original mechanics brief (Zach, preserved verbatim in spirit)

Recovered from an untracked `Zach Notes.docx` found in a stale duplicate clone (`OneDrive/Desktop/ComcastSimulator`) — preserved here since it's the closest thing to a founding design doc and wasn't committed anywhere.

> Let's pretend it's 2012 — the beginning of the linear downturn. People are cutting the cord, streaming, belts are tightening, cable's growth period has ended. Managing portfolio allocations across different networks — in 2012 every network has individual leadership, focused on sole P&Ls. You have a network like Bravo — has built a solid stable of shows (Below Decks, Housewives), needs to focus on diversifying content mix while being beholden to pretty strict budget constraints: $750K/episode, 5% uptick each year to renew, 3% uptick in budget, 12-month amortization curve — every month you pay 1/12 of total freight of the show, you pay the first of the month. On March 30th, I am paying for 29 days of no revenue of the show.
>
> Year 1 you have a list of 20 shows, they all have some estimate against them. There's a research department to forecast what the ratings of the shows are; a scheduling team tries to optimize schedule to maximize short-term ratings and long-term IP development; finance team calculates ratings and costs, makes sure the costs hit the budget numbers, and we are maximizing revenue against cost allocation. Land all of the shows on the schedule, try to hit the budget — if you have extra money, allocate it to marketing or more shows. ROI on marketing vs. ROI on show without marketing. Dummy distribution revenue if we know there are X million subs of network X in 2012, 5% distribution rev, calc ad sales. Play that out 10 years.
>
> In year 2, different budget — they're going to have to choose to renew/cancel based on costs and revenue associated with it. Prove themselves over the first 3–5 years that they are maximizing their OCF; if they do a good job, take on a second network — Oxygen, cheaper content, $300K an episode, 3-year amortization curve — then they have to allocate funds across those two networks. If they do well on that, year 6, 8, or 10, the company chooses to launch a streaming network.
>
> When a show launches you start paying for the show in the month it airs — if I debut a show March 1st, 10 episodes at $750K/12, I pay this number in March, whether March 1st or March 30th. If you launch a show on March 30th you are accumulating some revenue and paying for a show that is not accumulating revenue — how do you fund your cash cows vs. your other shows, how you will make these decisions. Put it all to linear to maximize short-term profits, or others may say do a lower OCF in hopes of a better long-term future — for every dollar spent, higher return on linear vs. SVOD, but this should change over time.
>
> Dummy green light model: a great show — the pitch — NBC original — do you put it on NBC or Peacock? Green light model: this is rating on linear, this is performance on Peacock in terms of number of paid adds, LTV curve from subscription revenue, engagement of the show — you could build this P&L on what it would look like on linear vs. SVOD. Build out a revenue ratio: every hour of every day gets a forecast in terms of how many people watch, but we can add a ratio on top of this so that this is easier for students. Revenue for premiere episode for each of them.
