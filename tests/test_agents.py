"""Tests for the agent team, the hand-offs between agents, and the tools."""

from app.agents.tools import get_component_owner, search_known_issues
from app.agents.triage_team import AGENT_NAMES, build_triage_team, extract_field, run_triage_workflow


def test_build_team_has_three_agents_and_tools():
    # A fake key is fine: building agents does not contact the LLM.
    team = build_triage_team(api_key="fake-key")
    assert [agent.name for agent in team.values()] == AGENT_NAMES

    tool_names = [tool.__name__ for tool in team["investigator"].tools]
    assert tool_names == ["search_known_issues", "get_component_owner"]
    assert not team["analyst"].tools and not team["lead"].tools


def test_workflow_hands_output_from_agent_to_agent(fake_team):
    result = run_triage_workflow("Android app crashes uploading an 8 MB photo", team=fake_team)

    # Agent 1 got the raw report.
    assert "8 MB photo" in fake_team["analyst"].prompts[0]
    # Agent 2 got Agent 1's analysis.
    assert "Likely component: media-upload" in fake_team["investigator"].prompts[0]
    # Agent 3 got both earlier outputs.
    lead_prompt = fake_team["lead"].prompts[0]
    assert "Likely component: media-upload" in lead_prompt
    assert "Likely duplicate of BUG-104" in lead_prompt

    assert result["severity"] == "S2"
    assert result["team"] == "Media Team"


def test_search_finds_the_right_duplicate():
    result = search_known_issues("android app crash when uploading large profile photo")
    assert result.startswith("[BUG-104]")


def test_search_with_no_match_says_new_issue():
    assert "NEW issue" in search_known_issues("printer jammed quantum banana")


def test_search_with_empty_query():
    assert "No query provided" in search_known_issues("   ")


def test_component_owner_known_and_unknown():
    assert "Media Team" in get_component_owner("Media-Upload")
    assert "S1:" in get_component_owner("media-upload")
    assert "Unknown component" in get_component_owner("billing")


def test_extract_field_handles_markdown_bold():
    report = "**Severity:** S1\nPriority: P0\nTeam: Academics Team"
    assert extract_field(report, "Severity") == "S1"
    assert extract_field(report, "Priority") == "P0"
    assert extract_field(report, "Team") == "Academics Team"
    assert extract_field(report, "Duplicate of") is None
