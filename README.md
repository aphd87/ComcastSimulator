# The Slate — Media Portfolio Simulation

A Streamlit business simulation teaching media portfolio economics through the lens of Comcast/NBCUniversal's networks (TV/Streaming) and Universal Pictures (Movies). Each network runs its own real calendar era (2012-2026); Movies runs on production cycles rather than a fixed year.

Full design intent, mechanics, and session history: see `DESIGN_NOTES.md`.

## Deployment note — action item for Darden

**This tool is intended for distribution to business schools worldwide as a case-study companion, not run from a single central deployment.** That has one concrete architectural consequence, flagged here for Darden:

- The upcoming AI-graded custom show-concept feature (free-form student pitch → LLM-graded rubric score) calls the Claude API. **Each school's own deployment must configure its own `ANTHROPIC_API_KEY`** in that deployment's Streamlit secrets — the key is never committed to this repo and is never shared across deployments.
- If a school doesn't configure a key, the feature is simply unavailable for that deployment (no crash, no fallback to a shared/central key) — there is no scenario where one school's usage bills another school or the tool's maintainer.
- **Practically: whoever manages each school's Streamlit Cloud deployment needs their own Anthropic API key**, and needs to be told to add it under that deployment's "Secrets" settings. This is worth surfacing to Darden now, before the feature ships, so each participating school's IT/faculty contact knows to provision one.

## Instructor settings — per-deployment Secrets

Same mechanism as the API key above: any setting an instructor should be able to tailor for their own class lives in that deployment's own Streamlit secrets (Settings → Secrets on Streamlit Cloud, or `.streamlit/secrets.toml` locally — **never commit this file**), not a shared config in the repo.

**`YEARS_PER_LEVEL`** (added 2026-08-03) — how many in-game years each network level (Oxygen/Bravo/Peacock) runs. Defaults to **4** if not set. To change it, add to that deployment's secrets:

```toml
YEARS_PER_LEVEL = 4
```

Any whole number from 2–8 is accepted (out-of-range values are clamped automatically, so a typo can't produce a degenerate or multi-decade level). Every network's calendar era shifts together to keep clean handoffs with no overlap — e.g. at 4 years: Oxygen 2012–2015, Bravo 2016–2019, Peacock 2020–2023. Restart the app (or wait for the next redeploy) after changing this — it's read once when the app starts, not live per page load.
