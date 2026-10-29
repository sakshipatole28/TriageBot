"""Local data for TriageBot: a small sample issue tracker and a team ownership map.

The data describes a made-up college app called "CampusConnect".
Files are read every time a tool runs, so if you edit the JSON through the
docker compose volume mount, the change is visible without a rebuild.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

DATA_DIR = Path(__file__).resolve().parent

# Severity -> how quickly the owning team must respond.
SEVERITY_SLA = {
    "S1": "Critical: respond within 1 hour, fix in a hotfix release.",
    "S2": "Major: respond within 1 day, fix in the next release.",
    "S3": "Minor: fix within 2 releases.",
    "S4": "Cosmetic: add to the backlog.",
}


def load_known_issues() -> List[Dict[str, Any]]:
    """Return the list of past issues from known_issues.json."""
    with open(DATA_DIR / "known_issues.json", encoding="utf-8") as f:
        return json.load(f)


def load_components() -> Dict[str, Dict[str, str]]:
    """Return the component -> owning team map from components.json."""
    with open(DATA_DIR / "components.json", encoding="utf-8") as f:
        return json.load(f)
