"""Shared test helpers.

FakeAgent replaces a real Agno agent, so tests never call an LLM or the internet.
It records every prompt it receives, so we can check the hand-off between agents.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agents.tools import get_component_owner, search_known_issues
from app.main import app


class FakeAgent:
    """Stand-in for agno.agent.Agent with the same .run(prompt) method."""

    def __init__(self, reply, tool_calls=None):
        self.reply = reply
        self.tool_calls = tool_calls or []
        self.prompts = []

    def run(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(content=self.reply, tools=self.tool_calls, status="COMPLETED")


class FakeInvestigator(FakeAgent):
    """Pretends to be the LLM deciding to call both tools, but runs the REAL tool code."""

    def run(self, prompt):
        self.prompts.append(prompt)
        calls = [
            SimpleNamespace(tool_name="search_known_issues",
                            result=search_known_issues("android crash upload large photo")),
            SimpleNamespace(tool_name="get_component_owner",
                            result=get_component_owner("media-upload")),
        ]
        return SimpleNamespace(content="Likely duplicate of BUG-104. Owner: Media Team.",
                               tools=calls, status="COMPLETED")


LEAD_REPLY = (
    "Severity: S2\n"
    "Priority: P1\n"
    "Team: Media Team\n"
    "Duplicate of: BUG-104\n\n"
    "### Summary\nAndroid app crashes on large photo upload.\n"
    "### Next steps\n1. Link to BUG-104."
)


@pytest.fixture
def fake_team():
    """A full fake team: analyst -> investigator (real tools) -> lead."""
    return {
        "analyst": FakeAgent("Summary: crash on photo upload. Likely component: media-upload"),
        "investigator": FakeInvestigator(None),
        "lead": FakeAgent(LEAD_REPLY),
    }


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def with_key(monkeypatch):
    """Pretend a Groq key is configured (the key is fake and never used)."""
    monkeypatch.setattr("app.config.MODEL_PROVIDER", "groq")
    monkeypatch.setattr("app.config.GROQ_API_KEY", "test-key-not-real-123")


@pytest.fixture
def without_keys(monkeypatch):
    """Pretend no API key is configured at all."""
    monkeypatch.setattr("app.config.GEMINI_API_KEY", "")
    monkeypatch.setattr("app.config.GROQ_API_KEY", "")
