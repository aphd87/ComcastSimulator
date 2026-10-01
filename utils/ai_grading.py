"""
AI-graded custom show-concept feedback — optional, BYOK.

Uses Claude Haiku 4.5 via the deploying school's own ANTHROPIC_API_KEY, set
in that Streamlit Cloud deployment's own secrets. No key is ever bundled or
committed to this repo, and there is no shared/fallback key — see
README.md for why (this tool is distributed to schools worldwide, so each
school's own deployment pays for its own usage). If a school hasn't
configured a key, api_key_configured() returns False and the caller should
hide the feature rather than erroring.
"""
from __future__ import annotations
import os
from typing import Literal

import streamlit as st
from pydantic import BaseModel, Field


class ShowConceptGrade(BaseModel):
    originality_score:  int = Field(description="0-25. Is this a genuinely new concept, not a copy of an existing show or a thin reskin?")
    market_fit_score:   int = Field(description="0-25. Does the pitch make a credible case for its stated network/genre/audience?")
    feasibility_score:  int = Field(description="0-25. Is the described scope realistic for a reality/competition/scripted TV budget?")
    presentation_score: int = Field(description="0-25. Is the pitch clear and specific, not vague or generic?")
    feedback:  str       = Field(description="2-3 sentence overall assessment, written directly to the student.")
    strengths: list[str] = Field(description="1-3 short bullet points on what's working in the pitch.")
    risks:     list[str] = Field(description="1-3 short bullet points on what could sink this concept.")
    research_recommended: bool = Field(
        description="True if the concept is risky or uncertain enough (weak feasibility, "
                     "unclear market fit, or genuinely novel/unproven territory) that paying "
                     "for Research on this show once it's in the portfolio would be worth it. "
                     "False if the concept is solid and predictable enough that Research "
                     "would likely just confirm what's already obvious.")
    research_rationale: str = Field(
        description="1 sentence explaining the research_recommended call — what specifically "
                     "makes this concept worth (or not worth) paying to de-risk.")


class MovieConceptGrade(BaseModel):
    """Movies-side parallel to ShowConceptGrade (2026-08-17) -- deliberately
    a separate model/prompt, not a reused TV one: TV's feasibility_score
    grades against "a reality/competition/scripted TV budget" and market_fit
    grades "network/genre/audience," neither of which fits a theatrical
    concept (genre + Concept Type + Source Material, budget/P&A cash out
    upfront with no amortization, distribution-window strategy instead of
    a network slot)."""
    originality_score:  int = Field(description="0-25. Is this a genuinely new concept, not a copy of an existing film or a thin reskin?")
    market_fit_score:   int = Field(description="0-25. Does the pitch make a credible case for its stated genre/concept-type/source-material audience?")
    feasibility_score:  int = Field(description="0-25. Is the described scope realistic for a theatrical release's production budget and P&A?")
    presentation_score: int = Field(description="0-25. Is the pitch clear and specific, not vague or generic?")
    feedback:  str       = Field(description="2-3 sentence overall assessment, written directly to the student.")
    strengths: list[str] = Field(description="1-3 short bullet points on what's working in the pitch.")
    risks:     list[str] = Field(description="1-3 short bullet points on what could sink this concept at the box office.")
    research_recommended: bool = Field(
        description="True if the concept is risky or uncertain enough (weak feasibility, "
                     "unclear market fit, or genuinely novel/unproven territory) that paying "
                     "for the in-game Research / Social Listening feature on this concept "
                     "would be worth it. False if the concept is solid and predictable enough "
                     "that Research would likely just confirm what's already obvious.")
    research_rationale: str = Field(
        description="1 sentence explaining the research_recommended call.")


def grade_movie_concept(title: str, genre: str, concept_type: str, source_material: str,
                         pitch: str) -> MovieConceptGrade | None:
    """Grade a free-form movie pitch with Claude Haiku 4.5 -- Movies-side
    parallel to grade_show_concept above, own model/prompt (see
    MovieConceptGrade's docstring for why). Returns None on any failure
    (missing key, API error) so the caller can show a friendly message
    instead of crashing the page."""
    api_key = _api_key()
    if not api_key:
        return None

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.parse(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": (
                    "You are grading a business-school student's original theatrical movie "
                    "concept pitch for a portfolio-simulation exercise.\n\n"
                    f"Working title: {title}\nGenre: {genre}\nConcept Type: {concept_type}\n"
                    f"Source Material: {source_material}\nPitch:\n{pitch}\n\n"
                    "Score it on originality, market fit, feasibility, and presentation "
                    "(0-25 each), and give brief, constructive feedback aimed at the student. "
                    "If Source Material is an adaptation (Book/Video Game/TV Show), factor in "
                    "whether the pitch actually leverages the source property's built-in "
                    "audience credibly, rather than ignoring it. Also judge whether this "
                    "concept is risky/uncertain enough that it would be worth the student "
                    "paying for the in-game Research feature before committing budget, versus "
                    "solid enough that Research would likely just confirm the obvious."
                ),
            }],
            output_format=MovieConceptGrade,
        )
        return response.parsed_output
    except Exception:
        return None


class ShowPitchIdea(BaseModel):
    show_name: str = Field(description="A punchy, original working title — must not match or "
                             "closely resemble any existing real or well-known TV show.")
    genre:     str = Field(description="Exactly one of: Reality, Competition, Talk, Scripted, "
                             "True Crime, Drama.")
    pitch:     str = Field(description="2-3 sentence pitch describing the concept, hook, and audience.")
    suggested_episodes:     int   = Field(description="Reasonable first-season episode count, 6-20.")
    suggested_ep_cost_k:    int   = Field(description="Reasonable cost per episode in $K, 200-1500 "
                                            "depending on genre/scope (reality cheaper, scripted pricier).")
    suggested_rating:       float = Field(description="Reasonable projected 18-49 rating for an "
                                            "unproven new concept, 0.3-2.5.")
    suggested_svod_appeal:  int   = Field(description="0-100 streaming-conversion appeal score for "
                                            "this concept's genre/hook.")


class ShowPitchBatch(BaseModel):
    pitches: list[ShowPitchIdea] = Field(description="A batch of distinct, original show concepts "
                                           "-- no two should share the same premise or hook.")


def _api_key() -> str | None:
    """This deployment's own key: Streamlit secrets first, then the
    ANTHROPIC_API_KEY environment variable (handy for local runs)."""
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY")
        if key:
            return str(key)
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY") or None


def api_key_configured() -> bool:
    """True if this deployment has its own Anthropic API key configured."""
    return bool(_api_key())


def grade_show_concept(show_name: str, genre: str, pitch: str) -> ShowConceptGrade | None:
    """Grade a free-form show pitch with Claude Haiku 4.5.

    Returns None on any failure (missing key, API error) so the caller can
    show a friendly message instead of crashing the page.
    """
    api_key = _api_key()
    if not api_key:
        return None

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.parse(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": (
                    "You are grading a business-school student's original TV/streaming show "
                    "concept pitch for a portfolio-simulation exercise.\n\n"
                    f"Show name: {show_name}\nGenre: {genre}\nPitch:\n{pitch}\n\n"
                    "Score it on originality, market fit, feasibility, and presentation "
                    "(0-25 each), and give brief, constructive feedback aimed at the student. "
                    "Also judge whether this concept is risky/uncertain enough that it would be "
                    "worth the student paying for the in-game Research feature on this show once "
                    "it's in their portfolio, versus solid enough that Research would likely just "
                    "confirm the obvious."
                ),
            }],
            output_format=ShowConceptGrade,
        )
        return response.parsed_output
    except Exception:
        return None


def generate_show_pitch(network_context: str) -> ShowPitchIdea | None:
    """Generate an original show concept for a student who's stuck on
    ideation — complements grade_show_concept() above, which grades a
    pitch the student already wrote rather than proposing one. Returns
    None on any failure (missing key, API error) so the caller can show a
    friendly message instead of crashing the page.
    """
    api_key = _api_key()
    if not api_key:
        return None

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.parse(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": (
                    f"Propose an original TV show concept for {network_context}, for a "
                    "business-school portfolio-simulation exercise. The concept must be "
                    "genuinely original — do not reuse or lightly reskin any existing real or "
                    "well-known show. Suggest realistic production parameters (episode count, "
                    "cost per episode, projected rating, streaming appeal) a student could "
                    "sanity-check and adjust before greenlighting it."
                ),
            }],
            output_format=ShowPitchIdea,
        )
        return response.parsed_output
    except Exception:
        return None


def generate_show_pitches(network_context: str, n: int = 3) -> list[ShowPitchIdea] | None:
    """Batch version of generate_show_pitch() -- one API call returns n
    distinct concepts instead of one, so a student can browse several
    ideas side by side and pick whichever fits their slate, rather than
    clicking "another pitch" repeatedly and losing the earlier ones.
    Returns None on any failure, same posture as generate_show_pitch()."""
    api_key = _api_key()
    if not api_key:
        return None

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.parse(
            model="claude-haiku-4-5",
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": (
                    f"Propose {n} distinct, original TV show concepts for {network_context}, for a "
                    "business-school portfolio-simulation exercise. Each concept must be genuinely "
                    "original and clearly different from the others — do not reuse or lightly reskin "
                    "any existing real or well-known show, and no two should share the same "
                    "premise or hook. Suggest realistic production parameters (episode count, cost per "
                    "episode, projected rating, streaming appeal) a student could sanity-check and "
                    "adjust before greenlighting it."
                ),
            }],
            output_format=ShowPitchBatch,
        )
        return response.parsed_output.pitches
    except Exception:
        return None


# ── Student pitch review: feedback + estimated metrics (2026-10-01) ──────────
# A student writes their own show pitch; one call grades it (same rubric as
# grade_show_concept) AND estimates the numbers a network's research team
# would put on it, in the same shape as the Acquire a Pitched Show catalog.
# Those estimates become the show's real numbers if the student greenlights
# it from the review card, so a student can't simply claim a hit rating.

class ShowPitchEstimate(BaseModel):
    demo_age:    Literal["18-34", "18-49", "25-54", "35-64"] = Field(
        description="Core age band this show would draw.")
    demo_gender: Literal["Skews Female", "Balanced", "Skews Male"] = Field(
        description="Gender skew of the core audience.")
    demo_reach:  Literal["National (US)", "Global", "Regional (US)"] = Field(
        description="Where the audience is: National (US) for most cable shows, Global only for "
                    "concepts that clearly travel internationally, Regional for local-interest shows.")
    episodes:    int = Field(description="First-season episode count, 6-20.")
    ep_cost_k:   int = Field(description="Production cost per episode in $K, consistent with the genre, "
                                         "scope, and the network's typical cost range given in the prompt.")
    rating:      float = Field(description="Projected 18-49 rating for this unproven concept, 0.3-2.5. "
                                           "Typical new cable show 0.8-1.4; above 1.8 only for an "
                                           "exceptionally strong, well-funded concept.")
    svod_appeal: int = Field(description="0-100: how well the show would attract and keep streaming "
                                         "subscribers (bingeable, serialized, broad appeal score higher).")
    ip_score:    int = Field(description="0-100 franchise/brand value: spinoff, format-sale, and "
                                         "longevity potential. Most new concepts land 35-65.")
    rationale:   str = Field(description="One or two sentences, to the student, explaining the biggest "
                                         "drivers of these estimates (especially rating and cost).")


class ShowPitchReview(ShowConceptGrade):
    estimate: ShowPitchEstimate


# Bounds applied after parsing, so a model slip can never put an absurd
# number into the game economy.
ESTIMATE_BOUNDS = {"episodes": (4, 24), "ep_cost_k": (100, 5000), "rating": (0.3, 2.5),
                   "svod_appeal": (20, 100), "ip_score": (20, 90)}


def clamp_estimate(est: ShowPitchEstimate) -> dict:
    d = est.model_dump()
    for k, (lo, hi) in ESTIMATE_BOUNDS.items():
        d[k] = min(max(d[k], lo), hi)
    d["rating"] = round(float(d["rating"]), 1)
    d["ep_cost_k"] = int(round(d["ep_cost_k"] / 10) * 10)
    return d


def review_show_pitch(show_name: str, genre: str, pitch: str, origin: str, format_source: str,
                      network_display: str, ep_cost_range_k: tuple,
                      calibration: str) -> ShowPitchReview | None:
    """Grade a student's own pitch and estimate its metrics with Claude
    Haiku 4.5. `calibration` is a few catalog pitches rendered as text, so
    estimates land on the same scale as the rest of the game. Returns None
    on any failure (missing key, API error), same posture as the rest of
    this module."""
    api_key = _api_key()
    if not api_key:
        return None

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    origin_line = (f"International Format adapted from {format_source or 'an overseas original'}"
                   if origin == "International Format" else "Domestic Original")
    try:
        response = client.messages.parse(
            model="claude-haiku-4-5",
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": (
                    "You are a TV network's development and research team reviewing a business-school "
                    "student's original show pitch in a portfolio simulation.\n\n"
                    f"Network: {network_display} (typical cost per episode "
                    f"${ep_cost_range_k[0]}K-${ep_cost_range_k[1]}K)\n"
                    f"Show name: {show_name}\nGenre: {genre}\nOrigin: {origin_line}\n"
                    f"Pitch:\n{pitch}\n\n"
                    "1) Grade the pitch on originality, market fit, feasibility, and presentation "
                    "(0-25 each) with brief, constructive feedback written to the student, and judge "
                    "whether paying for in-game Research on it would be worthwhile.\n"
                    "2) Estimate the show's audience and production metrics as a realistic, slightly "
                    "skeptical network researcher would. Weaker, vaguer, or less feasible pitches should "
                    "get lower ratings. Higher ratings generally require higher cost per episode. An "
                    "International Format of a proven overseas hit earns a modestly higher, more "
                    "reliable rating and IP Score than an untested domestic idea.\n\n"
                    "For scale, these are pitches already in the game's marketplace:\n"
                    f"{calibration}"
                ),
            }],
            output_format=ShowPitchReview,
        )
        return response.parsed_output
    except Exception:
        return None
