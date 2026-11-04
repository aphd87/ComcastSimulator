"""Builds the instructor board reference for opening Movie Week with the
Universal Pictures simulation (85-minute class, ~60 minutes of play), run the
day after the TV simulation class.

Run:  python docs/build_instructor_plan.py
Output: docs/The_Slate_Instructor_Plan_Movies_Week_85min.docx

Mirrors the format of the TV-day board reference (numbered boards drawn on
the whiteboard, timing, what not to over-explain, key phrases, student
reactions, flow summary) and calls back to that class's boards.
Game facts match the engine as of 2026-11-04 (4 films, must-finish pacing, 15/55/15 split); update if utils/movie_models.py changes.
"""
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.shared import Inches, Pt

from build_student_guides import (new_doc, title_block, para, bullets, steps, callout, table,
                                  page_break, shade, OUT_DIR)


def board(doc, lines):
    """A whiteboard sketch: a shaded, monospace box, drawn line for line."""
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.rows[0].cells[0]
    c.width = Inches(6.5)
    shade(c, "F4F5F7")
    first = True
    for line in lines:
        p = c.paragraphs[0] if first else c.add_paragraph()
        first = False
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        r = p.add_run(line if line else " ")
        r.font.name = "Consolas"
        r.font.size = Pt(9)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def teaches(doc, items):
    para(doc, "**What this teaches:**")
    bullets(doc, items)


def build_plan():
    doc = new_doc(footer_text="The Slate — Universal Pictures Simulation · Instructor Board Reference")
    title_block(doc, "Opening Movie Week",
                "Universal Pictures Simulation — Board Visual Reference. Print & bring to class.",
                label="THE SLATE  ·  INSTRUCTOR BOARD REFERENCE")

    doc.add_heading("The session in one look", level=1)
    table(doc, ["", ""], [
        ["**Where it sits**", "The day after the TV simulation class (Boards 0–4: sports as a loss leader, three hard choices, portfolio architecture). Today opens Movie Week, and every later Movie Week class builds on it (see *Carry it through Movie Week*)."],
        ["**The turn**", "Yesterday students learned to **spread risk across a portfolio**. Today they can't: every film is one concentrated bet, paid up front. And unlike TV, **luck is real** here (25% of each film's grade)."],
        ["**Format**", "Teams of ~4: one Driver plays; teammates can register **Follow Along** on their own laptops to watch live (or crowd around one screen). Same team details as yesterday so both scores sit together on the Leaderboard."],
        ["**Timing**", "**0–15 movie business principles (Boards 0, 1, W) → 15–70 simulation → 70–85 debrief (Boards 2–3).** Four films in ~45 minutes, plus sign-in and a buffer."],
        ["**The rule**", "**Every team finishes all four films**, as well as it can. The first finished slate is official and Redo is off on it, so think, but don't stall."],
        ["**What counts**", "First submitted score is official. Pass = decisions-only (risk-adjusted) NPV averages above $0, so luck can't pass a slate. The score uses graded NPV = 75% decisions + 25% luck (what each film actually earned)."],
    ], [1.5, 5.0])
    t = doc.tables[-1]
    t.rows[0]._tr.getparent().remove(t.rows[0]._tr)

    doc.add_heading("Before class", level=2)
    bullets(doc, [
        "**Instructor:** open the app the morning of class and click through once. If anything errors after an update, Streamlit Cloud → **Manage app → Reboot app**. Confirm the Leaderboard says scores are saved to the database (`DATABASE_URL`), or a restart erases the class's scores.",
        "**Students (10 min pre-work):** **choose your Driver**, skim the Movies student guide, and **draft four loglines**, one per film. Pitches are optional, but they're what the class sees on the Pitch Board; drafting in class eats play time.",
        "**Bring:** two dark dry-erase markers, one bright marker for circling, an eraser, and this printout.",
    ])

    # ── BEFORE PLAY ──────────────────────────────────────────────────────────
    page_break(doc)
    doc.add_heading("BOARD 0: YESTERDAY YOU SPREAD THE RISK. TODAY YOU CAN'T.", level=1)
    para(doc, "(Draw this on a whiteboard, landscape orientation. Divide the board in half.)", muted=True)
    board(doc, [
        "┌────────────────────────────────────────────────────────────────┐",
        "│   YESTERDAY YOU SPREAD THE RISK.  TODAY YOU CAN'T.             │",
        "└────────────────────────────────────────────────────────────────┘",
        "",
        "  TV (YESTERDAY)                   │   MOVIES (TODAY)",
        "                                   │",
        "  10-20 shows at once              │   ONE film per cycle",
        "  Cost amortized 12-36 months      │   Cost paid IN FULL, up front",
        "  Scorecard: OCF margin            │   Scorecard: risk-adjusted NPV",
        "  A flop is one line in the P&L    │   A flop is the whole cycle",
        "  Your MIX smoothed the curve      │   No mix inside a film",
        "                                   │",
        "══════════════════════════════════════════════════════════════════",
        "            THE ONE-CHECK PROBLEM",
        "   You write the whole check before anyone buys a ticket.",
        "   If the film fails, nothing else in the cycle offsets it.",
        "══════════════════════════════════════════════════════════════════",
        "",
        "  ⭕ KEY INSIGHT (circle in bright color):",
        "     \"Yesterday: not your luck, your mix.",
        "      Today: luck is real. How do you SIZE the bet?\"",
    ])
    teaches(doc, [
        "Portfolio thinking still matters, but now it works across four films, not inside one.",
        "Risk shows up as the **bear case**, and it's paid up front.",
        "The skill shifts from \"spread it out\" to \"size it right.\"",
    ])

    doc.add_heading("BOARD 1: YOUR GREENLIGHT — THREE HARD CHOICES", level=1)
    para(doc, "(Landscape, three columns. This is the movie version of yesterday's Board 1.)", muted=True)
    board(doc, [
        "┌──────────────────────────────────────────────────────────────────────┐",
        "│        YOUR GREENLIGHT: THREE HARD CHOICES  ($3.5B studio budget)    │",
        "└──────────────────────────────────────────────────────────────────────┘",
        "",
        "  CHOICE 1               │  CHOICE 2               │  CHOICE 3",
        "  How big a bet?         │  How do we release it?  │  Who carries the risk?",
        "  ───────────────────────┼─────────────────────────┼──────────────────────",
        "  Budget buys quality... │  WIDE: 4,000 screens    │  SELF-FINANCE",
        "  ...up to a point       │   (blockbusters)        │   all upside, all risk",
        "                         │  PLATFORM: 600 screens, │",
        "  $20M tentpole?         │   grows on word of mouth│  PRESALE",
        "  → looks cheap, flops   │   (dramas, awards)      │   guaranteed advance,",
        "                         │  DAY-AND-DATE: theaters │   capped upside",
        "  $300M horror film?     │   + Peacock together    │   = INSURANCE",
        "  → money you never      │   (horror, comedy)      │",
        "    earn back            │                         │  Worth it when the film",
        "                         │  Every window steals a  │  is a coin flip",
        "  Real Q: what's the     │  little from the next   │  (horror), not when it's",
        "  RIGHT size for THIS    │                         │  a likely hit",
        "  genre?                 │  Match strategy to film │",
    ])
    teaches(doc, [
        "Bet sizing is genre-specific (students see each genre's typical budget in the app).",
        "Release strategy is a choice about which audience and which window, not a default.",
        "Financing structure moves risk off your books, at a price.",
    ])

    doc.add_heading("BONUS: WHAT THE BEAR / BASE / BULL BARS MEAN", level=2)
    para(doc, "(Only draw if you have time or students ask.)", muted=True)
    board(doc, [
        "   NPV ($M)",
        "   +300 |                       ███  BULL  (breakout)",
        "   +150 |            ███        ███",
        "      0 |───███──────███────────███──────────────────",
        "    -80 |   ███  BEAR (weak run)       BASE (expected) in the middle",
        "",
        "   Every bar = what the film earns  MINUS  Capital at Risk",
        "   +$10M of budget pushes ALL THREE bars down ~$10M",
        "   ...unless the film earns it back",
    ])

    doc.add_heading("BOARD W: WHERE A FILM'S MONEY COMES FROM", level=1)
    para(doc, "(Principles, minutes 11–15. Students need this map for steps 6–7: Release, PVOD, Pay-1, Pay-2.)", muted=True)
    board(doc, [
        "  THEATRICAL ──► PVOD ──► PAY-1 STREAMING ──► PAY-2 ──► LIBRARY",
        "  (~45-90 days)  (~$20     (~18 months:         (~4 yrs   (long tail;",
        "                 rental)   keep on Peacock,     out)      reviews matter)",
        "                           license, or bid)",
        "",
        "  Theaters keep ~half the ticket.   P&A buys the opening, not the film.",
        "  Every window steals a little from the next.",
        "  By Pay-2 the costs were paid long ago: a Pay-2 fee is almost pure profit.",
        "",
        "  ⭕ \"You write the check at the left edge.",
        "     You get paid all the way to the right.\"",
    ])
    teaches(doc, [
        "Box office is only the first window; NPV adds them all up in today's dollars.",
        "Release choices (Wide, Platform, Day-and-Date, Direct to PVOD / Peacock) decide which windows a film gets.",
        "Class 7 goes deeper on where the money goes; today students just need the map.",
    ])

    doc.add_heading("HOW TO USE THIS IN CLASS (minutes 0–15): MOVIE BUSINESS PRINCIPLES", level=2)
    para(doc, "**While drawing Board 0 (5 min):**")
    steps(doc, [
        "Write the title (30 sec).",
        "Draw the TV half; ask, \"What kept your network alive yesterday?\" Listen for mix, renewals, amortization (1.5 min).",
        "Draw the Movies half while explaining each contrast (1.5 min).",
        "Write the key insight and circle it (30 sec).",
        "Discuss: \"If you can't average the risk away inside a film, what can you do?\" (1 min).",
    ])
    para(doc, "**While drawing Board 1 (6 min):**")
    steps(doc, [
        "Write the title and the three column headers (1 min).",
        "Fill Choice 1 while students react to \"$20M tentpole\" and \"$300M horror film\" (1.5 min).",
        "Fill Choice 2 (1.5 min).",
        "Fill Choice 3 (1.5 min).",
        "Bridge: \"You just made three greenlight calls in your head. Now: where does the money come back from?\" (30 sec).",
    ])
    para(doc, "**While drawing Board W (4 min):**")
    steps(doc, [
        "Draw the five windows left to right; ask, \"Where does a movie make money after the theater?\" (1.5 min).",
        "Add the three one-liners: exhibitor split, P&A, Pay-2 as almost pure profit (1.5 min).",
        "Circle the key line and send them in: \"In the next 55 minutes you'll make these calls four times, with real money. Every team finishes all four films.\" (1 min).",
    ])

    doc.add_heading("WHAT NOT TO OVER-EXPLAIN", level=2)
    bullets(doc, [
        "❌ Don't explain NPV math  ✅ Just say: \"What the film earns, minus what you spent, in today's dollars.\"",
        "❌ Don't explain how the bear case is weighted  ✅ Just say: \"The score cares about your bad outcome, not just your hopeful one.\"",
        "❌ Don't reveal the best budget or P&A for each genre  ✅ Just say: \"The app shows you the typical budget. The rest is your call.\"",
        "❌ Don't explain presale mechanics  ✅ Just say: \"It's insurance. Insurance has a premium.\"",
        "❌ Don't predict outcomes  ✅ Just say: \"You're about to find out.\"",
    ])

    # ── DURING PLAY ──────────────────────────────────────────────────────────
    page_break(doc)
    doc.add_heading("THE SIMULATION (minutes 15–70): EVERY TEAM FINISHES", level=1)
    table(doc, ["Clock", "Where teams should be", "Call it out loud / watch for"], [
        ["**15–19**", "Sign in (same team details as TV day); one Driver, the rest Follow Along; open **Movies**.", "Mismatched team names."],
        ["**19–31**", "**Film 1** (Years 1–2). Wide release only.", "\"Simulate Film 1 by minute 31.\" Teams leaving the defaults alone: the default film is an under-funded tentpole."],
        ["**31–43**", "**Film 2**: release strategies unlock", "\"Simulate Film 2 by minute 43.\" Everyone defaulting to Wide. Who considered Platform for a drama?"],
        ["**43–54**", "**Film 3**", "\"Simulate Film 3 by minute 54.\" Budgets far below the genre's typical budget. Pay-2: who gambled on Keep, and why?"],
        ["**54–64**", "**Film 4** (final film: Pay-2 decided in its own row). The score saves automatically on the last Simulate.", "\"Simulate Film 4 by minute 64.\""],
        ["**64–70**", "**Buffer.** Slow teams finish; finished teams read the Score Breakdown and the 📋 Pitch Board.", "\"Six minutes left.\" Hard stop at 70."],
    ], [0.8, 3.0, 2.7])
    para(doc, "**Where teams stall, and the unstick.** Every step except the film itself is optional, and Simulate greenlights the film and runs its Theatrical Simulation for a team that hasn't:")
    bullets(doc, [
        "**Festivals and Holding Deals:** \"Optional. Bid on one festival film or skip it; don't spend five minutes here.\"",
        "**The pitch:** \"Paste the logline you drafted for homework.\" (Pitches feed Class 8.)",
        "**Release Plan table:** \"Pick Season and Release, click Run Theatrical Simulation, then set PVOD and Pay-1.\"",
        "**Pay-1 shopping:** \"Accept a bid or keep it on Peacock. One re-shop only.\"",
        "Watch progress on a Follow Along screen instead of walking every table.",
    ])
    callout(doc, "tip",
            "**Teams that don't finish:** the Driver signs back in tonight with exactly the same details and picks up where they "
            "left off; the score records when they simulate Film 4. This needs the database connected (check the Leaderboard footer).")
    para(doc, "**Questions to ask while circulating:**")
    bullets(doc, [
        "\"What's your Capital at Risk on this film, and what has to go right to earn it back?\"",
        "\"Why this budget for this genre? What's the typical budget telling you?\"",
        "\"Your bull case is great. What does your bear case look like?\"",
        "\"You chose presale. What are you insuring against?\"",
        "\"Have you made the same movie three times?\"",
    ])
    callout(doc, "tip", "Start sketching Board 2's frame around minute 64 so it's ready when the scores land.")

    # ── AFTER PLAY ───────────────────────────────────────────────────────────
    page_break(doc)
    doc.add_heading("BOARD 2: WHAT ACTUALLY HAPPENED?  (minutes 70–77)", level=1)
    para(doc, "(Fill from the Leaderboard while results populate. Same layout as yesterday's Board 2.)", muted=True)
    board(doc, [
        "┌────────────────────────────────────────────────────────────────┐",
        "│          WHAT ACTUALLY HAPPENED?  (Your 4-film slate)          │",
        "└────────────────────────────────────────────────────────────────┘",
        "",
        "  TOP 3 TEAMS                       BOTTOM 3 TEAMS",
        "  ──────────────────────────────────────────────────────────────",
        "  🥇 Team ______                    🔴 Team ______",
        "     Score: __  Avg NPV: $__M         Score: __  Avg NPV: $__M",
        "     Genres: ______                   Genres: ______",
        "     Release: W / P / D&D             Release: W / P / D&D",
        "     Key move: ______                 Key move: ______",
        "  🥈 ...                            🔴 ...",
        "  🥉 ...                            🔴 ...",
        "",
        "  PATTERN: what separated the top from the bottom?",
        "  ✅ Budgets sized to genre          ❌ Cheap tentpoles / bloated budgets",
        "  ✅ Strategy matched to the film    ❌ Wide release for everything",
        "  ✅ A varied slate                  ❌ The same film four times",
        "",
        "  THE GAP = bet sizing + matching strategy to film + slate variety",
    ])
    para(doc, "**Key teaching moments:**")
    bullets(doc, [
        "Point to the spread: \"Same studio, same budget, same four slots. Look at this gap.\"",
        "Point to the release column: \"Who used Platform or Day-and-Date? What kind of films were they?\"",
        "Ask the bottom teams for their biggest decision, not their unluckiest film.",
        "Open the **📋 Pitch Board** (Leaderboard page): read a top team's logline and a bottom team's aloud, with each film's actual result beside it. Ask: \"Could you have predicted these from the pitch alone?\"",
    ])

    doc.add_heading("BOARD 3: LUCK VS. ARCHITECTURE, REVISITED  (minutes 77–83)", level=1)
    para(doc, "(The callback to the TV day's close: \"Not your luck. Your mix.\")", muted=True)
    board(doc, [
        "┌────────────────────────────────────────────────────────────────┐",
        "│   YESTERDAY: \"NOT YOUR LUCK. YOUR MIX.\"   IS THAT STILL TRUE?   │",
        "└────────────────────────────────────────────────────────────────┘",
        "",
        "  IN TV                              IN FILM",
        "  Luck averaged out across a slate   Luck is 25% of each film's grade",
        "  Mix = the whole game               Mix = across 4 films only",
        "",
        "  ══════════════════════════════════════════════════════════════",
        "   THE REAL ANSWER: you can't remove luck in film.",
        "   You SIZE the bet so one bad roll can't sink the studio.",
        "  ══════════════════════════════════════════════════════════════",
        "",
        "   Tools you had:   right-sized budget   →  smaller bear case",
        "                    presale              →  insurance",
        "                    platform / D&D       →  match the audience",
        "                    a varied slate       →  luck evens out over 4",
    ])
    para(doc, "**Ask:** \"Whose best film was luck, and whose was a decision?\" Then: \"Did anyone size a bet so a flop couldn't hurt them?\"")

    # ── FLOW / PHRASES / REACTIONS ───────────────────────────────────────────
    page_break(doc)
    doc.add_heading("FLOW SUMMARY", level=1)
    table(doc, ["Time", "Board", "What happens"], [
        ["0–5", "Board 0", "TV vs. movies: the one-check problem"],
        ["5–11", "Board 1", "Three greenlight choices"],
        ["11–15", "Board W", "Where a film's money comes from (windows)"],
        ["15–64", "—", "Sign in; four films on the clock (31 / 43 / 54 / 64)"],
        ["64–70", "Board 2 (frame)", "Buffer; sketch Board 2 while teams finish"],
        ["70–77", "Board 2", "Fill top / bottom 3 from the Leaderboard; name the pattern"],
        ["77–83", "Board 3", "Luck vs. architecture, revisited"],
        ["83–85", "Close", "Bridge to Class 7: \"Where does the money actually go?\""],
    ], [1.0, 1.4, 4.1])

    doc.add_heading("KEY PHRASES TO USE", level=2)
    bullets(doc, [
        "After Board 0: \"Yesterday the mix saved you. Today there's no mix inside a film.\"",
        "After Board 2: \"Same studio, same four slots. The gap is how you sized and released your bets.\"",
        "After Board 3: \"In TV, architecture beats luck. In film, architecture decides how much luck can hurt you.\"",
    ])

    doc.add_heading("COMMON STUDENT REACTIONS (& how to handle)", level=2)
    table(doc, ["They say", "You say"], [
        ["\"Our films were just unlucky.\"", "\"25% was luck. Look at your bear case: did you size the bet so luck couldn't sink you?\""],
        ["\"Bigger budgets should always win.\"", "\"Budget buys quality up to the genre's norm. Past that, you're paying for something the audience doesn't reward.\""],
        ["\"Why not always go wide?\"", "\"Every window steals from the next. A drama on 4,000 screens is mostly empty seats.\""],
        ["\"Presale gave away our hit.\"", "\"That's what insurance costs. Was the film a coin flip or a likely hit?\""],
        ["\"We did the same as yesterday and lost.\"", "\"Yesterday's skill was mixing. Today's is sizing. Same discipline, different lever.\""],
    ], [2.2, 4.3])

    doc.add_heading("THE CLOSE (what to say)", level=2)
    para(doc, "\"Yesterday you learned that a network wins on portfolio architecture, not individual hits. Today you found the "
              "limit of that idea: a film is one bet, written as one check, before anyone buys a ticket. Studios live with "
              "that by sizing bets, sharing risk, and choosing how a film reaches its audience. That's what the rest of this "
              "week's cases are about.\"")

    doc.add_heading("BOARD 1.5: THE REAL SKILL (creative alignment)", level=2)
    para(doc, "(Optional, mirrors yesterday's Board 1.5.)", muted=True)
    board(doc, [
        "  FILMMAKERS THINK:                 │  YOU THINK:",
        "  Can I make it great?              │  What's the right budget for this genre?",
        "  Will it play on 4,000 screens?    │  Which release reaches its audience?",
        "  Is the studio behind me?          │  What's our bear case?",
        "",
        "  The genius move: right-sizing the bet PROTECTS the film.",
        "  A $300M horror film has to be a blockbuster to survive.",
        "  A $25M one only has to be good.",
    ])

    page_break(doc)
    doc.add_heading("CARRY IT THROUGH MOVIE WEEK", level=1)
    para(doc, "Today is the shared experience every later movie class points back to. Capture these before you leave the room:")
    bullets(doc, [
        "**Download the Leaderboard CSV** (All Submissions — Raw Data): every team's NPV, score parts and deal nets.",
        "**Screenshot the 📋 Pitch Board**: every team's loglines with how each film did. Class 8 starts from \"yesterday's pitches.\"",
        "**Note two films by name**: one sized right, one over-sized or under-funded. Use them as live examples all week.",
    ])
    table(doc, ["Later class", "Call back to the simulation"], [
        ["**Class 7: Behind the Box Office** (Donna Langley's capital)", "Opens with \"What were we actually managing?\" Use Board W and each team's Capital at Risk: the 2.5–3× break-even multiple is the bear case they felt. Pay-1 / Pay-2 is the \"why not put everything on Peacock?\" discussion. Close: \"Would you run your Universal slate differently now?\""],
        ["**Horror vs. tentpole expected value**", "Who sized a horror film right, and who funded a cheap tentpole? Budget buys quality only up to the genre's norm."],
        ["**Production incentives**", "Tax Incentive financing almost always helped in the sim. Why does the real arms race keep escalating?"],
        ["**Class 8: Movie Data** (UVA dashboard, pitches)", "Start from the Pitch Board loglines; students rebuild one with data and compare it to how the sim film did."],
    ], [2.2, 4.3])

    # ── APPENDIX ─────────────────────────────────────────────────────────────
    page_break(doc)
    doc.add_heading("APPENDIX: ALTERNATE OPENERS", level=1)
    para(doc, "Swap one of these in for Boards 0–1 if the week's first case calls for it.")
    doc.add_heading("Alternate A — \"Size the bet\" (three real Universal releases)", level=2)
    board(doc, [
        "  FILM (2023, approx.)        CONCEPT            BUDGET   RELEASE",
        "  Super Mario Bros. Movie     Animated / game IP ~$100M   Wide, spring  (~$1.3B worldwide)",
        "  Oppenheimer                 Prestige drama     ~$100M   Wide, summer  (~$975M)",
        "  Five Nights at Freddy's     Horror / game IP   ~$20M    Day-and-Date on Peacock (~$290M)",
        "",
        "  Ask: \"Same studio, same year. Why were these budgets right for these films?\"",
    ])
    doc.add_heading("Alternate B — \"The windowing waterfall\"", level=2)
    para(doc, "Open Board W with the real case: in 2020 Universal sent Trolls World Tour straight to "
              "premium video on demand, AMC threatened to stop showing Universal films, and the two later agreed to a much "
              "shorter theatrical window. Ask: \"Who was right?\"")

    doc.add_heading("QUICK REFERENCE: HOW THE GAME BEHAVES", level=2)
    table(doc, ["Lever", "What the simulation rewards"], [
        ["**Production budget**", "Close to the genre's typical budget (gold hint). Far below looks cheap; far above has diminishing returns."],
        ["**P&A**", "Essential but saturating; the sweet spot is roughly 0.5–1× the typical budget."],
        ["**Screens**", "Up to the genre's audience (also hinted). Beyond that, mostly empty seats."],
        ["**Release strategy**", "Wide for tentpoles; Platform for drama and awards; Day-and-Date for horror and comedy (from Film 2)."],
        ["**Financing**", "Tax incentive almost always helps. Presale is insurance: pays off for high-variance films, a bad trade for likely hits."],
        ["**Pay-1 window**", "Any bid can be accepted; shorter terms return the film to Peacock sooner. One go-back-to-market round per film."],
        ["**Pay-2 window**", "Decided the cycle after release and locked: 🎲 Keep (catalog gamble, better with good reviews) vs a streamer's sure fee."],
        ["**Festivals**", "Bid against the analysts' break-even; prices sit near value, some cheap, some rich. Lowballing rarely wins; winning at or above break-even is the winner's curse. Hot films draw more rivals."],
        ["**Partnerships**", "Sign once, then renew each cycle (pricier after a hit) or let go. Fees count in the score."],
        ["**Library IP / Lead Actor**", "Reviving a Universal title lifts the opening (once per slate, legacy fee). A held actor's bonus applies only when cast."],
        ["**Direct releases**", "Direct to PVOD beats Wide for smaller comedy / horror / drama films, not tentpoles. Direct to Peacock never recoups in cash: Acquisition needs heavy P&A and suits animation / sci-fi; Retention pays on a light spend for horror / comedy. Debate: product or platform marketing expense?"],
        ["**Attractions**", "After a park-genre hit: Build / Pass a Universal Studios attraction. Roughly break-even on average; better for sequels and family films."],
        ["**Scoring**", "Risk-adjusted NPV 45%, capital efficiency 20%, strategic fit 20%, diversification 15%. Graded NPV = 75% decisions + 25% luck, plus each cycle's deals (fees, festival films, attractions)."],
        ["**A team that changes nothing**", "Always fails (score in the high 30s): passing depends on decisions alone. A good contrast for Board 2."],
    ], [1.7, 4.8])
    callout(doc, "tip",
            "After class, the Leaderboard's **All Submissions — Raw Data** table has a download button for a CSV of every "
            "team's scores.")

    out = OUT_DIR / "The_Slate_Instructor_Plan_Movies_Week_85min.docx"
    doc.save(out)
    return out


def build_tv_plan():
    """TV / Streaming day: Peacock level, all four years in one 85-minute class,
    anchored on Independent Study Case A (The Cost of Culture: Content
    Amortization at NBCUniversal). Rebuilds the Class 5 'NBCU Simulation'
    boards (originally Oxygen True Crime, Year 1 in class, Years 2-4 async)
    for Peacock, keeping their names, key insights and phrases."""
    doc = new_doc(footer_text="The Slate — Peacock (SVOD) Simulation · Instructor Board Reference")
    title_block(doc, "Streaming TV Day: Peacock + Case A",
                "Peacock Simulation — Board Visual Reference. Print & bring to class.",
                label="THE SLATE  ·  INSTRUCTOR BOARD REFERENCE")

    doc.add_heading("The session in one look", level=1)
    table(doc, ["", ""], [
        ["**Where it sits**", "Case A (*The Cost of Culture: Content Amortization at NBCUniversal*) is the pre-read. Today students run Peacock 2020–2023 themselves. The next class opens Movie Week with the Universal Pictures simulation, which calls back to today's boards."],
        ["**The case question**", "Rebecca Kovacs has two days to recommend Peacock's next slate. Sports bring subscribers in; what keeps them? Originals, library content, or neither? Today every team runs that audit with its own money."],
        ["**Format**", "Teams of ~4: one Driver plays; teammates register **Follow Along** on their own laptops. Use team details students will reuse for Movies, so both scores sit together on the Leaderboard."],
        ["**Timing**", "**0–10 frame & sign-in → 10–56 four years on the clock → 56–68 buffer → 68–85 debrief boards.**"],
        ["**The rule**", "**Every team finishes all four years**, as well as it can. The first finished run is the official score and Redo is off on it, so think, but don't stall."],
        ["**What counts**", "Pass = level OCF margin at or above **10%**. Score: OCF margin 35%, show ROI 25%, genre mix 15%, marketing efficiency 15%, renewal quality 10%."],
    ], [1.5, 5.0])
    t = doc.tables[-1]
    t.rows[0]._tr.getparent().remove(t.rows[0]._tr)

    doc.add_heading("Before class", level=2)
    bullets(doc, [
        "**Instructor, the morning of class:** open the app and click through once. Confirm the Leaderboard footer says **\"Scores are saved to this deployment's database.\"** A ⚠️ \"local disk\" warning means a restart would wipe scores *and* unfinished games. If anything errors after an update: **⋮ → Reboot app**.",
        "**Pre-draw Boards 0 and 1** before students arrive. There are only five minutes of framing today; the boards carry it.",
        "**Students:** read Case A; skim the TV / Streaming student guide (Peacock sections: Financing, Renewal, Sports Rights, Film Licensing); **choose your Driver before class**.",
        "**Bring:** two dark dry-erase markers, one bright marker for circling, an eraser, this printout, and the class clock slide on the projector.",
    ])

    # ── BEFORE PLAY ──────────────────────────────────────────────────────────
    page_break(doc)
    doc.add_heading("BOARD 0: SPORTS IS A LOSS LEADER", level=1)
    para(doc, "(Pre-drawn. Landscape, board divided in half. Point to it while you frame Kovacs's question.)", muted=True)
    board(doc, [
        "┌──────────────────────────────────────────────────────────────┐",
        "│           SPORTS IS A LOSS LEADER                            │",
        "└──────────────────────────────────────────────────────────────┘",
        "",
        "  NFL SEASON (5 months)             │   OFF-SEASON (9 months)",
        "  📈 Millions of subs arrive        │   📉 Subs bleed out",
        "  Churn = LOW (games every week)    │   Churn = HIGH (no football)",
        "  Revenue = GREAT...                │   Where's the content?",
        "  ...but the rights fee is bigger   │   Only originals & library hold them",
        "                                    │",
        "══════════════════════════════════════════════════════════════════",
        "              THE 9-MONTH GAP PROBLEM",
        "   Only originals can hold subs through the off-season.",
        "   If originals fail, you lose the season's subscriber gains.",
        "   (Case A: the NBA deal, $2.45B a year, is the same problem.)",
        "══════════════════════════════════════════════════════════════════",
        "",
        "  ⭕ KEY INSIGHT (circle in bright color):",
        "     \"You're already playing with ONE HAND TIED BEHIND YOUR BACK.\"",
        "     Sports is the hook. Your slate is what keeps them.",
    ])
    teaches(doc, [
        "In the sim, sports revenue only sticks in proportion to what you spend on originals that year (licensed films count half).",
        "About 45% of a season's sports revenue returns the next year as retained subscribers, fading after that. The payoff is later.",
        "Everything you greenlight or renew must answer: \"Does this hold subscribers through the 9-month off-season?\"",
        "This is Zach Schlessel's (NBCU) framing: sports brings a 5-month spike, and originals must carry the other 9 months.",
    ])

    doc.add_heading("BOARD 1: YOUR BUDGET — THREE HARD CHOICES", level=1)
    para(doc, "(Pre-drawn. Three columns. ~$150M, one budget for everything.)", muted=True)
    board(doc, [
        "┌────────────────────────────────────────────────────────────────────────┐",
        "│        PEACOCK: THREE HARD CHOICES  (~$150M, one budget)               │",
        "└────────────────────────────────────────────────────────────────────────┘",
        "",
        "  CHOICE 1               │  CHOICE 2               │  CHOICE 3",
        "  Which sports, if any?  │  Keep or cut originals? │  License library films?",
        "  ───────────────────────┼─────────────────────────┼──────────────────────",
        "  NFL, Premier League,   │  Sunk-cost trap:        │  3 finished films/year",
        "  Olympics = premium,    │  \"I paid $50M!\"         │  Sealed bid vs a rival",
        "  slow payback           │  WRONG.                 │  True value HIDDEN",
        "                         │                         │",
        "  College FB, Pro Golf,  │  Real Q: revenue > cost │  Clues: critics +",
        "  Women's Soccer =       │  NEXT year?             │  box office",
        "  cheap, keep more fans  │  (cancelling still      │",
        "                         │   costs 25% of the year)│  Cheap retention...",
        "  A win = 4-7 yr lock    │  Cut originals and the  │  ...or winner's curse",
        "                         │  sports fans leave too  │",
    ])
    teaches(doc, [
        "Choice 1 is Case A's NBA problem at classroom scale: a multi-year commitment everything else has to carry.",
        "Choice 2 is forward-looking, not sunk cost, and on Peacock a cut original also takes its subscribers with it.",
        "Choice 3 is Case A's library question: cheaper retention than originals, if you don't overpay.",
    ])

    doc.add_heading("HOW TO USE THIS IN CLASS (minutes 0–10)", level=2)
    steps(doc, [
        "Point at Board 0: \"Kovacs has two days. Sports brings them in. What keeps them?\" Take two answers and write them in a corner; Board 3 reads them back (1.5 min).",
        "Point at Board 1, one column each: \"These are her three choices. In a minute they're yours, with real money\" (2 min).",
        "Rules (1 min): first finished run is official, Redo is off, **everyone finishes all four years**, watch the clock slide.",
        "Sign in (minutes 5–10): one Driver per team, everyone else Follow Along. Team details typed exactly the same. Open **Peacock**.",
    ])

    doc.add_heading("WHAT NOT TO OVER-EXPLAIN", level=2)
    bullets(doc, [
        "❌ Don't explain the retention formula  ✅ Just say: \"Sports fans stay if your shows give them a reason.\"",
        "❌ Don't reveal which sports package pays back  ✅ Just say: \"Premium rights pay off slowly. Read the tier table.\"",
        "❌ Don't explain ASU 2019-02 now  ✅ Save it for Board 4. Just say: \"Costs get recognized when the viewing comes in.\"",
        "❌ Don't predict outcomes  ✅ Just say: \"You're about to find out.\"",
    ])

    # ── DURING PLAY ──────────────────────────────────────────────────────────
    page_break(doc)
    doc.add_heading("THE PLAY BLOCK (minutes 10–68): EVERY TEAM FINISHES", level=1)
    table(doc, ["Clock", "Where teams should be", "Call it out loud"], [
        ["**10–22**", "**Year 1 (2020), guided together.** Walk the page one section at a time: Financing → Renewal → Sports → Films → Greenlight → Simulate. Everyone simulates together.", "\"Before you simulate: name your tentpole and your steady show.\""],
        ["**22–34**", "Year 2 (2021), teams on their own", "\"Simulate Year 2 by minute 34.\""],
        ["**34–45**", "Year 3 (2022)", "\"Simulate Year 3 by minute 45.\""],
        ["**45–56**", "Year 4 (2023). The score saves automatically on the last Simulate.", "\"Simulate Year 4 by minute 56.\""],
        ["**56–68**", "**Buffer.** Slow teams catch up; finished teams read the Score Breakdown and start the memo.", "\"Ten minutes left to play.\" Hard stop at 68."],
    ], [0.8, 3.6, 2.1])
    para(doc, "**Where teams stall, and the unstick:**")
    bullets(doc, [
        "**Sports bids:** debating the NFL for five minutes. \"Pick one package or none and move on. You can bid again next year.\"",
        "**Film bids:** \"Bid what the critics score and box office justify, or pass. Zero is a bid.\"",
        "**Building their own show:** writing the pitch takes time. \"Acquire from the pitch marketplace this year.\"",
        "**Renewal:** leaving every show on Renew. \"Look at projected OCF. What are you keeping, and why?\"",
        "Watch progress on a Follow Along screen instead of walking every table.",
    ])
    para(doc, "**Questions to ask while circulating:**")
    bullets(doc, [
        "\"Which of your shows is holding the sports fans?\"",
        "\"What did that sports package cost you this year, and when does it pay back?\"",
        "\"Why that bid for that film? What do the critics score and box office tell you?\"",
        "\"You're keeping a money-loser. Is that franchise value, or sunk cost?\"",
    ])
    callout(doc, "tip",
            "**Teams that don't finish:** the Driver signs back in tonight with exactly the same details and picks up where they "
            "left off; the score records when they simulate Year 4. This needs the database connected (check the Leaderboard footer).")
    callout(doc, "tip", "Start sketching Board 2's frame around minute 60 so it's ready when the scores land.")

    # ── AFTER PLAY ───────────────────────────────────────────────────────────
    page_break(doc)
    doc.add_heading("BOARD 2: WHAT ACTUALLY HAPPENED?  (minutes 68–73)", level=1)
    para(doc, "(Fill from the Leaderboard; its instructor notables and CSV show sports, film and cancellation nets.)", muted=True)
    board(doc, [
        "┌────────────────────────────────────────────────────────────────┐",
        "│        WHAT ACTUALLY HAPPENED?  (Peacock 2020–2023)            │",
        "└────────────────────────────────────────────────────────────────┘",
        "",
        "  TOP 3 TEAMS                       BOTTOM 3 TEAMS",
        "  ──────────────────────────────────────────────────────────────",
        "  🥇 Team ______                    🔴 Team ______",
        "     OCF margin: __%                  OCF margin: __%",
        "     Sports: ______                   Sports: ______",
        "     Films licensed: __               Films licensed: __",
        "     Key move: ______                 Key move: ______",
        "  🥈 ...                            🔴 ...",
        "  🥉 ...                            🔴 ...",
        "",
        "  PATTERN: what separated the top from the bottom?",
        "  ✅ Cut losers, kept retainers      ❌ Renewed everything",
        "  ✅ Right-sized sports bet          ❌ Premium rights, thin slate",
        "  ✅ Value films at a fair bid       ❌ Overpaid (winner's curse)",
        "",
        "  THE GAP = renewal rigor + sports sizing + bidding discipline",
    ])
    para(doc, "**Ask the bottom teams for their biggest decision, not their unluckiest show.** "
              "Benchmarks if useful: renewing everything lands around 5–8% (fails); cutting losers and licensing value films reaches ~10%; "
              "adding a niche sports package and tight marketing reaches ~12–13%. The NFL is a slow-payback bet (deeply negative in Year 1, recovering by Year 4).")

    doc.add_heading("BOARD 3: SPORTS VS. ENTERTAINMENT REVISITED  (minutes 73–78)", level=1)
    para(doc, "(Read back the two answers you wrote in the corner at minute 2.)", muted=True)
    board(doc, [
        "┌────────────────────────────────────────────────────────────────┐",
        "│   REMEMBER THE OPENING QUESTION?  WHO WAS THE REAL LOSS LEADER? │",
        "└────────────────────────────────────────────────────────────────┘",
        "",
        "  SPORTS                            ENTERTAINMENT (originals + library)",
        "  Locked in for 4-7 years           Decided every year",
        "  Brings subscribers in fast        Keeps them after the season",
        "  Loses money in its season         Costs money every year",
        "  YOU CAN'T UNDO IT                 YOU CONTROL THIS",
        "",
        "  ══════════════════════════════════════════════════════════════",
        "   THE REAL ANSWER: they're BOTH loss leaders. BOTH necessary.",
        "   The question wasn't \"which one?\"",
        "   It was \"which loss can you afford, and does one pay for the other?\"",
        "  ══════════════════════════════════════════════════════════════",
    ])
    para(doc, "**Ask:** \"Did your originals keep the sports fans? How do you know?\" Then: \"Who licensed films, and did they earn their fee?\"")

    doc.add_heading("BOARD 4: WHEN YOU PAY vs. WHEN IT HITS EARNINGS  (minutes 78–83)", level=1)
    para(doc, "(Case A's core idea, and the old revenue-curve board's successor. Two true views of the same show: "
              "the simulation tracks when you pay; Case A's accounting rules decide when the cost hits earnings.)", muted=True)
    board(doc, [
        "  TENTPOLE ORIGINAL (binge drop)       PROCEDURAL / LIBRARY",
        "  Cost ↑                               Cost ↑",
        "      | ██                                 | ▇▇▇▇▇▇▇▇▇▇▇▇",
        "      | ██ ▇                               |",
        "      |_██_▇_▁_▁______                     |_____________________",
        "        M1 M2 M3 ...                         Y1     Y2     Y3",
        "  ASU 2019-02: cost follows VIEWING,   Steady viewing → steady charge",
        "  so it lands in the launch period",
        "",
        "  THE SIMULATION = WHEN YOU PAY: a show's cost leaves evenly,",
        "  month by month, over its contract (36 months on Peacock)",
        "  CASE A = WHEN IT HITS EARNINGS: cost follows viewing, so a",
        "  binge tentpole books most of its cost at launch",
        "",
        "  ⭕ \"Same show, same total cost. Your cash says one thing;",
        "     your earnings report says another. A CFO manages both.\"",
        "",
        "  ALSO NOT IN THE SIM:  weekly vs binge release (+48% short-term",
        "  retention, CMU)  ·  premium NBC/Bravo content after Versant",
    ])
    para(doc, "**Ask:** \"Which of your shows was a tentpole? Redraw your Year 1 margin with its cost front-loaded.\" "
              "Then: \"If you released it weekly instead of all at once, what happens to both curves?\"")

    doc.add_heading("THE CLOSE + MEMO  (minutes 83–85)", level=2)
    para(doc, "\"You came in thinking entertainment builds the brand and sports is just acquisition. You found they're mirrors: "
              "sports brings them in, your slate decides whether they stay, and the accounting decides *when* it shows up on the P&L. "
              "Not your luck. Your mix. Next class you run Universal Pictures, where there's no mix inside a film: every film is one check, written up front.\"")
    callout(doc, "key",
            "**Memo (150 words, due tonight):** To Kovacs's planning review: recommend Peacock's content mix (originals, library, "
            "sports) and support it with **one number from your simulation**. Name one thing the simulation didn't capture that "
            "would change your recommendation.")

    # ── FLOW / PHRASES / REACTIONS ───────────────────────────────────────────
    page_break(doc)
    doc.add_heading("FLOW SUMMARY", level=1)
    table(doc, ["Time", "Board", "What happens"], [
        ["0–5", "Boards 0–1", "Kovacs's question; three hard choices; rules"],
        ["5–10", "—", "Sign in; open Peacock"],
        ["10–22", "—", "Year 1 guided together"],
        ["22–56", "—", "Years 2–4 on the clock (34 / 45 / 56)"],
        ["56–68", "Board 2 (frame)", "Buffer; sketch Board 2 while teams finish"],
        ["68–73", "Board 2", "Top / bottom 3; name the pattern"],
        ["73–78", "Board 3", "Sports vs. entertainment revisited"],
        ["78–83", "Board 4", "When you pay vs. when it hits earnings"],
        ["83–85", "Close", "Memo prompt; bridge to Movie Week"],
    ], [1.0, 1.4, 4.1])

    doc.add_heading("KEY PHRASES TO USE", level=2)
    bullets(doc, [
        "Board 0: \"You're already playing with one hand tied behind your back.\"",
        "Board 2: \"Same platform, same budget. The gap is what you kept, what you cut, and what you bid.\"",
        "Board 3: \"You didn't answer wrong at the start. You just didn't have data. They're both loss leaders; the genius is making one pay for the other.\"",
        "Board 4: \"The sim shows when you pay. The accounting shows when it hits earnings. You have to manage both.\"",
        "Close: \"Not your luck. Your mix.\" (Movie day opens by testing that line.)",
    ])

    doc.add_heading("COMMON STUDENT REACTIONS (& how to handle)", level=2)
    table(doc, ["They say", "You say"], [
        ["\"Our sports deal was a disaster.\"", "\"In its season, every package loses money. Did your slate keep the fans long enough for the payback?\""],
        ["\"We lost the film auction.\"", "\"Did the winner earn their fee? Winning isn't the goal; winning at the right price is.\""],
        ["\"We couldn't cut that show, it cost so much.\"", "\"That's the sunk-cost trap. The question is next year's revenue against next year's cost.\""],
        ["\"Our shows were just unlucky.\"", "\"Look at Board 2. Luck would be random. The top teams share a pattern.\""],
        ["\"Peacock's target is too easy.\"", "\"Doing nothing misses it. And ask why a streamer gets a 10% bar when Bravo gets 15%.\""],
        ["\"The sim's accounting isn't realistic.\"", "\"The sim tracks when the money leaves; that's real. Board 4 is when it hits earnings. What would front-loading do to your Year 1?\""],
    ], [2.2, 4.3])

    doc.add_heading("BOARD 1.5: THE REAL SKILL (creative alignment)", level=2)
    para(doc, "(Optional, if a team argues for keeping a beloved money-loser.)", muted=True)
    board(doc, [
        "  CREATIVES THINK:                  │  YOU THINK:",
        "  Will this excite audiences?       │  Will it hold subscribers after the season?",
        "  Can I make it great?              │  Front-loaded or steady cost?",
        "  Does the platform trust me?       │  Is it worth more than a library film?",
        "",
        "  The genius move: your financial discipline protects their creative freedom.",
    ])

    # ── APPENDIX ─────────────────────────────────────────────────────────────
    page_break(doc)
    doc.add_heading("QUICK REFERENCE: HOW PEACOCK BEHAVES", level=1)
    table(doc, ["Lever", "What the simulation does"], [
        ["**Revenue**", "Subscriptions instead of cable fees: each active original's rating adds subscribers, and the base grows 45% a year. Cancelling a show loses its subscribers."],
        ["**Sports (6 packages)**", "NFL, Premier League, Summer Olympics (premium); College Football Conference, Pro Golf Tour, Women's Pro Soccer (value / emerging; Women's Soccer +20% a year held). Sealed bids against six rivals; a win locks 4–7 years. Every package loses money in its own season; ~45% of a season's revenue returns next year as retained subscribers, fading after."],
        ["**Retention link**", "Sports revenue sticks in proportion to that year's originals spend; licensed films count half their fee."],
        ["**Film licensing**", "Three finished films a year, sealed bid against one rival streamer; true value hidden until signed; fee paid every year of the term. Well-reviewed films retain better."],
        ["**Renewal**", "Every show defaults to Renew. Cancelling still charges 25% of that year's cost."],
        ["**Amortization**", "Peacock shows paid evenly over 36 months: when you pay (Board 4 adds when it hits earnings under ASU 2019-02)."],
        ["**Greenlighting**", "Up to 3 new shows a year (acquire or build; building needs a pitch). Rival-interest pitches cost 25% more."],
        ["**Benchmarks (4 years)**", "Renew everything ≈ 5–8% (fails). Cut losers + value films ≈ 10%. + niche sports, tight marketing ≈ 12–13%. NFL deeply negative in Year 1, recovering by Year 4."],
        ["**Marketing**", "Zach's model: the budget is split evenly across active shows; each $1M a show gets lifts its ad revenue ~1%; about $3M per show is the viability threshold. A 20-show slate can't reach it within the $24M cap: the pressure to cut shows is intended."],
        ["**Official run**", "First finished run counts; Redo, Restart and network switching are locked once a year is simulated. Practice runs are only recorded if the official run didn't pass."],
    ], [1.7, 4.8])
    callout(doc, "tip", "After class, the Leaderboard's **All Submissions — Raw Data** table downloads a CSV of every team's scores, "
                        "including sports, film and cancellation nets.")

    out = OUT_DIR / "The_Slate_Instructor_Plan_Peacock_Case_A_85min.docx"
    doc.save(out)
    return out


if __name__ == "__main__":
    print("wrote", build_tv_plan())
    print("wrote", build_plan())
