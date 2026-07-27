# VideoOS — Video Network Portfolio Simulator

A Streamlit business simulation teaching video network portfolio economics through the lens of Comcast/NBCUniversal's networks (TV/Streaming) and Universal Pictures (Movies). Set in 2012, at the start of the cord-cutting shift.

Full design intent, mechanics, and session history: see `DESIGN_NOTES.md`.

## Deployment note — action item for Darden

**This tool is intended for distribution to business schools worldwide as a case-study companion, not run from a single central deployment.** That has one concrete architectural consequence, flagged here for Darden:

- The upcoming AI-graded custom show-concept feature (free-form student pitch → LLM-graded rubric score) calls the Claude API. **Each school's own deployment must configure its own `ANTHROPIC_API_KEY`** in that deployment's Streamlit secrets — the key is never committed to this repo and is never shared across deployments.
- If a school doesn't configure a key, the feature is simply unavailable for that deployment (no crash, no fallback to a shared/central key) — there is no scenario where one school's usage bills another school or the tool's maintainer.
- **Practically: whoever manages each school's Streamlit Cloud deployment needs their own Anthropic API key**, and needs to be told to add it under that deployment's "Secrets" settings. This is worth surfacing to Darden now, before the feature ships, so each participating school's IT/faculty contact knows to provision one.
