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

**Final state**: 35 tests passing (28 on `utils/movie_models.py`, 4 AppTest-based on `pages/movies.py`'s Greenlight phase — see the AppTest limitation above for why not more), full app import-checks cleanly, local server starts with no traceback.

**Still genuinely open:**
1. The actual interactive click-through (Release → Results → Complete → Submit) is still only verified by direct unit tests on the underlying functions plus a manual code read — not by driving the real Streamlit widgets, for the AppTest reason documented above. **A human browser pass is the one thing nobody has done across this entire multi-session build** — please do this before trusting Day 2 in front of students.
2. Tailwind's actual rendering is still unconfirmed for the same reason (no browser access this whole effort).

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
