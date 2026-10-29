"""Pydantic models: they validate what comes in and describe what goes out."""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class TriageRequest(BaseModel):
    """A new bug report that a user wants triaged."""

    issue: str = Field(
        ...,
        min_length=20,
        max_length=4000,
        description="The bug report text: what happened, where, and how to reproduce it.",
        examples=[
            "The Android app crashes when I upload a profile photo bigger than 5 MB. "
            "Happens every time on version 2.3.1."
        ],
    )

    @field_validator("issue")
    @classmethod
    def must_have_real_text(cls, value: str) -> str:
        """Reject reports that are only spaces, and strip extra whitespace."""
        trimmed = value.strip()
        if len(trimmed) < 20:
            raise ValueError("Bug report must contain at least 20 non-whitespace characters.")
        return trimmed


class TriageResponse(BaseModel):
    """The final triage decision produced by the agent team."""

    status: str = "success"
    issue: str = Field(..., description="The bug report that was submitted.")
    report: str = Field(..., description="Final triage report written by the Triage Lead (markdown).")
    severity: Optional[str] = Field(default=None, description="S1 (critical) to S4 (minor).")
    priority: Optional[str] = Field(default=None, description="P0 (fix now) to P3 (backlog).")
    team: Optional[str] = Field(default=None, description="Team the bug should be assigned to.")
    related_issues: List[str] = Field(default_factory=list, description="Past issue IDs the tools found.")
    tools_used: List[str] = Field(default_factory=list, description="Tools the Investigator agent called.")


class HealthResponse(BaseModel):
    """Answer of GET /health. Never contains secrets."""

    status: str = "healthy"
    app_name: str
    llm_configured: bool
    model: str
    agents: List[str]
    known_issues: int
