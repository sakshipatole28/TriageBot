# TriageBot: Multi-Agent Bug Triage Assistant 🐞

TriageBot reads a new bug report for a sample college app ("CampusConnect") and hands it through
three AI agents. The **Issue Analyst** structures the report. The **Duplicate Investigator** calls real
tools to search a local issue tracker and find the owning team. The **Triage Lead** decides severity,
priority, team and next steps.

Built with FastAPI and Agno, and runs on the free tier of **Gemini** or **Groq**. It is containerised with
Docker and Docker Compose, deployable to Kubernetes, and automated with GitHub Actions and Jenkins.

See **[EXPLAINED.md](EXPLAINED.md)** for the architecture, a file-by-file guide, viva questions and the demo script.

## Quick start (Ubuntu)

```bash
# 1. Python setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Add ONE free API key
cp .env.example .env
nano .env          # set GROQ_API_KEY=... or GEMINI_API_KEY=...

# 3. Tests (no key or internet needed)
pytest -v

# 4. Run
uvicorn app.main:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000  (Swagger docs at /docs)
```

## Docker

```bash
docker build -t triagebot:1.0 .
docker run -d --name triagebot -p 8000:8000 --env-file .env triagebot:1.0
curl http://localhost:8000/health

docker compose up -d --build     # api on :8000, Streamlit ui on :8501
docker compose ps                # both should show (healthy)
docker compose down
```

## Kubernetes (kind)

```bash
docker build --network=host -t triagebot:1.0 .
GROQ_API_KEY=your_real_key ./scripts/deploy-k8s.sh triagebot:1.0
# creates the kind cluster (first time), loads the image, creates the Secret,
# applies k8s/, waits for the rollout and curls /health
# open http://localhost:30080
```

## CI/CD

Both pipelines run the tests, build the image, check the container, then deploy it to Kubernetes
with the same script, `scripts/deploy-k8s.sh`.

| Pipeline | Deploys to | Key comes from |
|---|---|---|
| GitHub Actions (`.github/workflows/ci.yml`) | a throwaway kind cluster in the runner; on `main` the image is also pushed to `ghcr.io/<owner>/triagebot` | repo secret `GROQ_API_KEY` (optional) |
| Jenkins (`Jenkinsfile`) | the kind cluster on this machine, so the app stays live at http://localhost:30080 | Jenkins credential `groq-api-key` (Secret text) |

## API

| Method | Path | What it does |
|---|---|---|
| GET | `/` | Web UI |
| GET | `/health` | Status, model, agent names, number of known issues (never the key) |
| POST | `/triage` | Body `{"issue": "..."}` (20 to 4000 chars). Returns severity, priority, team, related issues, tools used and the full report |

Error codes: `422` invalid input, `503` no API key configured, `504` the agents took too long, `500` the LLM provider failed (keys are redacted).
