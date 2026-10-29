"""The TriageBot agent team.

Three Agno agents work one after another, each handing its output to the next:

    bug report
       -> 1. Issue Analyst          (structures the report, guesses the component)
       -> 2. Duplicate Investigator (CALLS TOOLS: searches past issues, finds the owner)
       -> 3. Triage Lead            (decides severity, priority, team and next steps)
       -> final triage report

We wire the hand-offs ourselves in run_triage_workflow() instead of letting
an LLM "coordinator" decide, so the flow is predictable, cheaper (3 LLM steps)
and easy to test with fake agents.
"""

import re
from typing import Any, Dict, List, Optional

from agno.agent import Agent

from app import config
from app.agents.tools import get_component_owner, search_known_issues

AGENT_NAMES = ["Issue Analyst", "Duplicate Investigator", "Triage Lead"]

COMPONENT_LIST = "auth, media-upload, notifications, timetable, search, web-ui, attendance"


def create_model(api_key: Optional[str] = None, model_id: Optional[str] = None):
    """Create the LLM object for the selected provider (Gemini or Groq).

    Creating the object does not call the internet; the first call happens in agent.run().
    """
    if config.MODEL_PROVIDER == "google":
        from agno.models.google import Gemini

        return Gemini(id=model_id or config.GEMINI_MODEL, api_key=api_key or config.GEMINI_API_KEY)

    from agno.models.groq import Groq

    return Groq(id=model_id or config.GROQ_MODEL, api_key=api_key or config.GROQ_API_KEY)


def build_triage_team(api_key: Optional[str] = None, model_id: Optional[str] = None) -> Dict[str, Agent]:
    """Build the three agents. Returns a dict so each step can be called by role."""
    model = create_model(api_key=api_key, model_id=model_id)

    analyst = Agent(
        name="Issue Analyst",
        role="Turn a messy bug report into a clear, structured summary.",
        model=model,
        telemetry=False,
        instructions=[
            "Read the bug report and write these short sections:",
            "Summary (one sentence), Steps to reproduce, Expected vs actual behaviour,",
            "Environment (device, OS, app version if given), Likely component, Missing information.",
            f"Likely component must be ONE of: {COMPONENT_LIST}.",
            "Only use facts from the report. Write 'not given' when something is missing.",
        ],
    )

    investigator = Agent(
        name="Duplicate Investigator",
        role="Check the issue tracker for duplicates and find the owning team.",
        model=model,
        tools=[search_known_issues, get_component_owner],
        telemetry=False,
        instructions=[
            "You MUST call search_known_issues with 4-8 keywords from the analysis.",
            "You MUST call get_component_owner with the likely component.",
            "Then report: possible duplicates (issue ID, status, why it matches or not),",
            "the owning team and contact, and any known workaround.",
            "Never invent issue IDs. Only mention IDs returned by the tools.",
        ],
    )

    lead = Agent(
        name="Triage Lead",
        role="Make the final triage decision and write the ticket.",
        model=model,
        telemetry=False,
        instructions=[
            "Decide using ONLY the analysis and investigation you are given.",
            "Start your answer with exactly these four lines:",
            "Severity: <S1|S2|S3|S4>",
            "Priority: <P0|P1|P2|P3>",
            "Team: <owning team name>",
            "Duplicate of: <issue ID, or 'None - new issue'>",
            "Then add markdown sections: ### Summary, ### Why this severity, "
            "### Next steps (numbered), ### Questions for the reporter.",
            "S1 = core feature broken for many users, S2 = major feature broken, "
            "S3 = minor bug with workaround, S4 = cosmetic.",
        ],
    )

    return {"analyst": analyst, "investigator": investigator, "lead": lead}


def _content(run_output: Any) -> str:
    """Get the text out of an Agno RunOutput, and stop if the agent failed."""
    status = str(getattr(run_output, "status", "")).lower()
    text = str(getattr(run_output, "content", "") or "").strip()
    if "error" in status:
        raise RuntimeError(text or "The LLM provider returned an error.")
    return text


def _tool_calls(run_output: Any) -> List[Any]:
    """Tool calls the agent made during its run (empty list if none)."""
    return list(getattr(run_output, "tools", None) or [])


def extract_field(report: str, name: str) -> Optional[str]:
    """Read a 'Name: value' line from the report, e.g. extract_field(r, 'Severity') -> 'S2'."""
    match = re.search(rf"^[\s*#-]*{name}\s*\**\s*:\s*\**\s*(.+?)\s*\**\s*$", report, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else None


def run_triage_workflow(issue_text: str, team: Optional[Dict[str, Agent]] = None) -> Dict[str, Any]:
    """Run the 3 agents in order and return the final triage result."""
    team = team or build_triage_team()

    # Step 1: Issue Analyst structures the raw report.
    analysis = _content(team["analyst"].run(f"Bug report:\n\"\"\"\n{issue_text}\n\"\"\""))

    # Step 2: Duplicate Investigator gets the analysis and uses the tools.
    investigation_run = team["investigator"].run(
        f"Analysis from the Issue Analyst:\n{analysis}\n\n"
        "Search for duplicates and find the owning team."
    )
    investigation = _content(investigation_run)

    # Remember which tools were called and which past issues they returned.
    tools_used: List[str] = []
    related_issues: List[str] = []
    for call in _tool_calls(investigation_run):
        name = getattr(call, "tool_name", None)
        if name and name not in tools_used:
            tools_used.append(name)
        for issue_id in re.findall(r"BUG-\d+", str(getattr(call, "result", "") or "")):
            if issue_id not in related_issues:
                related_issues.append(issue_id)

    # Step 3: Triage Lead sees the original report plus both previous outputs.
    report = _content(
        team["lead"].run(
            f"Original bug report:\n{issue_text}\n\n"
            f"Issue Analyst said:\n{analysis}\n\n"
            f"Duplicate Investigator found:\n{investigation}"
        )
    )

    severity = extract_field(report, "Severity")
    priority = extract_field(report, "Priority")
    return {
        "report": report,
        "severity": severity[:2].upper() if severity else None,
        "priority": priority[:2].upper() if priority else None,
        "team": extract_field(report, "Team"),
        "related_issues": related_issues,
        "tools_used": tools_used,
        "analysis": analysis,
        "investigation": investigation,
    }
