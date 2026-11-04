// Class clock slides for The Slate: TV (Peacock) day and Movie day, 85-minute classes.
// Run: npm install pptxgenjs (anywhere), then NODE_PATH=<that node_modules> node docs/build_class_clock_slides.js <out.pptx>.
// apply_theme.js comes from the pptx skill; edit the require path if it moves.
const pptxgen = require("pptxgenjs");
const { applyTheme } = require("C:/Users/apalo/.claude/skills/synced/2c577515-6a24-4cae-9755-9c1a8d5c64fa_060fcb80-080b-448a-8b96-f66c7893af5d/pptx/scripts/apply_theme.js");

const THEME = {
  name: "The Slate Clock",
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "14181F", lt1: "FFFFFF", dk2: "232A36", lt2: "C9D1DC",
    accent1: "E8A33D",  // amber: guided / principles
    accent2: "3F7FB0",  // steel blue: play
    accent3: "D0573F",  // rust: hard stop
    accent4: "5B6577",  // slate grey: setup / buffer
    accent5: "3FA37C",  // green: debrief
    accent6: "8C96A8",
    hlink: "3F7FB0", folHlink: "8C96A8",
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "The Slate: Class Clocks";
const C = pres.SchemeColor;

pres.defineSlideMaster({
  title: "CLOCK",
  background: { color: C.text1 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.4, w: 12.1, h: 0.8,
        fontSize: 38, bold: true, color: C.background1, align: "left", valign: "top", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 1.2, w: 12.1, h: 0.5,
        fontSize: 20, color: C.accent1, valign: "top", margin: 0 }, text: "" } },
  ],
});

const X0 = 0.6, W = 12.13, TOTAL = 85;
const mx = (m) => X0 + (W * m) / TOTAL;

function clockSlide({ section, title, subtitle, segments, ticks, tiles, rules, notes }) {
  pres.addSection({ title: section });
  const s = pres.addSlide({ masterName: "CLOCK", sectionTitle: section });
  s.addText(title, { placeholder: "title" });
  s.addText(subtitle, { placeholder: "body" });

  // Timeline bar
  const barY = 2.25, barH = 0.75;
  segments.forEach((g, i) => {
    const x = mx(g.from), w = mx(g.to) - mx(g.from);
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: barY, w: w - 0.03, h: barH, fill: { color: g.color }, line: { color: g.color },
      objectName: `segment-${i}`,
    });
    const narrow = w < 0.95;
    s.addText(g.label, {
      x: narrow ? x - 0.4 : x, y: narrow ? barY - 0.42 : barY, w: narrow ? w + 0.8 : w - 0.03,
      h: narrow ? 0.36 : barH, fontSize: narrow ? 12 : 15, bold: !narrow,
      color: narrow ? C.background2 : C.background1, align: "center", valign: "middle",
      margin: 0, isTextBox: true, objectName: `segment-label-${i}`,
    });
  });
  // Minute ticks
  ticks.forEach((m) => {
    s.addText(`${m}`, {
      x: mx(m) - 0.3, y: barY + barH + 0.05, w: 0.6, h: 0.3, fontSize: 12,
      color: C.background2, align: "center", margin: 0, isTextBox: true, objectName: `tick-${m}`,
    });
  });

  // Checkpoint tiles
  const tileY = 3.65, tileH = 1.45, gap = 0.3;
  const tileW = (W - gap * (tiles.length - 1)) / tiles.length;
  tiles.forEach((t, i) => {
    const x = X0 + i * (tileW + gap);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x, y: tileY, w: tileW, h: tileH, rectRadius: 0.12,
      fill: { color: C.text2 }, line: { color: t.stop ? C.accent3 : C.text2, width: t.stop ? 2 : 0.75 },
      objectName: `tile-${i}`,
    });
    s.addText(t.time, {
      x, y: tileY + 0.12, w: tileW, h: 0.8, fontSize: 44, bold: true,
      color: t.stop ? C.accent3 : C.accent1, align: "center", valign: "middle", margin: 0,
      isTextBox: true, objectName: `tile-time-${i}`,
    });
    s.addText(t.label, {
      x: x + 0.1, y: tileY + 0.9, w: tileW - 0.2, h: 0.45, fontSize: 15,
      color: C.background1, align: "center", valign: "middle", margin: 0,
      isTextBox: true, objectName: `tile-label-${i}`,
    });
  });

  // Rules
  const ruleY = 5.45, ruleH = 1.45, rGap = 0.3;
  const ruleW = (W - rGap * (rules.length - 1)) / rules.length;
  rules.forEach((r, i) => {
    const x = X0 + i * (ruleW + rGap);
    s.addText([
      { text: r.head, options: { bold: true, fontSize: 17, color: C.accent1, breakLine: true } },
      { text: r.body, options: { fontSize: 15, color: C.background1 } },
    ], {
      x, y: ruleY, w: ruleW, h: ruleH, valign: "top", margin: 0, paraSpaceAfter: 4,
      isTextBox: true, objectName: `rule-${i}`,
    });
  });

  s.addNotes(notes);
}

const GREY = "5B6577", AMBER = "E8A33D", BLUE = "3F7FB0", BLUE2 = "2F6893", BUF = "7A6A4F", GREEN = "3FA37C";

clockSlide({
  section: "TV Day",
  title: "Today's clock: Peacock, 2020–2023",
  subtitle: "Every team finishes all four years.",
  segments: [
    { from: 0, to: 10, label: "Frame + sign in", color: GREY },
    { from: 10, to: 22, label: "Year 1 together", color: AMBER },
    { from: 22, to: 34, label: "Year 2", color: BLUE },
    { from: 34, to: 45, label: "Year 3", color: BLUE2 },
    { from: 45, to: 56, label: "Year 4", color: BLUE },
    { from: 56, to: 68, label: "Buffer", color: BUF },
    { from: 68, to: 85, label: "Debrief", color: GREEN },
  ],
  ticks: [0, 10, 22, 34, 45, 56, 68, 85],
  tiles: [
    { time: ":22", label: "Year 1 simulated (together)" },
    { time: ":34", label: "Year 2 simulated" },
    { time: ":45", label: "Year 3 simulated" },
    { time: ":56", label: "Year 4 simulated" },
    { time: ":68", label: "Hard stop for play", stop: true },
  ],
  rules: [
    { head: "Your first finished run counts", body: "Redo is off on it. Think, but don't stall: waiting won't tell you more than simulating will." },
    { head: "Stuck? Decide and move", body: "A sports bid of zero is a choice. No time to write a pitch? Acquire one from the marketplace." },
    { head: "Not done by :68?", body: "Your Driver signs back in tonight with exactly the same team details and finishes Year 4." },
  ],
  notes: "Call the checkpoints out loud: Year 2 by 34, Year 3 by 45, Year 4 by 56. Ten-minute warning at 58. "
       + "Buffer 56-68: slow teams catch up, finished teams read the Score Breakdown and start the memo. Debrief 68-85: Boards 2, 3, 4.",
});

clockSlide({
  section: "Movie Day",
  title: "Today's clock: Universal Pictures, four films",
  subtitle: "Every team finishes all four films.",
  segments: [
    { from: 0, to: 15, label: "Movie business principles", color: AMBER },
    { from: 15, to: 19, label: "Sign in", color: GREY },
    { from: 19, to: 31, label: "Film 1", color: BLUE },
    { from: 31, to: 43, label: "Film 2", color: BLUE2 },
    { from: 43, to: 54, label: "Film 3", color: BLUE },
    { from: 54, to: 64, label: "Film 4", color: BLUE2 },
    { from: 64, to: 70, label: "Buffer", color: BUF },
    { from: 70, to: 85, label: "Debrief", color: GREEN },
  ],
  ticks: [0, 15, 19, 31, 43, 54, 64, 70, 85],
  tiles: [
    { time: ":31", label: "Film 1 simulated" },
    { time: ":43", label: "Film 2 simulated" },
    { time: ":54", label: "Film 3 simulated" },
    { time: ":64", label: "Film 4 simulated" },
    { time: ":70", label: "Hard stop for play", stop: true },
  ],
  rules: [
    { head: "Your first finished slate counts", body: "Redo is off on it. Think, but don't stall: one film every 12 minutes." },
    { head: "Short on time? Skip the extras", body: "Every step but the film is optional. Skip festivals and holds; paste the logline you drafted." },
    { head: "Not done by :70?", body: "Your Driver signs back in tonight with exactly the same team details and finishes Film 4." },
  ],
  notes: "Principles 0-15: Board 0 (one-check problem), Board 1 (three greenlight choices), Board W (windows). "
       + "Call the checkpoints out loud: Film 1 by 31, Film 2 by 43, Film 3 by 54, Film 4 by 64. "
       + "Buffer 64-70. Debrief 70-85: Boards 2 and 3, then bridge to Class 7.",
});

(async () => {
  const out = process.argv[2];
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  console.log("wrote", out);
})();
