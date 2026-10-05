"""Builds the instructor board reference for opening Movie Week with the
Universal Pictures simulation (85-minute class, ~60 minutes of play), run the
day after the TV simulation class.

Run:  python docs/build_instructor_plan.py
Output: docs/The_Slate_Instructor_Plan_Movies_Week_85min.docx

Mirrors the format of the TV-day board reference (numbered boards drawn on
the whiteboard, timing, what not to over-explain, key phrases, student
reactions, flow summary) and calls back to that class's boards.
Game facts match the engine as of 2026-10-01; update if utils/movie_models.py changes.
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
        ["**Where it sits**", "The day after the TV simulation class (Boards 0–4: sports as a loss leader, three hard choices, portfolio architecture). Today opens Movie Week."],
        ["**The turn**", "Yesterday students learned to **spread risk across a portfolio**. Today they can't: every film is one concentrated bet, paid up front. And unlike TV, **luck is real** here (25% of each film's grade)."],
        ["**Format**", "Teams of ~4 on **one laptop** (Movies has no Follow Along view). Same team details as yesterday so both scores sit together on the Leaderboard."],
        ["**Timing**", "**0–12 boards → 12–72 play → 72–85 debrief boards.** Five films in 60 minutes ≈ 12 minutes per film."],
        ["**What counts**", "First submitted score is official. Pass = decisions-only (risk-adjusted) NPV averages above $0, so luck can't pass a slate. The score uses graded NPV = 75% decisions + 25% luck (what each film actually earned)."],
    ], [1.5, 5.0])
    t = doc.tables[-1]
    t.rows[0]._tr.getparent().remove(t.rows[0]._tr)

    doc.add_heading("Before class", level=2)
    bullets(doc, [
        "**Instructor:** open the app the morning of class and click through once. If anything errors after an update, Streamlit Cloud → **Manage app → Reboot app**. Confirm the Leaderboard says scores are saved to the database (`DATABASE_URL`), or a restart erases the class's scores.",
        "**Students (10 min pre-work):** skim the Movies student guide and **draft five loglines**, one per film. Simulate stays locked without one; drafting in class eats play time.",
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
        "  20-40 shows at once              │   ONE film per cycle",
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

    doc.add_heading("HOW TO USE THIS IN CLASS (minutes 0–12)", level=2)
    para(doc, "**While drawing Board 0 (6 min):**")
    steps(doc, [
        "Write the title (30 sec).",
        "Draw the TV half; ask, \"What kept your network alive yesterday?\" Listen for mix, renewals, amortization (1.5 min).",
        "Draw the Movies half while explaining each contrast (1.5 min).",
        "Write the key insight and circle it (30 sec).",
        "Discuss: \"If you can't average the risk away inside a film, what can you do?\" (2 min).",
    ])
    para(doc, "**While drawing Board 1 (6 min):**")
    steps(doc, [
        "Write the title and the three column headers (1 min).",
        "Fill Choice 1 while students react to \"$20M tentpole\" and \"$300M horror film\" (1.5 min).",
        "Fill Choice 2 (1.5 min).",
        "Fill Choice 3 (1.5 min).",
        "Close: \"You just made three greenlight calls in your head. In 60 minutes you'll make fifteen with real money.\" (30 sec).",
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
    doc.add_heading("THE 60-MINUTE PLAY BLOCK (minutes 12–72)", level=1)
    table(doc, ["Clock", "Where teams should be", "What to watch for"], [
        ["**12–24**", "Register; Film 1 (Years 1–2)", "Teams leaving the defaults alone. The default film is an under-funded tentpole."],
        ["**24–36**", "Film 2 — **release strategies unlock**", "Everyone defaulting to Wide. Who considered Platform for a drama, or Day-and-Date for horror?"],
        ["**36–48**", "Film 3", "Budgets far below the genre's typical budget (gold hint under Production Budget). Pay-2 calls: who gambled on Keep, and why?"],
        ["**48–60**", "Film 4 (final film: Pay-2 decided in its own row)", "Pay-1: anyone take a lower bid on a shorter term? Anyone go back to market?"],
        ["**60–70**", "**View Final Slate**", "Teams submitting without reading the Score Breakdown."],
        ["**70–72**", "**Submit Official Score**", "First submission is official."],
    ], [0.9, 2.5, 3.1])
    para(doc, "**Questions to ask while circulating:**")
    bullets(doc, [
        "\"What's your Capital at Risk on this film, and what has to go right to earn it back?\"",
        "\"Why this budget for this genre? What's the typical budget telling you?\"",
        "\"Your bull case is great. What does your bear case look like?\"",
        "\"You chose presale. What are you insuring against?\"",
        "\"Have you made the same movie three times?\"",
    ])
    callout(doc, "tip", "Start sketching Board 2's frame around minute 65 so it's ready when the scores land.")

    # ── AFTER PLAY ───────────────────────────────────────────────────────────
    page_break(doc)
    doc.add_heading("BOARD 2: WHAT ACTUALLY HAPPENED?  (minutes 72–78)", level=1)
    para(doc, "(Fill from the Leaderboard while results populate. Same layout as yesterday's Board 2.)", muted=True)
    board(doc, [
        "┌────────────────────────────────────────────────────────────────┐",
        "│          WHAT ACTUALLY HAPPENED?  (Your 5-film slate)          │",
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
        "  ✅ A varied slate                  ❌ The same film five times",
        "",
        "  THE GAP = bet sizing + matching strategy to film + slate variety",
    ])
    para(doc, "**Key teaching moments:**")
    bullets(doc, [
        "Point to the spread: \"Same studio, same budget, same five slots. Look at this gap.\"",
        "Point to the release column: \"Who used Platform or Day-and-Date? What kind of films were they?\"",
        "Ask the bottom teams for their biggest decision, not their unluckiest film.",
        "Open the **📋 Pitch Board** (Leaderboard page): read a top team's logline and a bottom team's aloud, with each film's actual result beside it. Ask: \"Could you have predicted these from the pitch alone?\"",
    ])

    doc.add_heading("BOARD 3: LUCK VS. ARCHITECTURE, REVISITED  (minutes 78–83)", level=1)
    para(doc, "(The callback to yesterday's Board 4 close: \"Not your luck. Your mix.\")", muted=True)
    board(doc, [
        "┌────────────────────────────────────────────────────────────────┐",
        "│   YESTERDAY: \"NOT YOUR LUCK. YOUR MIX.\"   IS THAT STILL TRUE?   │",
        "└────────────────────────────────────────────────────────────────┘",
        "",
        "  IN TV                              IN FILM",
        "  Luck averaged out across 30 shows  Luck is 25% of each film's grade",
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
        "                    a varied slate       →  luck evens out over 5",
    ])
    para(doc, "**Ask:** \"Whose best film was luck, and whose was a decision?\" Then: \"Did anyone size a bet so a flop couldn't hurt them?\"")

    doc.add_heading("OPTIONAL BOARD 4: THE WINDOWING WATERFALL  (if 5+ minutes remain)", level=1)
    board(doc, [
        "  THEATRICAL ──► PVOD ──► PAY-1 STREAMING ──► PAY-2 ──► LIBRARY",
        "  (~45-90 days)  (rental)  (keep on Peacock,    (smaller  (long tail;",
        "                           license, or bid)      license)  reviews matter)",
        "",
        "  Tally on the board:        WIDE   PLATFORM   DAY-AND-DATE",
        "    Tentpole / Sci-Fi / Anim  ___     ___         ___",
        "    Drama / Awards            ___     ___         ___",
        "    Horror / Comedy           ___     ___         ___",
    ])
    para(doc, "Reveal what the game rewards: **Wide** for tentpoles, sci-fi, and animation; **Platform** for drama and awards; **Day-and-Date** for horror and comedy. Then ask who took a lower Pay-1 bid for a shorter term, and why.")

    # ── FLOW / PHRASES / REACTIONS ───────────────────────────────────────────
    page_break(doc)
    doc.add_heading("FLOW SUMMARY", level=1)
    table(doc, ["Time", "Board", "What happens"], [
        ["0–6", "Board 0", "Yesterday vs. today: the one-check problem"],
        ["6–12", "Board 1", "Three greenlight choices"],
        ["12–72", "—", "Play four films; circulate with the questions above"],
        ["65–72", "Board 2 (frame)", "Sketch the frame while teams finish"],
        ["72–78", "Board 2", "Fill top / bottom 3 from the Leaderboard; name the pattern"],
        ["78–83", "Board 3", "Luck vs. architecture, revisited"],
        ["(optional)", "Board 4", "Windowing tally, if time allows"],
        ["83–85", "Close", "Bridge to the week's cases"],
    ], [1.0, 1.4, 4.1])

    doc.add_heading("KEY PHRASES TO USE", level=2)
    bullets(doc, [
        "After Board 0: \"Yesterday the mix saved you. Today there's no mix inside a film.\"",
        "After Board 2: \"Same studio, same five slots. The gap is how you sized and released your bets.\"",
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
    para(doc, "Draw Board 4's waterfall first. Then the real case: in 2020 Universal sent Trolls World Tour straight to "
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
        ["**Scoring**", "Risk-adjusted NPV 45%, capital efficiency 20%, strategic fit 20%, diversification 15%. Graded NPV = 75% decisions + 25% luck."],
        ["**A team that changes nothing**", "Always fails (score in the high 30s): passing depends on decisions alone. A good contrast for Board 2."],
    ], [1.7, 4.8])
    callout(doc, "tip",
            "After class, the Leaderboard's **All Submissions — Raw Data** table has a download button for a CSV of every "
            "team's scores.")

    out = OUT_DIR / "The_Slate_Instructor_Plan_Movies_Week_85min.docx"
    doc.save(out)
    return out


if __name__ == "__main__":
    print("wrote", build_plan())
