"""Builds the instructor session plan for opening Movie Week with the
Universal Pictures simulation (85-minute class, ~60 minutes of play).

Run:  python docs/build_instructor_plan.py
Output: docs/The_Slate_Instructor_Plan_Movies_Week_85min.docx

Reuses the student guides' styling helpers so both documents look the same.
Game facts quoted here (budgets, release-strategy rules, scoring) match the
engine as of 2026-10-01; update them if utils/movie_models.py changes.
"""
from pathlib import Path

from build_student_guides import (new_doc, title_block, para, bullets, steps, callout, table,
                                  page_break, OUT_DIR)


def board(doc, title, columns, rows, widths):
    """A whiteboard layout rendered as a table."""
    para(doc, f"**Board: {title}**")
    table(doc, columns, rows, widths)


def build_plan():
    doc = new_doc(footer_text="The Slate — Media Portfolio Simulation · Instructor Session Plan")
    title_block(doc, "Opening Movie Week",
                "An 85-minute session built around the Universal Pictures simulation, run right after the TV simulation.",
                label="THE SLATE  ·  INSTRUCTOR SESSION PLAN")

    doc.add_heading("Session at a glance", level=1)
    table(doc, ["", ""], [
        ["**Purpose**", "Open the movie module by having students feel the economics of a film slate before the cases: one concentrated, front-loaded bet per film instead of TV's amortized portfolio."],
        ["**Where it sits**", "Directly after the TV / Streaming simulation. Students already know the app, the team setup, and portfolio thinking; this session flips that intuition."],
        ["**Format**", "Teams of ~4 on **one laptop** (Movies has no Follow Along view). Students should use the same team details as in the TV session so both scores sit together on the Leaderboard."],
        ["**Timing**", "**~12 min before → 60 min play → ~13 min debrief.** Five films in 60 minutes is about 12 minutes per film."],
        ["**What counts**", "Each team's **first submitted score** is official. Passing = average graded NPV above $0. Graded NPV is 75% decisions (risk-adjusted) and 25% luck (what each film actually earned)."],
    ], [1.5, 5.0])
    t = doc.tables[-1]
    t.rows[0]._tr.getparent().remove(t.rows[0]._tr)

    doc.add_heading("Which plan to run", level=2)
    para(doc, "All three plans share the same 60-minute play block; they differ in the 12 minutes before and the 13 minutes after.")
    table(doc, ["Plan", "Big idea", "Best when"], [
        ["**C — Portfolio vs. one bet** (recommended)", "TV averages risk across a slate; a movie concentrates it in one decision.", "Opening Movie Week right after TV. It turns last session into the setup for this one."],
        ["**A — Size the bet**", "Capital discipline: budget buys quality, but every dollar is at risk up front.", "You want the debrief to land on NPV, risk, and how much to spend."],
        ["**B — The windowing waterfall**", "Release strategy and cannibalization across theatrical, PVOD, and streaming.", "The week's cases lean on distribution, windows, and the streaming shift."],
    ], [1.9, 2.6, 2.0])
    callout(doc, "tip",
            "A strong combination: **Plan C's opening** (it bridges from TV) with **Plan A's debrief** (it lands on capital "
            "discipline). Save Plan B's waterfall for the next session's distribution case.")

    page_break(doc)
    doc.add_heading("Before class", level=1)
    doc.add_heading("Instructor checklist", level=3)
    bullets(doc, [
        "**Open the app and click through once** the morning of class. If anything looks broken after a recent update, use Streamlit Cloud's **Manage app → Reboot app**.",
        "**Make sure scores will be saved:** `DATABASE_URL` set in the app's Secrets (the Leaderboard should say \"Scores are saved to this deployment's database\"). Without it, a restart erases the class's scores.",
        "**Optional:** `ANTHROPIC_API_KEY` in Secrets turns on AI Pitch Feedback for loglines.",
        "Post the **Movies student guide** (docs/The_Slate_Student_Guide_Movies.docx) with the pre-work below.",
    ])
    doc.add_heading("Student pre-work (10 minutes)", level=3)
    bullets(doc, [
        "Skim the Movies student guide.",
        "**Draft five loglines**, one per film (1–3 sentences each: who it's about, what they want, what's in the way). The app won't let a team Simulate without one, and drafting them in class eats play time.",
        "Use the **same University, School, Class, and Team Name** as in the TV session.",
    ])

    doc.add_heading("The 60-minute play block (all plans)", level=1)
    table(doc, ["Clock", "Where teams should be", "What to watch for"], [
        ["**0–12**", "Register; Film 1 (Years 1–2) greenlit and simulated", "Teams leaving the defaults alone. The default film is an under-funded tentpole and loses money."],
        ["**12–24**", "Film 2", "Budgets far below the genre's typical budget (the gold hint under Production Budget)."],
        ["**24–36**", "Film 3 — **release strategies unlock** (Wide / Platform / Day-and-Date)", "Everyone defaulting to Wide. Ask who considered Platform for a drama or Day-and-Date for a horror film."],
        ["**36–48**", "Film 4", "Pay-1 choices: did anyone take a lower bid on a shorter term, or reject the offers and go back to market?"],
        ["**48–58**", "Film 5, then **View Final Slate**", "Teams about to submit without reading the Score Breakdown."],
        ["**58–60**", "**Submit Official Score**", "Remind them: the first submission is the official one."],
    ], [0.9, 2.6, 3.0])
    doc.add_heading("Questions to ask while circulating", level=3)
    bullets(doc, [
        "\"What's your Capital at Risk on this film, and what has to go right to earn it back?\"",
        "\"Why this budget for this genre? What's the typical budget telling you?\"",
        "\"You chose presale. What are you insuring against?\"",
        "\"Your bull case is great. What does your bear case look like, and could the studio survive it?\"",
        "\"Is your slate diversified, or have you made the same movie three times?\"",
    ])

    page_break(doc)
    doc.add_heading("Plan C — Portfolio vs. one bet  (recommended opener)", level=1)
    para(doc, "**Learning goal:** students articulate why a film slate is managed differently from a TV portfolio: cost timing, the success metric, and how risk is (or isn't) averaged away.")
    doc.add_heading("Before (12 min)", level=2)
    steps(doc, [
        "**(3 min)** Cold-call two teams on last session: \"What kept your TV network alive?\" Listen for amortization, renewing cash cows, and spreading bets across genres.",
        "**(6 min)** Build the board below, column by column, asking the class to fill in the Movies side.",
        "**(3 min)** Close with the question they'll answer by playing: \"If you can't average away risk, how do you manage it?\"",
    ])
    board(doc, "TV vs. Movies", ["", "TV / Streaming (last session)", "Movies (today)"], [
        ["**Bets**", "Many shows at once", "One film per cycle"],
        ["**Cost timing**", "Amortized over 12–36 months", "Paid in full up front, before anyone sees it"],
        ["**Scorecard**", "OCF margin", "Risk-adjusted NPV"],
        ["**Risk**", "Averaged across a slate", "Concentrated in one decision"],
        ["**Biggest lever**", "Renew / cancel", "Budget, P&A, and release strategy"],
    ], [1.3, 2.6, 2.6])
    doc.add_heading("After (13 min)", level=2)
    steps(doc, [
        "**(4 min)** Each team gives a 60-second report: best film, worst film, and one sentence on why.",
        "**(6 min)** Fill the three-pane board below from those reports.",
        "**(3 min)** Bridge to the week: \"Studios manage concentration through slates, co-financing, and windowing. That's what the next cases are about.\"",
    ])
    board(doc, "What decided your slate", ["What we controlled", "What we couldn't", "What we'd tell the CFO"], [
        ["Budget vs. genre norm; P&A; release strategy; financing; diversification",
         "Box-office legs, reviews, word of mouth (25% of the grade is what films actually earned)",
         "One recommendation for next year's slate, with the number behind it"],
    ], [2.2, 2.2, 2.1])
    callout(doc, "key",
            "Listen for the shift from \"spread it out\" (TV) to \"size it right\" (Movies). Teams that won usually funded "
            "fewer, well-matched bets rather than trying to make every film big.")

    page_break(doc)
    doc.add_heading("Plan A — Size the bet", level=1)
    para(doc, "**Learning goal:** capital discipline. Budget buys quality, but every dollar is at risk before release, so the right budget depends on the genre and the downside.")
    doc.add_heading("Before (12 min)", level=2)
    steps(doc, [
        "**(2 min)** Write three real Universal releases on the board (approximate figures): The Super Mario Bros. Movie (2023, ~$100M budget, ~$1.3B worldwide), Oppenheimer (2023, ~$100M, ~$975M), and Five Nights at Freddy's (2023, ~$20M, ~$290M, released day-and-date on Peacock).",
        "**(7 min)** Ask: \"Same studio, same year. Why were these budgets right for these films?\" Fill the board below.",
        "**(3 min)** Set the challenge: \"Today you're the one deciding how much to spend.\"",
    ])
    board(doc, "Sizing the bet", ["Film", "Concept", "Budget", "P&A", "Release", "What could go wrong"], [
        ["Super Mario Bros.", "Animated / game IP", "~$100M", "", "Wide, spring", ""],
        ["Oppenheimer", "Prestige drama", "~$100M", "", "Wide, summer", ""],
        ["Five Nights at Freddy's", "Horror / game IP", "~$20M", "", "Day-and-Date", ""],
    ], [1.3, 1.2, 0.8, 0.6, 1.1, 1.5])
    doc.add_heading("After (13 min)", level=2)
    steps(doc, [
        "**(5 min)** Plot every team on the 2×2 below using the Leaderboard (Score Breakdown shows each part).",
        "**(5 min)** Ask the top-right and bottom-left teams to explain their budgets. Probe: \"Did you fund your films at their genre's typical budget? What happened when you didn't?\"",
        "**(3 min)** Ask: \"Whose best film was luck, and whose was a decision?\" Only 25% of the grade is luck, so a team can have a lucky hit and still score poorly.",
    ])
    board(doc, "Risk-adjusted NPV vs. diversification", ["", "Low diversification", "High diversification"], [
        ["**High NPV**", "One strong recipe, repeated", "Strong, balanced slate"],
        ["**Low NPV**", "Concentrated and wrong", "Spread thin, under-funded"],
    ], [1.3, 2.6, 2.6])

    page_break(doc)
    doc.add_heading("Plan B — The windowing waterfall", level=1)
    para(doc, "**Learning goal:** release strategy and cannibalization. Each window earns money but can steal from the next; the right sequence depends on the film.")
    doc.add_heading("Before (12 min)", level=2)
    steps(doc, [
        "**(5 min)** Draw the waterfall below. Ask where the money is made and where one window steals from another.",
        "**(4 min)** Bring in a real case: in 2020 Universal sent Trolls World Tour straight to premium video on demand, AMC threatened to stop showing Universal films, and the two later agreed to a much shorter theatrical window. Ask: \"Who was right?\"",
        "**(3 min)** Preview the game's three release strategies (Wide, Platform, Day-and-Date), which unlock at Film 3.",
    ])
    board(doc, "The windowing waterfall", ["Theatrical", "PVOD", "Pay-1 streaming", "Pay-2", "Library"], [
        ["~45–90 days; studio keeps ~half of ticket sales", "Premium rental at home; studio keeps most of each rental",
         "Keep on Peacock, license for a fee, or take bids", "A smaller second license", "Long tail; better reviews earn more"],
    ], [1.3, 1.3, 1.4, 1.1, 1.4])
    doc.add_heading("After (13 min)", level=2)
    steps(doc, [
        "**(4 min)** Tally each team's release strategy by genre on the board below.",
        "**(5 min)** Reveal what the game rewards: **Wide** for tentpoles, sci-fi, and animation; **Platform** (about 600 theaters expanding on word of mouth) for drama and awards titles; **Day-and-Date** for horror and comedy, where a Peacock premiere is worth more than the box office given up.",
        "**(4 min)** Pay-1: \"Who took a lower bid because the term was shorter? Who rejected the offers and went back to market, and did it pay?\"",
    ])
    board(doc, "Release strategy by genre (tally)", ["Genre", "Wide", "Platform", "Day-and-Date"], [
        ["Tentpole / Sci-Fi / Animated", "", "", ""],
        ["Drama / Awards", "", "", ""],
        ["Horror / Comedy", "", "", ""],
    ], [2.3, 1.4, 1.4, 1.4])

    page_break(doc)
    doc.add_heading("Quick reference: how the game behaves", level=1)
    table(doc, ["Lever", "What the simulation rewards"], [
        ["**Production budget**", "Close to the genre's typical budget (shown in a gold hint). Far below looks cheap and draws weaker audiences; far above has diminishing returns."],
        ["**P&A**", "Essential (with none, few people show up) but saturating. The sweet spot is roughly 0.5–1× the typical budget."],
        ["**Screens**", "Up to the genre's audience (also hinted). Beyond that, mostly empty seats."],
        ["**Release strategy**", "Wide for tentpoles; Platform for drama and awards; Day-and-Date for horror and comedy (unlocks at Film 3)."],
        ["**Financing**", "Tax incentive almost always helps. Presale is insurance: it pays off for high-variance films (horror) and is a bad trade for likely hits."],
        ["**Pay-1 window**", "Any bid can be accepted; shorter terms return the film to Peacock sooner. One go-back-to-market round per film, usually at lower bids."],
        ["**Scoring**", "Risk-adjusted NPV 45%, capital efficiency 20%, strategic fit 20%, diversification 15%. Graded NPV = 75% decisions + 25% luck."],
        ["**A team that changes nothing**", "Loses money and fails. That's intentional: the defaults are a trap worth discussing."],
    ], [1.7, 4.8])
    callout(doc, "tip",
            "After class, the Leaderboard's **All Submissions — Raw Data** table has a download button for a CSV of every "
            "team's scores, useful for grading or for opening the next session.")

    out = OUT_DIR / "The_Slate_Instructor_Plan_Movies_Week_85min.docx"
    doc.save(out)
    return out


if __name__ == "__main__":
    print("wrote", build_plan())
