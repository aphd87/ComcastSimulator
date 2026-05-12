from utils.models import Show

BRAVO_SLATE = [
    Show(1,  "Real Housewives (ATL)",    "Reality",     20, 750,  2.80, 95, 1,  "Bravo"),
    Show(2,  "Real Housewives (NYC)",    "Reality",     16, 720,  2.30, 88, 3,  "Bravo"),
    Show(3,  "Below Deck",              "Reality",     16, 700,  1.90, 82, 4,  "Bravo"),
    Show(4,  "Top Chef",               "Competition",  14, 800,  2.10, 90, 1,  "Bravo"),
    Show(5,  "Vanderpump Rules",        "Reality",     20, 650,  1.60, 75, 1,  "Bravo"),
    Show(6,  "Project Runway",          "Competition",  16, 900,  1.40, 70, 7,  "Bravo"),
    Show(7,  "Shahs of Sunset",         "Reality",     12, 600,  0.90, 55, 3,  "Bravo"),
    Show(8,  "Million Dollar Listing",  "Reality",     10, 550,  1.10, 60, 4,  "Bravo"),
    Show(9,  "Inside the Actors Studio","Talk",        12, 400,  0.70, 65, 2,  "Bravo"),
    Show(10, "Watch What Happens Live", "Talk",        30, 250,  0.80, 72, 1,  "Bravo"),
    Show(11, "The New Normal",          "Scripted",    22, 1200, 0.60, 40, 9,  "Bravo"),
    Show(12, "Gallery Girls",           "Reality",      8, 500,  0.50, 30, 8,  "Bravo"),
    Show(13, "NYC Prep",               "Reality",      8, 480,  0.40, 28, 6,  "Bravo"),
    Show(14, "Southern Charm",         "Reality",     10, 580,  1.20, 62, 3,  "Bravo"),
    Show(15, "Flipping Out",           "Reality",     12, 520,  0.90, 55, 2,  "Bravo"),
    Show(16, "Work of Art",            "Competition",  10, 700,  0.60, 42, 6,  "Bravo"),
    Show(17, "Tabatha Takes Over",     "Reality",     10, 450,  0.80, 50, 5,  "Bravo"),
    Show(18, "Most Eligible Dallas",   "Reality",      8, 480,  0.50, 32, 7,  "Bravo"),
    Show(19, "Newlyweds: First Year",  "Reality",      8, 500,  0.70, 45, 4,  "Bravo"),
    Show(20, "Unscripted Pilot",       "Reality",      6, 420,  0.90, 58, 10, "Bravo"),
]

# 20 shows, $250-320K/ep, 36-month amortization (cheaper, simpler — Level 1)
OXYGEN_SLATE = [
    Show(21, "Snapped",                    "True Crime",  20, 300, 0.80, 70, 1,  "Oxygen", amort_months=36),
    Show(22, "Cold Justice",               "True Crime",  14, 280, 0.90, 68, 3,  "Oxygen", amort_months=36),
    Show(23, "The Disappearance",          "True Crime",   8, 260, 0.60, 52, 5,  "Oxygen", amort_months=36),
    Show(24, "Preachers of LA",            "Reality",     10, 250, 0.50, 44, 7,  "Oxygen", amort_months=36),
    Show(25, "Oxygen True Crime Block",    "True Crime",  16, 270, 0.70, 60, 2,  "Oxygen", amort_months=36),
    Show(26, "Killer Motive",              "True Crime",  12, 290, 0.65, 58, 4,  "Oxygen", amort_months=36),
    Show(27, "Wanted: Dead or Alive",      "True Crime",  10, 260, 0.55, 50, 6,  "Oxygen", amort_months=36),
    Show(28, "Behind Bars",                "True Crime",   8, 240, 0.45, 42, 8,  "Oxygen", amort_months=36),
    Show(29, "Girls Incarcerated",         "Reality",     10, 255, 0.60, 55, 9,  "Oxygen", amort_months=36),
    Show(30, "License to Kill",            "True Crime",  12, 280, 0.70, 62, 1,  "Oxygen", amort_months=36),
    Show(31, "The Accused",                "True Crime",   8, 270, 0.55, 48, 3,  "Oxygen", amort_months=36),
    Show(32, "Forensic Files II",          "True Crime",  20, 230, 0.75, 65, 2,  "Oxygen", amort_months=36),
    Show(33, "Buried in the Backyard",     "True Crime",  10, 260, 0.50, 46, 10, "Oxygen", amort_months=36),
    Show(34, "Over My Dead Body",          "True Crime",   6, 320, 0.65, 58, 5,  "Oxygen", amort_months=36),
    Show(35, "Final Appeal",               "True Crime",   8, 250, 0.45, 40, 7,  "Oxygen", amort_months=36),
    Show(36, "Injustice with Nancy Grace", "True Crime",  12, 275, 0.60, 55, 4,  "Oxygen", amort_months=36),
    Show(37, "Killer Couples",             "True Crime",  16, 240, 0.65, 58, 1,  "Oxygen", amort_months=36),
    Show(38, "A Killing on the Cape",      "True Crime",   6, 300, 0.50, 45, 6,  "Oxygen", amort_months=36),
    Show(39, "Dateline-Style Pilot",       "True Crime",   8, 260, 0.70, 60, 3,  "Oxygen", amort_months=36),
    Show(40, "Crime Scene Kitchen",        "Competition", 12, 290, 0.55, 48, 8,  "Oxygen", amort_months=36),
]

# 10 shows, $1.5M-$3M/ep, 36-month amortization (SVOD originals — Level 3)
PEACOCK_SLATE = [
    Show(41, "Dr. Death",               "Drama",    8,  2500, 1.20, 85, 1, "Peacock", amort_months=36),
    Show(42, "Angelyne",                "Drama",    6,  2000, 0.90, 78, 3, "Peacock", amort_months=36),
    Show(43, "Rutherford Falls",        "Comedy",  10,  1800, 0.75, 70, 2, "Peacock", amort_months=36),
    Show(44, "Brave New World",         "Drama",    9,  3000, 0.85, 80, 1, "Peacock", amort_months=36),
    Show(45, "The Thing About Pam",     "Drama",    6,  2200, 1.10, 82, 4, "Peacock", amort_months=36),
    Show(46, "Kenan",                   "Comedy",  12,  1500, 0.70, 65, 2, "Peacock", amort_months=36),
    Show(47, "Girls5eva",               "Comedy",  10,  1800, 0.80, 72, 3, "Peacock", amort_months=36),
    Show(48, "MacGruber",               "Comedy",   8,  2000, 0.75, 68, 1, "Peacock", amort_months=36),
    Show(49, "The Resort",              "Drama",    8,  2800, 0.95, 80, 6, "Peacock", amort_months=36),
    Show(50, "Poker Face",              "Drama",   10,  2400, 1.05, 83, 5, "Peacock", amort_months=36),
]
