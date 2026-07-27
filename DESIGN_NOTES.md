# VideoOS — Design Notes

**Renamed from CableOS 2026-07-24** — the simulator spans both TV/Streaming and Movies now, so "Cable" undersold it; "Video Network Portfolio Simulator" is the actual scope. Code, docs, and UI all use VideoOS going forward; historical entries below that predate the rename keep the old name where it's part of the historical record (commit messages, past session summaries) rather than rewriting history.

A Streamlit business simulation for teaching video network portfolio economics through the lens of Comcast/NBCUniversal's networks. Set in 2012, at the start of the cord-cutting shift. FERPA-safe: students register with a pseudonym team name only, no PII is stored (see `app.py`, `utils/game_state.py`).

This doc captures the original design intent (from Zach's mechanics brief) reconciled against what's actually implemented, so the two don't drift apart as the codebase evolves.

## Status as of 2026-07-27 — read this first

**What happened today:** Added a 4th 🏠 App nav button (landing screen was previously unreachable after leaving it, see "App structure" below) and wired the two previously-orphaned `pages/finance.py` (P&L/OCF) and `pages/forecast.py` (10-Yr Forecast) pages in as new tabs under TV/Streaming. Then triaged Zach Schlessel's three unresolved structural asks (see below) and built the AI-graded custom show-concept feature: `utils/ai_grading.py` (Claude Haiku 4.5, `client.messages.parse` with a Pydantic `ShowConceptGrade` schema — originality/market-fit/feasibility/presentation, each 0-25) wired into `pages/greenlight.py` right before the title/IP legal-risk check. **BYOK, per school — this is the important part**: no API key is ever committed to this repo; each school's own Streamlit Cloud deployment sets its own `ANTHROPIC_API_KEY` in that deployment's secrets, and `api_key_configured()` gates the whole feature off (with a plain "ask your instructor" message, not a crash) when unset. Documented in the new `README.md` as an explicit action item to flag to Darden — this tool is going out to schools worldwide, so costs must be per-school, not centrally funded. `anthropic>=0.100.0` added to `requirements.txt`. 46 tests still pass; verified `api_key_configured()` correctly returns `False` with no `secrets.toml` present (this machine's current state). **Not yet verified in a real browser** — same standing gap as everything else in this doc, now also covering the AI-feedback UI.

**Still open, carried over from 2026-07-24 below:**
- No real human browser click-through has ever happened, on Day 1 or Day 2 (or the newer tabs/features added since).
- Whether the Streamlit Cloud deployment survived the `ImportError` fix from 07-22 — last checked via a user-initiated reboot on 07-27, outcome not yet confirmed back to this doc.
- Two of Zach Schlessel's three structural asks are now resolved (see 2026-07-27 entry above): budget sliders confirmed as staying dollar-based (no change needed), AI-graded show concepts built. **Movies category rework (sequels/new-IP/kids/horror-indie layered on the existing genre/NPV engine) is still unscoped** — open question is what the 4 categories should actually change mechanically (variance bounds? greenlight options? something else?). Needs a fresh design pass before building.

## History — 2026-07-24 end of session (superseded by 2026-07-27 above)

**What happened today:**
1. Restructured the quarterly Decisions phase (`pages/simulation.py`) into **Financing → Renewal → Greenlighting → Scheduling**. Renewal/Greenlighting/Scheduling reuse `pages/renewal.py`/`greenlight.py`/`schedule.py` verbatim — all three were fully built in earlier sessions but never actually imported or called from anywhere in the app, so students could never reach them despite the math and UI already existing. Financing (new revenue-stream breakdown — ad vs. distribution revenue — ahead of the existing marketing slider and cancel-shows decision) stays open by default; Renewal/Greenlighting/Scheduling sit below it.
2. Real bug caught mid-session: the original plan wrapped Renewal/Greenlighting/Scheduling in `st.expander`, which broke — `renewal.py` and `schedule.py` each already open their own internal `st.expander`, and Streamlit disallows nesting one expander inside another. Fixed by using `st.tabs` for the outer grouping instead; no changes to any of the three reused files' internals.
3. Sidebar cut down to nav-only. Removed the "Budget Allocation" marketing slider (duplicated the Decisions-phase slider; the Decisions-phase one is now the single source of truth). Movies (Day 2) moved from a sub-tab nested under whichever TV network happened to be active to its own peer button in the sidebar's network selector, next to Oxygen/Bravo/Peacock — `app.py`'s main content now branches on `ss.active_network == "movies"`.
4. Verified via headless `streamlit.testing.v1.AppTest`, run against the Anaconda install (per the "Real environment gotcha" note further down) — team registration, Oxygen's full Decisions phase (all four new sections, including the tabs' own internal expanders), and the Movies sidebar button all execute with zero exceptions.
5. Wrote an MBA-facing overview of the whole tool as a polished `.docx`. Not part of this repo; a standalone deliverable generated with `python-docx`, grounded in this doc's JTBD/mechanics sections rather than re-derived.

**Second pass, same day** — Zach Schlessel's feedback (quarters→years, real performance-linked budget, paid research, title-risk check, 3 charts), then a QA pass and a rename/nav restructure per the user:
6. Implemented quarters→years, real performance-linked budget, paid Research, title/IP legal-risk check, and 3 additive charts — see "Real mechanics built 2026-07-24" and the Zach Schlessel feedback section further down for full detail. Committed to git (commit `5cb039d`) at the user's request, not pushed anywhere.
7. QA pass caught two real bugs from the quarters→years rewrite: a dead `annual_budget` import left in `simulation.py`/`renewal.py`, and `app.py`'s `LEVEL_BRIEFS` "Suggested Order of Play" text still referencing pre-refactor tab names. Both fixed. Also deleted `pages/portfolio_v2.py` (confirmed dead, user chose to delete just this one — `finance.py`/`forecast.py` kept as-is, still orphaned but potentially useful later).
8. **Renamed CableOS → VideoOS** throughout code/docs, per the user (the tool now spans TV/Streaming + Movies, "Cable" undersold it).
9. **Sidebar restructured to 3-way top-level nav** (Leaderboard / TV-Streaming / Movies) — see "App structure" below. Added a "Choose Your Simulation" landing screen shown once after registering.
10. MBA overview `.docx` on the Desktop rebranded and content-refreshed — `VideoOS - MBA Overview.docx` (old `CableOS - MBA Overview.docx` removed). Not a text swap: rebuilt to describe the annual engine (4 years/level, was quarters), performance-linked budget, paid Research, title/IP risk check, and the 3-way TV/Movies/Leaderboard nav — the original was written before any of that existed.

**Third pass, same day** — UX rework of the Decisions phase per user feedback ("it's not clear students are being guided from decision to decision", "I want students to see previous year's P&L", "click each show and see a schedule populate underneath"):
11. **Guided 4-step wizard** replaces the old "Financing always-open + free-form tabs" layout — one step's content shown at a time (Financing → Renewal → Greenlighting → Scheduling), explicit numbered step tracker, Back/Next navigation, step 4's Next becomes End Year. New `ss.decision_step` state, reset to 1 at every year/level boundary (new year, redo year, network switch, advance, restart). Fixed a real staleness bug while doing this: the marketing slider previously only synced to `ss.mkt_budget` at End Year, so other pages reading it mid-year saw a stale value — now `key="mkt_budget"` binds the slider directly to that session-state field, always live.
12. **Last Year's P&L recap** — a pinned strip at the top of Decisions, starting year 2, showing the prior year's actual revenue/cost/OCF/margin. Previously this info vanished the moment a student advanced past Results.
13. **Renewal rebuilt as show cards** (`pages/renewal.py`) — the old column-of-selectboxes table replaced with a grid of per-show cards (rating, projected OCF, IP score, Renew/Watch/Cancel selector, and a premiere-month control that writes directly to the `Show` object's `air_month`). Below the grid, a live "This Year's Schedule" mini-view (12 month columns, count of premieres per month, hover for names) updates in real time as premiere months change — the "select a show, see a schedule populate" interaction the user asked for. Everything else in `renewal.py` (Budget Bridge, Genre Decay chart, paid Research, IP-value scatter, full data table) is untouched.
14. **Real, newly-confirmed instance of the existing AppTest limitation** (same class already diagnosed for `movies.py` in `tests/test_movies_page.py` — button handlers calling `st.rerun()` corrupt AppTest's widget-state tracking across a transition, not a real app bug). Adding explicit `key=` to `greenlight.py`'s and `schedule.py`'s previously-unkeyed widgets (a real, worthwhile fix regardless) shifted but didn't eliminate it — chaining several step transitions in one `AppTest` script (especially through Renewal's new 40-widget card grid) reliably crashes the harness, even though every individual step and interaction was verified correct in isolation (cards render, decisions persist, premiere months mutate the real Show objects, the mini-schedule updates, step counters increment/reset correctly). Did not redesign the wizard to dodge this, same reasoning as the existing `movies.py` precedent — would be a real UX downgrade for a test-tool artifact. **This makes a real human browser click-through of the full wizard flow (all 4 steps, multiple years) the single most important thing to do before using this with students** — more so than anything else flagged in this doc, since it's the most interaction-dense part of the app and the piece verified least completely by AppTest.

**Still open, carried over from 2026-07-22 below — neither has changed:**
- **No real human browser click-through has ever happened**, on Day 1 or Day 2. AppTest confirms today's restructure executes without exceptions — that's meaningfully weaker than an actual click-through (visual layout, whether Tailwind renders, whether the four new Financing/Renewal/Greenlighting/Scheduling sections are actually usable in one page rather than just import-clean). **Do this before using any of today's changes in front of students.**
- **Whether the Streamlit Cloud deployment survived the `ImportError` fix from 07-22 was never checked** — do that first, since it's independent of and predates today's local changes.

## History — 2026-07-22 session status (superseded by 2026-07-24 above)

**Live app**: https://comcastsimulator-f3riawhvhbihgap5qh2yzm.streamlit.app/ (Streamlit Community Cloud, auto-redeploys on every push to `main`). **Status unconfirmed** — it threw an `ImportError` on first deploy, a fix went out in the last commit of the day (`31109dd`), but nobody has checked whether the redeploy actually fixed it. **Do that check first, next session.**

**What happened today, roughly in order:**
1. Recovered CableOS's original design brief from an untracked file in a stale duplicate clone, formalized into this doc with JTBD for both student and instructor.
2. Designed and built the entire **Day 2 module** ("Universal Pictures" — movie/theatrical economics: NPV/IRR under variance, release-strategy tradeoffs, award season) — financial engine, turn-based UI, and tests. Caught and fixed a real calibration bug (unrealistic NPV, broken IRR) before shipping, and a real Streamlit deprecation (`components.v1.html` → `st.iframe`).
3. Set up Tailwind CSS (Play CDN, since there's no build pipeline here).
4. Diagnosed (not worked around) a genuine Streamlit AppTest testing-harness limitation — see `tests/test_movies_page.py`'s docstring.
5. **Consolidated the sidebar** per user feedback ("too many options for a simulation") — cut two dead sliders and a stale checklist, removed the Year control.
6. **Fixed a real crash** (`AttributeError: st.iframe`) the user hit running it locally — root cause was two Streamlit versions on their machine at different paths; fixed with a runtime capability check instead of assuming one version.
7. Fixed a theme mismatch (`.streamlit/config.toml` was light while the whole app is dark) and removed a stray duplicate config file.
8. **Built multi-school/multi-class leaderboard scoping** — a team's real identity is now `(school, class_section, team_name)`, not just a name, so two schools both having "Team Alpha" can't collide. Added a scope selector (My Class/My School/All Schools) and a school-vs-school comparison view. Added a 👑 crown icon for #1.
9. User **deployed the app live** to Streamlit Community Cloud (see URL above) and hit an `ImportError`.
10. Diagnosed as a likely Python-version mismatch — `utils/game_state.py`, `utils/models.py`, and `utils/charts.py` used modern `list[...]`/`dict[...]` type-hint syntax (needs Python 3.9+) without the `from __future__ import annotations` safety net, and had only ever been tested against a newer local Python than Cloud might be running. Fixed all three (commit `31109dd`) — **but this diagnosis was made from a redacted error message, not the real traceback, so it's a best-evidence guess, not a confirmed root cause.**

**Next session, in order:**
1. Check the live URL above. If it works, move on. If not, get the *full* (non-redacted) log from the app's "Manage app" panel — that's the one piece of information this session never had access to.
2. Once deployment is confirmed working: a real human click-through of Day 2's full flow (Greenlight → Release → Results ×3 → Complete → Submit) — still nobody has done this, in a browser or otherwise, all session (Claude in Chrome never connected). Also confirm Tailwind actually renders.
3. See "Working list — next up" below for smaller remaining items (award-season variance dimension follow-ups, etc.) — mostly already closed out.

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

Three sequential levels — **Oxygen → Bravo → Peacock** — each independently scored. **Each level is now 4 real years (2026-07-24), not 4 quarters within a frozen Year 1** — see "Annual turn engine" below.

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

**Partially reconciled 2026-07-24**: each level is now a genuine 4-year run (see "Annual turn engine" below) rather than a single frozen year — closer to the original "prove yourself over 3-5 years" framing than the quarterly engine it replaced, though still a bounded-attempt gate per level rather than one continuous playthrough across all three networks. Zach Schlessel's 2026-07-24 feedback pushes further in this direction (see his feedback section) — worth revisiting whether a continuous cross-network arc is the eventual target.

## Annual turn engine (2026-07-24 — replaces the quarterly engine)

Rebuilt `pages/simulation.py` from a quarterly loop (4 quarters inside a frozen "Year 1") to a real annual loop — `ss.year` is now the actual turn counter (1→`YEARS_PER_LEVEL`=4) driving every financial formula, not a fixed value the sidebar used to (and could no longer) change. Direct response to Zach Schlessel's "change from quarters to years" feedback, scoped specifically to the turn-cadence structural change — see his feedback section for the rest, still backlog.

- **Financial math simplified, not just relabeled**: cost/revenue no longer need the `/4` quarterly-slice bookkeeping (`monthly_amort(year)*3`, `ann_mkt/4`, etc.) — a turn is a full year now, so `Show.annual_amort_expense()` / `ad_revenue()` / `distribution_revenue()` are used directly. Removes a real inconsistency the quarterly engine had: revenue/cost were divided into quarters while `year` stayed frozen at 1 all session, so escalation/decay never actually progressed within a level; now each turn genuinely reflects that year's economics.
- **Renewal is now the actual cancellation mechanism.** Wiring Renewal into the Decisions phase earlier the same day only made it *visible* — its Renew/Watch/Cancel choices were written to `ss.renewal_decisions` but never mutated `ss.cancelled_shows`. With annual turns, Renewal is where Zach's "Order of Play" puts the cancellation decision, so its Cancel choices now drive `ss.cancelled_shows` directly at year-end. Financing's old standalone "Decision 2 — Cancel Shows" quick-multiselect was removed as redundant.
- **Cancellation penalty**: mid-year cancellations pay 25% of that year's amortization as a sunk-cost penalty (the annual-cadence equivalent of the old quarterly engine's "50% one-quarter penalty" — same intuition, rescaled).
- Session-state field renames: `ss.sim_month` (quarter-within-year counter) removed — `ss.year` serves this role directly now. `ss.monthly_log` → `ss.yearly_log`; each entry's `"quarter"` key → `"year"`.
- Verified via a full `AppTest` run through all 4 years of Oxygen (Decisions→Results ×4 → Complete → Submit → Advance to Bravo) — no exceptions, real score computed (88.8/100, passed), `ss.year` correctly reset to 1 on advancing to Bravo.
- **Not yet done**: a real human browser click-through of the new annual flow (same standing gap as the rest of this doc — AppTest confirms it executes, not that it's legible/usable on screen).

## App structure

**Sidebar nav restructured 2026-07-24 (second pass, same day)** — three peer top-level sections: 🏆 Leaderboard, 📺 TV/Streaming, 🎬 Movies (`ss.active_section`). Previously Leaderboard was a tab nested inside whichever of TV/Movies was active (duplicated in both), and Movies was a peer of the Oxygen/Bravo/Peacock network buttons rather than a peer of TV itself. The Oxygen/Bravo/Peacock selector is now a secondary selector shown only when TV/Streaming is the active section (`ss.active_network`, unchanged mechanics — lock icons, attempt badges, official scores). A new "Choose Your Simulation" landing screen (`ss.active_section is None`) appears once right after registering, with TV/Streaming and Movies as two cards plus a Leaderboard shortcut; picking a section persists it in the sidebar for free switching afterward.

**4th top-level nav button added (2026-07-27)**: 🏠 App — the landing screen above existed but had no way back to it once you'd picked a section (only "Change Team" got you there, by deregistering). Now `ss.active_section == "app"` (and the initial `None` state) both route to it; the nav button highlights correctly in both cases.

| Section | File | Purpose |
|---|---|---|
| 🏠 App | (landing screen, in `app.py`) | "Choose Your Simulation" cards (TV/Streaming, Movies) + Leaderboard shortcut. Reachable any time via the sidebar now, not just once after registering. |
| 🏆 Leaderboard | `pages/leaderboard.py` | Standalone top-level section as of this pass (was nested tabs, duplicated per-section). Already covered TV networks + Movies internally via its own tabs (`_render_board_tab`, `MOVIES_INFO`) — no wrapping needed, `render()` takes no args and reads `ss` directly. |
| 📺 TV/Streaming → Simulation (tab) | `pages/simulation.py` | Annual turn engine — Decisions → Results × 4 years per network, then submit for score. Financing (revenue-stream breakdown, marketing spend) is the always-open anchor; cancellation lives in the Renewal tab. |
| 📺 TV/Streaming → Renewal (sub-tab) | `pages/renewal.py` | Renew/Watch/Cancel decision matrix, IP-value vs. OCF tradeoff, budget waterfall, paid Research. |
| 📺 TV/Streaming → Greenlighting (sub-tab) | `pages/greenlight.py` | Linear vs. SVOD P&L builder for a new show concept, title/IP legal-risk check. |
| 📺 TV/Streaming → Scheduling (sub-tab) | `pages/schedule.py` | Premiere-day cash trough, monthly amortization grid, scheduling optimizer. |
| 📺 TV/Streaming → P&L / OCF (tab) | `pages/finance.py` | **Wired in 2026-07-27** (previously orphaned). Full income statement, monthly revenue/cost trend, distribution-revenue calculator, revenue-per-rating-point benchmarks — a fuller view than Financing's condensed summary. Reads the currently active network's shows/year/marketing spend from `ss` directly, no new state needed. |
| 📺 TV/Streaming → 10-Yr Forecast (tab) | `pages/forecast.py` | **Wired in 2026-07-27** (previously orphaned). Scenario tool spanning all three networks — adjustable cord-cut rate, budget growth, Bravo/Peacock launch year — independent of the active network's actual progress, so it lives as a tab rather than being tied to `ss.active_network`. |
| 📺 TV/Streaming → Theory (tab) | (in `app.py`, `THEORY_CONTENT`) | BCG matrix, HHI diversification, cord-cutting S-curve, amortization, LTV/CAC. |
| 🎬 Movies | `pages/movies.py` | Universal Pictures — Day 2. Own top-level section, own Theory tab, independent of TV network progress. |

`pages/portfolio_v2.py` — superseded by `simulation.py`'s turn engine (per commit `24ce9c9`), confirmed nothing imported it, **deleted 2026-07-24**.

## Day 2 — Movie/Theatrical Component ("Universal Pictures")

Scoped 2026-07-22. Audience is **MBA students** (same as Day 1) — this is not a simplified undergrad add-on, it should push real capital-allocation-under-uncertainty analysis. Universal Pictures is a real NBCUniversal division; theatrical economics (box office exhibitor splits, marketing spend front-loaded relative to and often exceeding production cost, theatrical/PVOD/streaming windowing, the Peacock exclusive-window strategy) are a genuinely different financial model than Day 1's TV amortization curves — good pedagogical contrast, not a redundant reskin.

**Why Day 1 (TV) comes first, and how it connects**: Day 1 teaches the steady-state building blocks — amortization timing, recurring P&L, portfolio thinking — through a forgiving, repeatable rhythm (20 shows, quarterly turns, retries allowed). Day 1's Green Light tab (linear vs. Peacock for a new show) is structurally the *same question* a movie studio asks — Day 2 doesn't introduce a new concept, it raises the stakes on one students already have: a portfolio of steady, amortized bets (TV) vs. one concentrated, front-loaded, fast-decaying bet (a movie).

**Duration: 6 years, structured as 3 movie cycles of 2 years each.** Revised from an initial 5-year guess — a real studio film runs 18–24 months from greenlight to release (pre-production/writing, the shoot, then post/VFX), so 5 years barely fit two full cycles. 6 years gives students **3 complete greenlight-to-release cycles**, enough to actually apply a lesson learned in Cycle 1 to Cycle 2 and 3 — the movie-industry equivalent of Day 1's "first attempt is official, retries are practice," but at the scale of a whole bet instead of a quarter.

- **Cycle structure (repeated 3×, Years 1–2, 3–4, 5–6)**:
  - **Year N (Greenlight/Production)** — the single-movie decision: budget tier, genre, talent, P&A commitment. Cash goes out; no revenue yet.
  - **Year N+1 (Release/Windowing)** — release-strategy decision (theatrical/day-and-date/platform), window-length choice, then actual box-office/streaming results resolve against the bull/base/bear scenario drawn for that title.
- **Portfolio complexity escalates across cycles**, not within Year 1 alone: Cycle 1 is a single film in isolation (learn the mechanics). Cycles 2–3 layer in slate effects — multiple concurrent titles, cannibalization dynamics compounding as PVOD/streaming windows realistically shorten year over year (mirrors Day 1's Oxygen → combined-portfolio escalation, just compressed into 2 more cycles instead of network unlocks).

### Cost structure — the core contrast with Day 1
Both production budget (`P`) and P&A/marketing spend (`M`) are committed *upfront*, before any revenue visibility — unlike Day 1's monthly-amortized cost spread over a season. Total capital at risk = `P + M`.

### Revenue engine — windowed waterfall, not a steady monthly stream
- **Opening weekend** = `f(marketing awareness, star power, genre appeal, screen count)` — same diminishing-returns marketing curve as Day 1's `MKT_ROI_PER_M`, but the payoff concentrates into one weekend instead of a season.
- **Total domestic box office** = opening weekend × a **multiplier** (real industry term — "the film did a 2.8x"). This is where quality/word-of-mouth risk lives: marketing can buy an opening, not legs. Model the multiplier as the variable that differs across scenarios (see Variance below), not the opening weekend itself.
- **International box office** = domestic × a genre-dependent multiplier.
- Studio nets roughly half of box office (exhibitor split, front-loaded higher early in the run, declining over time) → **PVOD window** (premium rental, studio keeps the large majority of the transaction) → **Peacock exclusive streaming window** → **EST/home entertainment** → long-tail **library licensing**.

### NPV over IRR as the primary metric
Discount the windowed cash flows at a studio cost-of-capital proxy (~10–12%), subtract `P + M` upfront. NPV is the right unit — a single bet doesn't have a "margin," it has a return on capital at risk. Report IRR alongside it, since front-loaded-cost/back-loaded-revenue structures can swing IRR wildly — that swing is itself part of the lesson.

### Variance is graded, not hidden
Run bull/base/bear scenarios on the box-office multiplier (and optionally the international multiplier). Score partly on **NPV under the bear case**, not just expected NPV — the single biggest thing that separates this from Day 1's deterministic P&L, and the reason a real-options framing (staged investment; option to expand/abandon at each checkpoint — greenlight → production → marketing commit → wide vs. platform release) is legitimate here, not decorative.

### Cannibalization math — the direct extension of Day 1's Green Light tab
If a student picks day-and-date/streaming, apply a cannibalization discount to theatrical box office, but credit a dollarized "attributable subscriber value" (Peacock adds/retention tied to the title — same LTV logic Day 1 already applies to SVOD). Net comparison of *(theatrical-heavy NPV)* vs. *(streaming-heavy NPV, net of cannibalization)* is the actual decision, calculable rather than a gut call. Ground the release-strategy decision in real comparables (WarnerMedia's 2021 HBO Max day-and-date experiment, Universal's post-2020 shortened theatrical window with AMC) rather than an abstract slider.

### Composite score (parallel to Day 1's `compute_score`, different components)
- **Risk-adjusted NPV** (weighted toward the bear case) — largest weight, core financial outcome.
- **Capital efficiency** — box-office lift per marketing dollar, penalizing "just spend the max."
- **Strategic fit** — did the release-window choice maximize combined theatrical + streaming value net of cannibalization, vs. a naive "theatrical is always better" default.
- **Decision quality at checkpoints** — if built with staged real-options turns, grade whether the student's contingent choice matched what the interim signal (tracking/awareness data, opening-weekend actuals) actually implied.

**Pass/fail gate**: positive risk-adjusted NPV (not a fixed OCF margin %) — judged on whether the bet cleared its cost of capital under a reasonably conservative scenario.

**Not yet decided**: exact turn structure for the staged real-options checkpoints (biggest open design risk — Day 1's tabs are single-decision-per-page; Day 2 may need a sequential-stage UI closer to `pages/simulation.py`'s quarterly engine), and whether Day 2 shares the existing leaderboard/attempt system or stands alone.

## Frontend: Tailwind CSS

Added 2026-07-22 (`utils/styles.py::TAILWIND_INJECT`, wired in `app.py`). Streamlit has no bundler step and this repo has no Node/npm toolchain, so this uses Tailwind's **Play CDN** (browser-side JIT) rather than a compiled build pipeline — the right-sized choice for a classroom tool, even though Tailwind's own docs flag Play CDN as unsuited to high-traffic production (doesn't apply here).

**Real gotcha, worth remembering**: `st.markdown(html, unsafe_allow_html=True)` renders via `innerHTML`, and `<script>` tags inserted through `innerHTML` never execute in any browser — this is a DOM-level restriction, not Streamlit-specific. The correct injection path is `st.components.v1.html(...)`, but that renders inside a *sandboxed iframe* — so the injected script has to reach out via `window.parent.document` to attach itself to the actual app page, not just the throwaway iframe. `TAILWIND_INJECT` does this, with a dedup guard (`id="tailwind-cdn"`) since Streamlit re-runs the whole script on every interaction.

Theme extended (`tailwind.config`) to match the existing hand-rolled palette in `GLOBAL_CSS` (bg/surface/line/ink/gold/etc., DM Serif Display/DM Mono/DM Sans), so new markup can mix Tailwind utility classes with the existing design tokens rather than clashing with them. **Adoption is incremental, not a forced rewrite**: new pages/components (including Day 2) should reach for Tailwind classes first; the ~3,500 lines of existing inline-styled HTML across `app.py`/`pages/*.py` don't need migrating unless touched anyway.

## Final JTBD list (consolidated — Day 1, Day 2, and the frontend)

**Student (player)**
1. When I'm handed a portfolio of shows I didn't choose, I want to quickly tell cash cows from dogs, so I can decide what to renew, cancel, or fund without re-deriving the whole P&L by hand.
2. When I decide whether a new show goes on linear or streaming, I want a side-by-side P&L (ad revenue/CPM vs. subscriber LTV) built from a few inputs, so I can reason about the real tradeoff instead of guessing.
3. When I schedule a show's premiere date, I want to see the cash-timing consequence of a late-month launch, so I understand why amortization *timing*, not just total cost, matters.
4. When I clear a network, I want a transparent score breakdown, so I know which specific decisions helped or hurt.
5. When I fail a level, I want a bounded number of practice retries before advancing anyway, so one bad first attempt doesn't block the rest of the course.
6. **(Day 2)** When I greenlight a movie, I want to see risk-adjusted NPV across bull/base/bear scenarios, not one deterministic number, so I learn to evaluate a concentrated bet the way a real studio does.
7. **(Day 2)** When I choose a release strategy (theatrical/day-and-date/platform), I want the cannibalization-vs-subscriber-value tradeoff calculated explicitly, so the decision is analytical, not a gut call.
8. **(Day 2)** When I manage Cycles 2 and 3 of a multi-year slate, I want portfolio-level effects (compounding cannibalization, shrinking windows) to carry forward from my earlier decisions, so the exercise rewards sustained strategy, not just one good pitch.

**Instructor**
9. When I run this in a live class, I want zero student PII stored anywhere, so I stay FERPA-compliant without vetting the tool myself.
10. When multiple teams play at once, I want a shared, tamper-resistant leaderboard keyed to the first attempt, so grading reflects real decisions, not the best of unlimited retries.
11. When I teach a concept (BCG matrix, HHI, amortization timing, LTV/CAC, and — new for Day 2 — NPV/real options under variance), I want it available as in-app reference content, so students can check theory against their own numbers mid-game.
12. When a level's difficulty needs tuning, I want pass thresholds and scoring weights centralized in one place, not scattered through UI code.
13. **(Frontend)** When I extend the UI (Day 2 or otherwise), I want a real utility-class system available, so new pages aren't hand-rolled inline-style strings copied from old ones.

## Working list — next up

**Built 2026-07-22, same session as the design above:**
- **`utils/movie_models.py`** — full financial engine: `MovieProject` dataclass, opening-weekend/box-office/PVOD/subscriber-value/library formulas, `windowed_cashflows()`, `npv()`/`irr()`, `risk_adjusted_npv()`, `capital_efficiency()`, `strategic_fit_score()`, `compute_movie_score()`, `draw_actual_multiplier()` (seeded, reproducible-per-team-per-cycle continuous outcome draw via `np.random.triangular`), `nearest_scenario_label()`.
  - **Calibration matters, caught before shipping**: the first pass produced a $200M movie showing a $650M+ NPV and an IRR pinned at the 500% search ceiling for every scenario — both wrong. Root causes: (1) `opening_weekend()` stacked star-power and P&A boosts multiplicatively instead of additively, blowing up box office scale; (2) theatrical revenue was timed at 2 weeks post-release, and *annualizing* a return that concentrated that fast produces an absurd IRR even for an ordinary hit. Fixed by rebalancing the opening-weekend formula (verified against realistic $10-20K/screen benchmarks) and moving theatrical revenue recognition to the run's midpoint (~6 weeks). Re-verified with a real smoke test (see the numbers below) before building any UI on top of it — don't trust a financial model that merely runs without erroring.
  - Verified realistic output: a $200M tentpole (wide theatrical) now shows base-case NPV ≈ +$179M, bear ≈ +$44M, bull ≈ +$369M — a believable spread. A $25M indie (platform release) shows base ≈ -$1M, bear ≈ -$10M — appropriately marginal/risky. Day-and-date on the same tentpole in Cycle 3 drops NPV to negative (theatrical suppression not fully offset by subscriber value) — a real, teachable result, not an artifact.
  - `irr()` now distinguishes "never recovers capital" (`None`) from "true IRR exceeds the 500% search ceiling" (`float('inf')`, displayed as ">500%") from an actually-converged rate — it no longer silently returns a boundary value dressed up as a precise answer.
- **`pages/movies.py`** — the turn engine, mirroring `pages/simulation.py`'s Decisions→Results phase-state-machine pattern (confirmed as the right call, not just a superficial resemblance): Greenlight (concept + capital commit) → Release Strategy (side-by-side risk-adjusted NPV preview across wide/platform/day-and-date, extending Day 1's Green Light tab) → Results (actual outcome resolves against a hidden continuous draw, revenue waterfall chart, slate-so-far chart) → repeats for all `CYCLES_TOTAL` (3), then a Complete phase with the composite score breakdown and submission. Submission reuses Day 1's existing FERPA-safe leaderboard infra (`game_state.py::record_attempt`) under a new `"movies"` network key — no new persistence system needed.
- **`pages/leaderboard.py`** refactored — per-network tab body extracted into `_render_board_tab()` and reused for a new "🎬 Universal Pictures" tab (`MOVIES_INFO`, deliberately *not* added to `NETWORK_INFO`/`NETWORK_ORDER` so it can't leak into the sidebar's TV network selector). Without this, a submitted movie score would have been recorded but invisible anywhere in the UI.
- **`app.py`** — new "🎬 Movies (Day 2)" tab, positioned after Simulation and before Leaderboard. Fully independent of the sidebar's Active Network (Oxygen/Bravo/Peacock) selection — Day 2 doesn't read or depend on `ss.active_network`.

**Verified this session**: all new/changed files syntax-check and import cleanly; the financial engine was smoke-tested directly (function calls, not just "doesn't crash") through several scenarios until the numbers were realistic; the local server (`localhost:8511`) starts with no traceback on the full wiring.

**Not yet verified — needs a human in a real browser** (Claude in Chrome wasn't connected in this environment across this entire multi-session effort, repeated connection attempts all failed): a full click-through of Greenlight → Release Strategy → Results → 3 cycles → Complete → Submit, and confirming Tailwind actually renders. Please run through at least one full slate before trusting this in front of students.

**Also built same session, working the list further (2026-07-22):**
- **`tests/test_movie_models.py`** (+ `tests/__init__.py`, `requirements-dev.txt`) — 24 tests, all passing. Not just "does it run" checks: pins the tentpole/indie NPV examples above to realistic dollar ranges, asserts `irr()` correctly distinguishes never-recovers (`None`) / exceeds-ceiling (`inf`) / a real converged rate, confirms day-and-date nets out worse than wide theatrical for a big tentpole (and skips PVOD entirely), confirms the window shrinks per cycle and floors at 17 days, confirms the scenario draw is reproducible per team+cycle and genre-bounded, confirms scoring clamps to 0-100 and an empty slate scores zero/fails. This is the regression guard the original calibration bug should have had from the start.
- **Genre-differentiated variance** — `GENRE_VARIANCE_SPREAD` widens/narrows the bear-to-bull spread per genre around a shared base case (Horror 1.6x baseline spread — the textbook high-variance genre — down to Awards/Prestige 0.7x, a narrower specialty-audience range). `domestic_box_office()`, `draw_actual_multiplier()`, and `nearest_scenario_label()` all now resolve genre-adjusted bounds automatically — no UI changes needed, the Greenlight/Release preview cards already read genre-aware NPV ranges through the existing code path.
- **Screen-count sanity warning** (`pages/movies.py`) — soft warning (not a hard block, math still runs either way) when planned opening screens are wildly disproportionate to total capital committed (rough benchmark: 18 screens/$M), since a student could otherwise "game" a huge opening off a tiny budget in a way no real distribution deal would allow.
- **Real Streamlit deprecation caught and fixed**: `st.components.v1.html` (used for the Tailwind injection) is deprecated, flagged for removal after 2026-06-01 — discovered via a warning surfaced while import-checking the full app, not from documentation. Replaced with `st.iframe(TAILWIND_INJECT, height=1)`, Streamlit's own recommended successor, which auto-detects a raw HTML string the same way. One real gotcha: `st.iframe` rejects `height=0` outright (`StreamlitInvalidHeightError`) where the old API silently allowed it — `height=1` is the smallest valid value and is visually negligible.

**Also built (2026-07-22): `tests/test_movies_page.py`** using Streamlit's official `streamlit.testing.v1.AppTest` harness — runs `pages/movies.py::render()` headlessly (no browser) and confirms the Greenlight phase renders with zero exceptions, the expected widgets exist, starts at cycle 1 with an empty log, and the bear/base/bull preview actually shows.

**Real, conclusively-diagnosed limitation, not a bug in the app**: a full interactive click-through (Greenlight → Release → Results → 3 cycles → Complete → Submit) via `AppTest` was attempted and hit a genuine Streamlit 1.59.2 AppTest bug — any button handler calling `st.rerun()` (the pattern used consistently across this *entire* codebase: `simulation.py`, `app.py`, and `movies.py` all do `if st.button(...): ss.x = y; st.rerun()`) corrupts AppTest's widget-state tracking on the *second* interaction after a phase transition, raising a spurious `KeyError` for a widget from the *previous* phase that's no longer rendered. Proven via a minimal synthetic repro isolated from the real code: removing `st.rerun()` made an identical two-phase flow pass cleanly; adding it back reproduced the failure every time, regardless of click pattern (chained vs. separate `.run()`, held references vs. re-querying fresh, an extra "settle" pass — none of it helped). **Did not change `movies.py`'s `st.rerun()` usage to work around this** — that would make it inconsistent with the rest of the app (which presumably works fine in real browsers, where this AppTest-specific issue doesn't apply) for no real benefit. Full detail preserved in `tests/test_movies_page.py`'s module docstring so a future session doesn't have to redo this multi-hour diagnosis. Worth retrying the interactive tests if Streamlit is ever upgraded past 1.59.2.

**Award season / critical reception — built 2026-07-22.** A genuinely separate risk axis from box-office performance, not just another slider: a movie can open huge and get panned, or open modestly and find acclaim, so `draw_critical_reception()` uses its own independent seeded triangular draw (own genre-tuned `CRITICAL_RECEPTION_BOUNDS`, own seed offset from the box-office multiplier's draw) rather than deriving reception from the same outcome. Two real effects, both zero when `critical_score` is unresolved (planning-stage bear/base/bull previews correctly show *no* reception effect — a student can't know reviews in advance, and leaking that into the preview would be a spoiler):
- **Library/EST longtail scales 0.7x–1.8x** with reception — acclaimed films have real, enduring library value independent of theatrical performance.
- **Awards-season rerelease bump** — a new, genuinely separate cash-flow window (~11 months out, For-Your-Consideration-style limited rerelease), but *only* for `AWARDS_ELIGIBLE_GENRES` (Drama, Awards/Prestige) clearing `AWARDS_CONTENDER_THRESHOLD` (72/100). An action tentpole never gets this, no matter how well-reviewed — matches how the real industry actually works, not just "higher score = more money everywhere."

`risk_adjusted_npv`/`capital_efficiency`/`strategic_fit_score`/`compute_movie_score` all thread an optional `critical_score` through — the **final slate score now reflects the actually-resolved reception**, not just the hypothetical bear/base box-office scenarios it already accounted for. This closes a real gap that would otherwise have existed: the Results screen would have shown the awards bump, but the Complete-phase score would have silently dropped it since it reconstructs `MovieProject` objects from scratch rather than reusing the resolved outcome. Caught before shipping, not after. 7 new tests (`TestAwardSeason`) cover: action never gets the bump, drama below/above threshold, no-critical-score means no bump and unscaled longtail, acclaimed vs. panned longtail direction, draw reproducibility/independence from the box-office seed, and that final scoring only ever helps (never hurts) relative to being scored blind.

**Final state, end of day 2026-07-22**: 46 tests passing (35 on Day 2's financial engine/page, 11 on multi-school leaderboard scoping — see "Multi-school / multi-class leaderboard" below), full app import-checks cleanly against the actual Anaconda runtime (not just whatever Python a fresh shell happens to resolve to — see "Status as of" at the top of this doc for why that distinction mattered), local server starts with no traceback, app is live-deployed (status unconfirmed, see top of doc).

**Still genuinely open** (see "Status as of 2026-07-22" at the top for the full, current list — this one is superseded):
1. ~~The actual interactive click-through~~ — still true, still nobody's done it, tracked at the top of this doc now alongside the deployment check.
2. ~~Tailwind's actual rendering is unconfirmed~~ — same, tracked at the top now.

## Multi-school / multi-class leaderboard — added 2026-07-22

Team identity used to be just `team_name` (a free-text pseudonym), which meant two different schools — or two sections of the same school — both having a "Team Alpha" would silently share attempt history and leaderboard position. Fixed by making a team's real identity the triple **(school, class_section, team_name)**:

- **Registration** (`app.py`) now collects School (curated dropdown — Northwestern Kellogg / Indiana Kelley / "Other" free-text, so any school can use this without a code change) and Class/Section (free text) alongside Team Name. Same FERPA posture as team_name itself — self-reported classroom context, not tied to any student identity.
- **Every gating/attempt function** in `utils/game_state.py` (`get_team_attempts`, `get_official_score`, `get_attempt_count`, `can_advance`, `get_team_network_status`) now takes `school`/`class_section` and scopes matching on all three fields, not just team_name.
- **`get_network_leaderboard(network, school=None, class_section=None)`** — `None` (default) means unfiltered/cross-school; a value scopes down. This is the one function that directly satisfies all four of the user's requirements via different filter combinations:
  1. **Class-only leaderboard** → `school=X, class_section=Y`
  2. **Team-vs-team across schools** → unfiltered (`None, None`), now shown with school/class as a label on each row
  3. Same as #1 — a class leaderboard *is* the class-scoped view
  4. **School-overall leaderboard** → `school=X, class_section=None` (every class at that school, rolled together)
- **`get_school_rollup(network)`** — new aggregate function (avg score, pass rate, top score, team count per school) — the school-vs-school comparison view, satisfying the other half of #2.

`pages/leaderboard.py` exposes this as a **scope selector** (My Class / My School / All Schools, `st.radio`) controlling the per-network podium/rankings/chart, plus a standalone **School Comparison** section (table + bar chart) always showing every school side by side regardless of scope selection.

**Verified, not just wired up**: `tests/test_game_state_scoping.py` (11 tests) — same-name teams at different schools/sections genuinely don't collide (attempts, `can_advance`, leaderboard ranking all isolated correctly), filtered views exclude what they should, rollup aggregates and ranks correctly. 46 tests total now passing.

**Fun top-3 icons** (the lighter half of this request): 👑 crown for #1 (replacing a plain gold medal) with a looping CSS glow (`utils/styles.py::crown-glow`), silver/bronze medals unchanged for #2/#3.

## Running this for a real class — operational notes

**Team identity has no account system, by design.** Registration is a free-text pseudonym (`st.text_input`), not tied to email or any student identity — matches the FERPA framing. Real consequence: if a team's members open the app on **separate devices**, they are *not* synced — each gets an independent session (own decisions, own budget state). Teams should share one device/browser tab.

**The leaderboard is a plain local file** (`leaderboard.json`, `utils/game_state.py::LEADERBOARD_FILE`), not a database. Whether different teams' scores land on one shared leaderboard depends entirely on deployment:
- **One central server** (e.g. Streamlit Community Cloud, one URL the whole class visits) → genuinely shared leaderboard. This is almost certainly the right model for a class and isn't set up yet — worth doing before real use.
- **Each student runs it locally** → every instance has its own separate file; nobody's scores are actually comparable.

**Sidebar is nav-only as of 2026-07-24** (Team Registration, Active Network selector including Movies) — no gameplay decisions live there anymore. This was the end state of a two-step consolidation:
- **2026-07-22** (user feedback: "too many options for a simulation") — went from 5 sections to 3 (Team Registration, Active Network, Budget Allocation) by removing dead Development/Reserve budget sliders (never read by `pages/simulation.py`'s scoring engine), a stale Quick Checklist (referenced pre-redesign tab names), and the Simulation Year slider (a first attempt always plays Year 1 now; `ss.year` stays fixed at 1 internally, only the ability to change it was removed).
- **2026-07-24** — removed the remaining Budget Allocation/Marketing slider too, since it duplicated the Decisions-phase Financing section's marketing control (the Decisions-phase one is now the only copy). Added Movies as a peer button in the Active Network selector, alongside Oxygen/Bravo/Peacock.

**Real environment gotcha, worth remembering**: this machine has two Streamlit installs on PATH at different versions — `C:\Program Files\Python314` (1.59.2) and Anaconda (`C:\Users\apalo\anaconda3`, 1.45.1). `streamlit run app.py` in a real shell resolves to the **Anaconda one**. A fix verified only against the other install (`st.iframe`, a newer API 1.45.1 doesn't have) shipped broken and threw `AttributeError` in actual use. Fixed with a `hasattr(st, "iframe")` runtime check rather than assuming a version. **Any future change should be verified against `anaconda3\python.exe` / `anaconda3\Scripts\streamlit.exe` explicitly**, not just whatever `python`/`streamlit` a fresh shell resolves to.

## Zach Schlessel (NBCUniversal) — feedback received 2026-07-24, pending triage

Received via email, covers two distinct artifacts — **only the second applies to this repo**:
1. **"Thesis Edits Needed"** (remove Paris Olympics reference; focus on Peacock originals vs. library vs. NBC/Bravo investment value; emphasize cross-platform cost amortization) — reads as edits to the written case study (`Independent Study Case A/B - Comcast NBCU` docs), not this codebase. Not actioned here.
2. **Simulation design feedback** (below) — a real, structural rework proposal for CableOS, not yet reconciled against what's built. Preserved close to verbatim so the actual ask isn't lossy-summarized before a decision is made on scope/priority.

**Major structural tensions with the current build, flagged before any of this is implemented:**
- ~~**"Change from quarters to years"**~~ — **implemented 2026-07-24**, see "Annual turn engine" above. User confirmed the specific structure via a clarifying question: each level (Oxygen/Bravo/Peacock) is now 4 real annual turns, not 4 quarters within a frozen year — matching this feedback's "Multi-Year Dynamics...compounds over a 4-year window" and "Deck 1/Deck 2" language, and the *original* Zach brief's "prove yourself over 3-5 years" framing more closely than the quarterly engine it replaced.
- ~~**Performance-based budget compounding**~~ — **implemented 2026-07-24**, see "Real mechanics built" below. Was a flat 3%/yr; now genuinely tied to each year's actual margin.
- ~~**Paid "research" option**~~ — **implemented 2026-07-24**, see below.
- ~~**Title/IP legal-risk check**~~ — **implemented 2026-07-24**, see below.
- **Amortization reassigned from network to content category** — currently Oxygen=36mo/Bravo=12mo/Peacock=36mo (network-based); this feedback proposes True Crime=24mo vs. Non-True-Crime=12mo (genre-based), independent of which network airs it. **Still deliberately not implemented** — would retroactively change the cost burden on Oxygen's mostly-True-Crime slate and could break the calibrated 12%/15%/10% pass thresholds. Needs a scope decision (replace vs. layer on top of network base) before touching it.
- **Budget model reframed as abstract 0-100 allocation sliders** — needs a value-mapping decision (what does "73" mean in dollars?) before it can be built without guessing. Not yet implemented.
- **AI-graded custom show-concept option** — needs an actual LLM API call wired up (secrets/cost implications), a different kind of change than anything else here. Not yet implemented.
- **Movies category rework** (sequels/new-IP/kids/horror-indie replacing Day 2's current risk-adjusted-NPV/genre model) — would touch the tested, calibrated Day 2 engine (46 passing tests). Not yet implemented, needs explicit scope agreement first.

## Real mechanics built 2026-07-24 (beyond the quarters-to-years engine and the 3 charts)

Three more items from Zach's feedback, each genuinely wired into gameplay (not illustrative, not decorative):

1. **Performance-linked budget** (`utils/models.py::performance_linked_growth()`) — replaces the flat 3%/yr `annual_budget()` growth. `ss.level_budget` is now real state: clear the level's pass threshold in a given year → next year's budget grows 8%; land between 0 and threshold → the old 3%; go negative → a 6% cut. Wired into the year-end transition in `pages/simulation.py` (captured in each `yearly_log` entry as `"budget"`, reset alongside other per-level state on network switch/advance/restart). Financing shows the real number with an over-budget warning (content cost + marketing vs. `ss.level_budget`) where none existed before (the old sidebar's budget-cap warnings were removed earlier the same session along with the sidebar's redundant marketing slider — this restores real budget feedback, just performance-linked instead of fixed). Renewal's Budget Bridge shows next year as a range (best/worst case) rather than a false-precision single number, since it genuinely isn't knowable until this year's results are in.
2. **Paid Research** (`pages/renewal.py`, `utils/models.py::preview_show_variance()`/`variance_to_stars()`) — $2M/show, deducted immediately from `ss.level_budget`. Reveals a real 1-5 star signal by replicating the *exact* seeded RNG sequence `_compute_year()` will use for that team+year (same seed formula, same per-show draw order) — a genuine preview of the actual upcoming outcome, not a decorative random number. `ss.research_revealed` tracks per-show-per-year reveals, reset with other per-level state.
3. **Title/IP legal-risk check** (`pages/greenlight.py`) — a "Show Name / Concept" matching any real title already in `utils/data.py`'s slates (Bravo/Oxygen/Peacock combined) triggers a legal-risk banner and blocks the P&L build entirely (`return` before any calculation), matching "Risk = 0 score: take an existing show title without permission, gets sued." Reuses existing show data as the protected-titles set rather than a separate hardcoded list.

All three verified via a single `AppTest` run through a full 4-year Oxygen level (with research purchases each year) → Submit → Advance to Bravo → Movies nav, no exceptions, `level_budget` correctly reset to Bravo's own base ($220M) on advancing.

Next step on the remaining items (genre-based amortization, 0-100 sliders, AI-graded show creation, movies category rework): agree scope/priority with the user before writing more code — each has a real conflict or missing decision, spelled out above.

**Three additive charts built 2026-07-24** (after the annual engine, on the user's request to visualize themes from this feedback "without upsetting anything" — no mechanic/formula changes, existing math surfaced or reused):
1. **Genre decay-curve chart** (`pages/renewal.py`) — plots `Show.projected_rating()`'s existing ip_score-driven maturation forward 6 years, grouped by genre. Answers Zach's own open question "how visible should decay curves be to students?" by making math that already existed visible for the first time.
2. **Linear vs. Streaming economics chart** (Financing, `pages/simulation.py`) — runs the team's own portfolio-average show through the existing `greenlight_linear`/`greenlight_svod` formulas at 3 year-checkpoints, visualizing Zach's "linear has higher CPM, Peacock has lower sub acquisition but originals drive usage" framing with the team's real numbers instead of a generic hypothetical.
3. **Year-over-year performance vs. budget chart** (Complete phase, `pages/simulation.py`) — actual OCF margin per year plotted against the real fixed-3%/yr budget line *and* an illustrative performance-linked budget line (margin ≥ threshold → +8%/yr, 0 to threshold → the real +3%, negative → −6%) computed from the team's actual results. Explicitly illustrative — does not change `annual_budget()` or any real budget mechanic; visualizes what Zach's "good year = more budget, poor year = a cut" idea would have looked like without committing to it yet.

Verified via `AppTest` through a full 4-year level (Decisions → Results ×4 → Complete) — all three charts render with no exceptions at every year. Still not human-browser-verified, same standing gap as everything else in this doc.

---

> **Streaming Entertainment Simulation: Zach's Feedback**
>
> **High Level Strategic Focus**
>
> *Core Business Shift (2018 to 2026)*
> 2018: Arms dealer model, build your own streamer, or buy smaller player (Tubi, Star, Showtime). 2026: Competing with FAANG, big talent deals (Taylor Sheridan), high sports rights costs, can't shut down Peacock, decade-long content rights, must partner with tech or pursue M&A.
>
> *Key Strategic Emphasis for Case*
> Shift from subscription growth to profitability. Prioritize profitability over subscriber acquisition. Studio business model changes: less profit from traditional window, incentives need to align with talent. No monoculture anymore: streaming built on old sitcoms and dramas, broadcast can't compete.
>
> *Thesis Edits Needed*
> Remove Paris Olympics reference (too far out). Edit to focus on value of Peacock originals vs. library vs. investment in NBC/Bravo. Emphasize how streaming amortizes costs across platforms.
>
> **Peacock Business Model Context**
>
> *Three Platform Structure*: Peacock (standalone streamer), NBC (linear network/broadcast), Bravo (linear cable).
>
> *Key Financial Dynamics — Linear (NBC/Bravo) Advantages*: Higher CPMs, more ad spots per hour (40-min shows, 20 min content), better ad revenue per hour, strong brand ecosystem, lower marketing spend required.
>
> *Peacock Challenges & Opportunities*: Lower sub acquisition than linear. Originals drive more subscriptions and usage; greater variability in performance. Library is cheaper but harder to predict — attracts fewer subs but is profitable (programmatic advertising). Sports as loss leader: NFL season is 5 months, massive sub spike, then churn.
>
> *The Profitability Curve Problem*: Amortization curve — studios must spread content costs across window and time. Overinvestment risk — entertainment slate can overinvest to fill content needs. Sports dynamics — NFL brings millions of subs for 5 months, requires originals to retain them for the remaining 9 months. Tier breaker — originals win long-term for brand equity and differentiation.
>
> **Core Student Decision Framework**
>
> *Business Strategy Layer*: Understand macro shifts (subs vs. profitability). Balance sports investment with entertainment profitability gap. Align budget discipline with creative flexibility. Consensus build: platform value, originals value, talent relations, ad sales, press benefits.
>
> *Creative Alignment*: Don't tell creatives exactly what to do — give guidelines and direction (e.g., "only 4 originals, certain areas to play"). Example: "We're moving away from horror/supernatural, moving toward prestige drama." Balance with talent sensibility: biggest hits break the mold, can't be engineered by research/finance.
>
> *Business Side Skills Required*: Financials must make sense AND convince creatives they align with creative vision. Acknowledge intangibles and qualitative considerations. Weigh opportunities and risks. Use case studies from other streamers to back decisions.
>
> **Simulation Structure**
>
> *Time Horizon*: Change from quarters to years (not quarters).
>
> *Annual Workflow — Order of Play (Year 1 Planning - Q1)*: Portfolio Review (spot cash cows vs. dogs in slate) → Renewal Decisions (cancel low-ROI shows to free budget) → Sidebar (adjust marketing and reserve allocation) → P&L Check (confirm income statement is healthy) → Portfolio Submit (lock in official score).
>
> *Carry-Forward from Previous Year*: Expected 5-10% decline on renewed shows (base case). Marketing assumed flat. Students can pay for research to examine decline scenarios.
>
> *Launch Timing Decision*: "Which quarter would you launch these shows and why?" Strategic consideration: how does timing shape brand equity?
>
> *Budget Constraints*: Total spend budget (e.g., $100 million). Students allocate content spend vs. marketing spend. Minimum thresholds (e.g., $3M marketing minimum for show viability).
>
> **TV Shows / Series Simulation**
>
> *Content Categories*: True Crime (lower ratings, better decay rate, lower CPM, amortizes over 2 years) vs. Non True Crime (higher ratings, higher decay rate, higher CPM, amortizes over 12 months). Different revenue profiles require different strategic positioning.
>
> *Simulation Mechanics — Deck 1: Oxygen / Basic Model*: 100 million annual budget. Allocate 0-100 on content, 0-100 on marketing. Content generates ratings, marketing impacts performance. Repeats fill 24/7 schedule for 52 weeks.
>
> *Deck 2: Bravo / Advanced Model*: Repeat erosion and decay modeling. Decay rate randomized by genre. Students pick slate that nets to budget. Shows available in specific years (production delays).
>
> *Revenue Calculation*: `Revenue = (Rating × CPM × Ad Spots per Hour) × Decay Curve × Hours per Day × 365 Days + Research Cost (optional) + Talent/Risk Adjustments`.
>
> *Performance Variables*: Ratings Band (varies by talent attached, genre, title testing). Decay Curve (genre-dependent decline). Marketing Spend Relationship (~1 percentage point rating increase per $1M, threshold dependent). Research Option (pay for a 1-5 star rating prediction — 1 star = 30% decline, 5 star = 10% growth).
>
> *Renewal & Greenlight Decisions*: Renew existing shows (with expected decline). Greenlight new shows (within budget). Make production choices (some shows available only Year 2+). Students balance risk: pay for research or gamble on instinct.
>
> *Risk & Title Compliance*: Risk assessment for each show (legal, market, creative). Risk = 0 score: take an existing show title without permission (gets sued) — originality matters.
>
> *Show Creation Option*: Students can propose a custom show (title + 3-4 sentence description); AI grades the concept and determines if testing/research is worth paying for.
>
> **Movies Simulation**
>
> *Same Year 1 Practice as TV*: Budget allocation, greenlight decisions, research vs. risk-taking.
>
> *Movie Categories*: Sequels, New Adult IP, Kids IP, Horror or Indie — different profiles with different revenue streams.
>
> *Windowing Strategy (Year 3 Introduction)*: Trade-off decisions — theatrical vs. streaming vs. PVOD vs. rental. Window length impacts box office revenue vs. streaming revenue; earlier streaming window hurts theater but helps streaming. Genre determines licensing/merchandise potential.
>
> *Revenue Streams*: Box office (theatrical window), licensing revenue (VOD, streaming, rental), theme park/merchandise opportunities, Universal licensing deals ("pay yourself" model).
>
> *Constraints*: Limited film slots (e.g., "10 films or 3 films"). Windowing rules apply year 3 onward. Genre determines theme park eligibility.
>
> **Grading & Scoring**
>
> *Evaluation Criteria*: P&L Health (does budget balance, is profitability trending right). Portfolio Strategy (are cash cows protecting losses appropriately). Renewal Logic (smart cancellations vs. emotional attachments). Marketing Discipline (spend threshold met, ROI positive). Creative Alignment (do chosen shows reflect stated strategy). Brand Equity (long-term positioning — originals vs. library balance).
>
> *Randomization*: Performance bands for new shows (talent, genre, testing dependent). Starting-point decay curves randomized. Production availability randomized. Shows can fail for legitimate reasons (talent departure, poor script, etc.).
>
> *Multi-Year Dynamics*: Year-over-year budget adjusts based on performance — good performance means more budget allocation, poor performance means a cut for the following year. Compounds over a 4-year simulation window.
>
> **Key Pedagogical Takeaways**
>
> *What Students Learn*: Financials & strategy integration (how numbers drive creative decisions). Platform dynamics (linear vs. streaming profitability profiles differ). Risk management (when to research vs. when to bet on instinct). Talent relations (financials only work if creatives are aligned). Long-term thinking (short-term wins vs. brand equity). Constraints (real production, talent, and budget limitations).
>
> *Case Study Scaffolding*: Start simple (Oxygen — basic spend allocation) → build complexity (Bravo — decay curves, genres, repeats) → add realism (multi-year — budget pressure, cumulative effects) → introduce windowing (movie distribution strategy).
>
> **Open Simulation Decisions**
>
> Will students manually create show titles or select from a catalog? How frequently does production availability randomize? Should budget constraints shift mid-year (emergency cancellations)? How visible should decay curves be to students (hidden vs. transparent)? Can students see competitors' slates (comparative analysis)? How are tie-breaker decisions (same ROI) handled?

## Original mechanics brief (Zach Schlessel, NBCUniversal — preserved verbatim in spirit)

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
