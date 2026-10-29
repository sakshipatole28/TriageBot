"""Tests for POST /triage: validation, missing key, errors and mocked end-to-end runs."""

from unittest.mock import patch

GOOD_REPORT = "The Android app crashes when I upload an 8 MB profile photo on version 2.3.1."


def test_empty_body_is_rejected(client):
    assert client.post("/triage", json={}).status_code == 422


def test_short_report_is_rejected(client):
    assert client.post("/triage", json={"issue": "app broken"}).status_code == 422


def test_whitespace_only_report_is_rejected(client):
    assert client.post("/triage", json={"issue": " " * 50}).status_code == 422


def test_missing_api_key_returns_503(client, without_keys):
    res = client.post("/triage", json={"issue": GOOD_REPORT})
    assert res.status_code == 503
    assert "API key is not configured" in res.json()["detail"]


def test_triage_with_mocked_workflow(client, with_key):
    """Replace the whole workflow with a fixed answer and check the API response shape."""
    fake_result = {
        "report": "Severity: S2\nPriority: P1\nTeam: Media Team",
        "severity": "S2",
        "priority": "P1",
        "team": "Media Team",
        "related_issues": ["BUG-104"],
        "tools_used": ["search_known_issues"],
    }
    with patch("app.main.run_triage_workflow", return_value=fake_result):
        res = client.post("/triage", json={"issue": GOOD_REPORT})
    assert res.status_code == 200
    data = res.json()
    assert data["severity"] == "S2"
    assert data["related_issues"] == ["BUG-104"]
    assert data["issue"] == GOOD_REPORT


def test_triage_end_to_end_with_fake_agents(client, with_key, fake_team):
    """Run the REAL workflow and REAL tools; only the LLM agents are fake."""
    with patch("app.agents.triage_team.build_triage_team", return_value=fake_team):
        res = client.post("/triage", json={"issue": GOOD_REPORT})
    assert res.status_code == 200
    data = res.json()
    assert data["severity"] == "S2"
    assert data["priority"] == "P1"
    assert data["team"] == "Media Team"
    assert data["related_issues"][0] == "BUG-104"
    assert data["tools_used"] == ["search_known_issues", "get_component_owner"]


def test_agent_error_returns_500_and_hides_key(client, with_key):
    error = RuntimeError("401 Unauthorized for key test-key-not-real-123")
    with patch("app.main.run_triage_workflow", side_effect=error):
        res = client.post("/triage", json={"issue": GOOD_REPORT})
    assert res.status_code == 500
    assert "test-key-not-real-123" not in res.text
    assert "[REDACTED]" in res.json()["detail"]
