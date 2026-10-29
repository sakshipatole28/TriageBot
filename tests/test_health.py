"""Tests for GET /health and GET /."""


def test_health_returns_200_and_agents(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["agents"] == ["Issue Analyst", "Duplicate Investigator", "Triage Lead"]
    assert data["known_issues"] == 10
    assert isinstance(data["llm_configured"], bool)


def test_health_never_leaks_the_key(client, with_key):
    res = client.get("/health")
    assert res.json()["llm_configured"] is True
    assert "test-key-not-real-123" not in res.text


def test_root_serves_html_ui(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "TriageBot" in res.text
    assert client.get("/static/app.js").status_code == 200
