"""FastAPI application for TriageBot.

Routes:
- GET  /        -> the HTML/CSS/JS web page
- GET  /health  -> is the service up? (used by Docker, compose, Kubernetes and CI)
- POST /triage  -> run the 3-agent team on a bug report
"""

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.agents.triage_team import AGENT_NAMES, run_triage_workflow
from app.data import load_known_issues
from app.schemas import HealthResponse, TriageRequest, TriageResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("triagebot")

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title=config.APP_NAME,
    description="Three AI agents read a bug report, find duplicates with real tools, and triage it.",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def serve_frontend() -> FileResponse:
    """Serve the single-page web UI."""
    return FileResponse(str(STATIC_DIR / "index.html"), media_type="text/html")


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness/readiness check. Says whether a key exists, never shows the key itself."""
    return HealthResponse(
        app_name=config.APP_NAME,
        llm_configured=config.is_provider_configured(),
        model=config.get_active_model_name(),
        agents=AGENT_NAMES,
        known_issues=len(load_known_issues()),
    )


@app.post("/triage", response_model=TriageResponse)
async def triage_issue(request: TriageRequest) -> TriageResponse:
    """Send a bug report through Analyst -> Investigator -> Lead and return the decision."""
    if not config.is_provider_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "LLM API key is not configured. Set GEMINI_API_KEY (https://aistudio.google.com/apikey) "
                "or GROQ_API_KEY (https://console.groq.com/keys) in .env or the environment."
            ),
        )

    logger.info("Triaging bug report (%d characters)", len(request.issue))
    try:
        # The agents are synchronous, so run them in a worker thread with a time limit.
        result = await asyncio.wait_for(
            asyncio.to_thread(run_triage_workflow, request.issue),
            timeout=config.REQUEST_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"The agents took longer than {config.REQUEST_TIMEOUT} seconds. Please try again.",
        )
    except Exception as exc:
        message = config.redact_secrets(str(exc))
        logger.error("Agent workflow failed: %s", message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"The agent team failed: {message}",
        )

    return TriageResponse(
        issue=request.issue,
        report=result["report"],
        severity=result.get("severity"),
        priority=result.get("priority"),
        team=result.get("team"),
        related_issues=result.get("related_issues", []),
        tools_used=result.get("tools_used", []),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT)
