"""Tools (plain Python functions) that the Duplicate Investigator agent can call.

Agno reads each function's name, type hints and docstring and sends them to
the LLM as a "function calling" schema. The LLM decides when to call a tool,
Agno runs the Python function, and the result goes back to the LLM.
"""

import re
from typing import List, Tuple

from app.data import SEVERITY_SLA, load_components, load_known_issues

# Common words that say nothing about which bug it is.
STOPWORDS = {
    "the", "and", "for", "with", "when", "this", "that", "from", "have", "has",
    "not", "but", "are", "was", "were", "can", "app", "every", "time", "after",
    "then", "into", "our", "your", "you", "they", "them", "its", "any", "all",
    "get", "got", "does", "did", "just", "also", "very", "some", "there",
}

# A past issue must score at least this much to count as related.
MIN_SCORE = 4


def _words(text: str) -> set:
    """Split text into lowercase words, dropping short and common words."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if len(t) > 2 and t not in STOPWORDS}


def score_issue(query: str, issue: dict) -> int:
    """Give a past issue a relevance score for the query (higher = more similar)."""
    query_lower = query.lower()
    query_words = _words(query)
    score = 0
    # Keyword hits are the strongest signal. \b makes "mb" not match "number".
    for keyword in issue.get("keywords", []):
        if re.search(rf"\b{re.escape(keyword.lower())}\b", query_lower):
            score += 3
    score += 2 * len(query_words & _words(issue.get("title", "")))
    score += len(query_words & _words(issue.get("description", "")))
    return score


def find_similar_issues(query: str, limit: int = 3) -> List[Tuple[int, dict]]:
    """Return up to `limit` (score, issue) pairs, best match first."""
    scored = [(score_issue(query, issue), issue) for issue in load_known_issues()]
    scored = [pair for pair in scored if pair[0] >= MIN_SCORE]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[:limit]


def search_known_issues(query: str) -> str:
    """Search the CampusConnect issue tracker for past bugs similar to the query.

    Use this to find possible duplicates before creating a new ticket.

    Args:
        query: Short description of the bug, e.g. "android crash upload large photo".

    Returns:
        Matching past issues with ID, title, component, status, severity and resolution,
        or a message saying nothing similar was found.
    """
    if not query or not query.strip():
        return "No query provided. Describe the bug in a few keywords."

    matches = find_similar_issues(query)
    if not matches:
        return f"No similar past issues found for: '{query}'. This looks like a NEW issue."

    lines = []
    for score, issue in matches:
        lines.append(
            f"[{issue['id']}] {issue['title']}\n"
            f"  component: {issue['component']} | status: {issue['status']} | "
            f"severity: {issue['severity']} | match score: {score}\n"
            f"  details: {issue['description']}\n"
            f"  resolution: {issue['resolution']}"
        )
    return "\n".join(lines)


def get_component_owner(component: str) -> str:
    """Look up which team owns a CampusConnect component and its response time rules.

    Args:
        component: Component name, one of: auth, media-upload, notifications,
            timetable, search, web-ui, attendance.

    Returns:
        The owning team, its chat channel, and the SLA for each severity level.
    """
    components = load_components()
    name = (component or "").strip().lower()
    if name not in components:
        return f"Unknown component '{component}'. Valid components: {', '.join(sorted(components))}."

    info = components[name]
    sla = "\n".join(f"  {level}: {rule}" for level, rule in SEVERITY_SLA.items())
    return (
        f"Component '{name}' is owned by {info['team']} (contact: {info['contact']}).\n"
        f"Scope: {info['description']}\nSeverity SLA:\n{sla}"
    )
