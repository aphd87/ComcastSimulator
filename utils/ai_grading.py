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


def api_key_configured() -> bool:
    """True if this deployment has its own Anthropic API key configured."""
    try:
        return bool(st.secrets.get("ANTHROPIC_API_KEY"))
    except Exception:
        return False


def grade_show_concept(show_name: str, genre: str, pitch: str) -> ShowConceptGrade | None:
    """Grade a free-form show pitch with Claude Haiku 4.5.

    Returns None on any failure (missing key, API error) so the caller can
    show a friendly message instead of crashing the page.
    """
    api_key = st.secrets.get("ANTHROPIC_API_KEY") if api_key_configured() else None
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
