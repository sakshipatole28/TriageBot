# TriageBot Explained (viva guide)

## 1. The problem in simple words

**The problem.** When a college app like "CampusConnect" has thousands of students, bug reports pour
in every day. Someone has to read each one, work out what is broken, check whether it was already
reported, find out which team owns that part of the app, and decide how urgent it is. Doing this by
hand is slow and boring, and duplicates slip through.

**What the app does.** TriageBot does that first pass automatically. You paste a bug report. Three
AI agents work on it in turn, and you get back a ready ticket: severity (S1 to S4), priority (P0 to P3),
the owning team, a possible duplicate from the issue tracker, and next steps.

**Why containers help.** The app needs Python 3.11, about ten pinned libraries and the right settings.
Without containers, "it works on my laptop" often fails on the lab PC or the server. A Docker image
packs the code, Python and all libraries into one unit that runs the same everywhere. Docker Compose
starts the API and the UI together with one command, and Kubernetes can run several copies and restart
them if they crash. CI/CD builds and tests that same image automatically on every push.

## 2. Architecture

```
                    Browser (HTML/JS UI on :8000)  or  Streamlit UI container (:8501)
                                     |
                                     |  POST /triage {"issue": "..."}
                                     v
  +------------------------------------------------------------------------------+
  |  FastAPI (app/main.py)                                                        |
  |   - Pydantic validates input (422 if too short)                               |
  |   - no API key?  -> 503                                                       |
  |   - runs the workflow in a thread with a timeout (504)                        |
  +-------------------------------------+----------------------------------------+
                                        |
                                        v   run_triage_workflow()  (app/agents/triage_team.py)
  +------------------------------------------------------------------------------+
  |  Agent 1: Issue Analyst                                                       |
  |    raw report -> summary, steps, environment, likely component                |
  +-------------------------------------+----------------------------------------+
                                        | analysis (text)
                                        v
  +------------------------------------------------------------------------------+
  |  Agent 2: Duplicate Investigator            function calling                  |
  |    LLM decides to call  ------------------>  search_known_issues(query)       |
  |                         ------------------>  get_component_owner(component)   |
  |                         <------------------  results from app/data/*.json     |
  +-------------------------------------+----------------------------------------+
                                        | investigation (text) + tool results
                                        v
  +------------------------------------------------------------------------------+
  |  Agent 3: Triage Lead                                                         |
  |    report + analysis + investigation -> Severity / Priority / Team /          |
  |    Duplicate of / Summary / Next steps / Questions for reporter               |
  +-------------------------------------+----------------------------------------+
                                        v
         JSON: severity, priority, team, related_issues, tools_used, report

  LLM provider: Gemini or Groq (chosen by environment variables)
```

## 3. File-by-file

| File | What it is for |
|---|---|
| `app/main.py` | FastAPI app with three routes (`/`, `/health`, `/triage`) and the error handling (422/503/504/500). |
| `app/config.py` | Reads all settings and API keys from environment variables and hides keys in error messages. |
| `app/schemas.py` | Pydantic models that check the incoming bug report and describe the JSON responses. |
| `app/agents/triage_team.py` | Creates the three Agno agents and runs them in order, passing each output to the next. |
| `app/agents/tools.py` | The two real tools the Investigator can call: issue search and team lookup. |
| `app/agents/__init__.py` | Makes the agent functions importable as one package. |
| `app/data/known_issues.json` | Ten sample past bugs, the local "issue tracker" the search tool reads. |
| `app/data/components.json` | Which team owns which part of the app, and their chat channel. |
| `app/data/__init__.py` | Loads the JSON files and holds the severity response-time rules. |
| `app/static/index.html` | The web page layout. |
| `app/static/style.css` | Styling for the web page, with light and dark mode. |
| `app/static/app.js` | Calls `/health` and `/triage` and shows the result safely (HTML is escaped). |
| `streamlit_app.py` | Optional second UI that talks to the API over HTTP, so it runs as its own container. |
| `.streamlit/config.toml` | Streamlit settings (headless, no usage stats). |
| `tests/conftest.py` | Fake agents and shared fixtures so tests never call a real LLM. |
| `tests/test_health.py` | Tests `/health`, `/`, and that the key never appears in responses. |
| `tests/test_api.py` | Tests validation, the 503 without a key, a mocked run, a real-tools run and key redaction. |
| `tests/test_agents.py` | Tests team construction, agent hand-offs, both tools and the field parser. |
| `pytest.ini` | Tells pytest where the tests are and hides one harmless library warning. |
| `requirements.txt` | Exact versions of every Python library. |
| `.env.example` | Template showing which settings exist, with blank keys. |
| `.gitignore` | Stops `.env`, venvs and caches from being committed to git. |
| `.dockerignore` | Stops `.env`, venvs, git, tests and docs from being copied into the image. |
| `Dockerfile` | Recipe for building the container image. |
| `docker-compose.yml` | Runs the API and Streamlit containers together with healthchecks. |
| `k8s/namespace.yaml` | Creates the `triagebot` namespace. |
| `k8s/configmap.yaml` | Non-secret settings (provider, model names, timeout). |
| `k8s/secret.yaml` | Placeholder API keys, for reference only. Not applied; the deploy script creates the real Secret. |
| `k8s/deployment.yaml` | Runs 2 pods with probes, resource limits and a non-root security context. |
| `k8s/service.yaml` | Gives the pods one stable address, load-balances between them, and opens NodePort 30080. |
| `k8s/ingress.yaml` | Exposes the service outside the cluster at `triagebot.local`. |
| `k8s/kustomization.yaml` | Lets `kubectl apply -k k8s/` apply all manifests at once (not the Secret). |
| `k8s/kind-cluster.yaml` | Settings for the local kind cluster: maps host port 30080 to the NodePort. |
| `scripts/deploy-k8s.sh` | The deploy step both pipelines share: cluster, image load, Secret, apply, rollout, `/health`. |
| `.github/workflows/ci.yml` | GitHub Actions: test, build, check `/health`, push to GHCR (main), deploy to a kind cluster. |
| `Jenkinsfile` | Jenkins pipeline: test, build, check, then deploy to the local kind cluster (live on :30080). |
| `README.md` | Short how-to-run guide. |
| `EXPLAINED.md` | This file. |

## 4. Line by line

### Dockerfile

| Line | Meaning |
|---|---|
| `FROM python:3.11-slim` | Start from the official Python 3.11 image, "slim" Debian variant (small, no compilers). |
| `ENV PYTHONDONTWRITEBYTECODE=1` | Do not write `.pyc` files; they are useless in an image. |
| `PYTHONUNBUFFERED=1` | Print logs immediately, so `docker logs` shows them in real time. |
| `PIP_NO_CACHE_DIR=1` | Do not keep pip's download cache, which keeps the image smaller. |
| `PIP_DISABLE_PIP_VERSION_CHECK=1` | Skip pip's "new version available" check. |
| `PIP_DEFAULT_TIMEOUT=120`, `PIP_RETRIES=10` | Wait longer and retry more, so a slow or flaky network doesn't fail the build with "from versions: none". |
| `WORKDIR /app` | All following commands run in `/app`, and it is created if missing. |
| `RUN groupadd ... useradd ...` | Create user `appuser` with UID 10001 and no login shell. |
| `COPY requirements.txt .` | Copy ONLY the dependency list first. |
| `RUN pip install -r requirements.txt` | Install libraries. Docker caches this layer and reuses it until `requirements.txt` changes, so code edits rebuild in seconds. |
| `COPY --chown=appuser:appuser app ./app` | Copy the code, owned by appuser. |
| `COPY ... streamlit_app.py .` / `.streamlit` | Copy the optional UI and its config. |
| `USER appuser` | Everything from here on, including the running app, is not root. |
| `EXPOSE 8000 8501` | Documents which ports the container listens on (it does not publish them; `-p` does). |
| `HEALTHCHECK ... CMD python -c "urllib...(/health)"` | Every 30s Docker calls `/health`. After 3 failures the container is marked `unhealthy`. Python is used instead of curl, so nothing extra is installed. |
| `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]` | Default start command. `0.0.0.0` means "accept connections from outside the container", which port mapping needs. |

### docker-compose.yml

| Line | Meaning |
|---|---|
| `services:` | List of containers to run. |
| `api:` / `build: .` | Build the image from the Dockerfile in this folder. |
| `image: triagebot:1.0` | Name and tag of the built image. |
| `container_name: triagebot-api` | Fixed container name, which makes `docker logs triagebot-api` easy. |
| `env_file: - path: .env, required: false` | Load API keys from `.env` on the host. If `.env` is missing the stack still starts and `/triage` returns 503. (Needs Compose 2.24 or newer.) |
| `ports: "8000:8000"` | Host port 8000 goes to container port 8000. |
| `volumes: ./app/data:/app/app/data:ro` | Mount the issue tracker JSON from the host, read-only. Edit it on the host and the tools see the change immediately. |
| `healthcheck: test/interval/timeout/retries/start_period` | Same `/health` check as the Dockerfile: every 15s, 5s timeout, 3 failures means unhealthy, and failures in the first 20s don't count. |
| `restart: unless-stopped` | If the container crashes, Docker restarts it (unless you stopped it yourself). |
| `ui:` / `command: streamlit run ...` | Same image, but starts Streamlit instead of uvicorn. |
| `API_URL: http://api:8000` | Compose has built-in DNS, so the name `api` resolves to the api container. |
| `depends_on: api: condition: service_healthy` | Start the UI only after the API is healthy. |
| (no `env_file` on ui) | The UI never sees the API keys (least privilege). |

### k8s/deployment.yaml

| Line | Meaning |
|---|---|
| `apiVersion: apps/v1`, `kind: Deployment` | The object type that manages identical pods. |
| `metadata: name/namespace/labels` | Name it `triagebot-api` in the `triagebot` namespace. |
| `replicas: 2` | Always keep 2 pods running. If one dies, a new one is created. |
| `selector.matchLabels: app: triagebot-api` | The deployment owns pods with this label. |
| `template:` | The blueprint for each pod. |
| `securityContext: runAsNonRoot / runAsUser: 10001` | Kubernetes refuses to run the pod as root, and uses the same UID as the Dockerfile. |
| `image: triagebot:1.0`, `imagePullPolicy: IfNotPresent` | Use the image loaded into the cluster by `kind load` instead of pulling from a registry. |
| `containerPort: 8000` (named `http`) | The port the app listens on. |
| `envFrom: configMapRef / secretRef` | Every key in the ConfigMap and the Secret becomes an environment variable, and `config.py` reads them. |
| `readinessProbe: httpGet /health` | "Can this pod take traffic?" If not, the Service stops sending it requests. |
| `livenessProbe: httpGet /health` | "Is this pod still alive?" If it fails 3 times, Kubernetes restarts the container. |
| `initialDelaySeconds / periodSeconds / failureThreshold` | Wait before the first check, how often to check, and how many failures count as "down". |
| `resources.requests: cpu 100m, memory 128Mi` | Minimum guaranteed (100m = 0.1 CPU). The scheduler uses this to pick a node. The app was measured at about 68 MB idle. |
| `resources.limits: cpu 500m, memory 512Mi` | Hard maximum. Above 512Mi the container is killed (OOMKilled), and CPU is throttled at 0.5. |
| `allowPrivilegeEscalation: false`, `drop: ["ALL"]` | The process cannot gain extra Linux privileges. |

## 5. Likely viva questions

1. **Image vs container?** An image is a read-only template (code, Python, libraries). A container is a running instance of an image. One image can run many containers.
2. **Why `python:3.11-slim`?** It is official and much smaller than the full image, so builds, pushes and the attack surface are all smaller.
3. **Why copy `requirements.txt` before the code?** Layer caching. The slow `pip install` layer is reused until dependencies change, so code edits rebuild in seconds.
4. **Why a non-root user?** If someone exploits the app, they get a powerless user, not root inside the container. Kubernetes `runAsNonRoot` enforces it.
5. **Why a healthcheck?** "Process is running" does not mean "app works". `/health` proves the web server responds. Docker marks the container healthy or unhealthy, compose waits for it, and Kubernetes routes traffic and restarts pods based on it.
6. **Readiness vs liveness probe?** Readiness decides whether a pod gets traffic. Liveness decides whether the pod should be restarted.
7. **ConfigMap vs Secret?** A ConfigMap holds normal settings (model name, timeout). A Secret holds sensitive values (API keys). It is stored separately, can be encrypted and access-controlled, and is not shown by `kubectl describe`. Base64 is encoding, not encryption.
8. **Why environment variables for keys?** The same image runs everywhere with different keys, and keys never end up in git or inside the image. That is also why `.env` is in `.gitignore` and `.dockerignore`.
9. **What does `.dockerignore` do?** It keeps files out of the build context, so `.env`, `.venv` and `.git` can never be copied into the image, and the build is faster.
10. **What does each agent do?** The Issue Analyst structures the raw report and guesses the component. The Duplicate Investigator calls `search_known_issues` and `get_component_owner` to find duplicates and the owner. The Triage Lead decides severity, priority, team and next steps using only what it was given.
11. **What is function calling?** We give the LLM the tool's name, parameters and docstring. The LLM replies "call `search_known_issues('android crash upload')`", Agno runs our Python function, and the result goes back to the LLM. The API's `tools_used` field proves it happened.
12. **Why mock the LLM in tests?** Tests must be fast, free, repeatable and run in CI without a key or internet. A real LLM gives different text every time. Our fake Investigator still runs the real tools, so the hand-off logic and the tools are really tested.
13. **What happens without an API key?** `/health` still returns 200 with `llm_configured: false`, and `/triage` returns 503 with a clear message. The service is up but not fully usable, which is honest.
14. **What does docker compose add over `docker run`?** It defines both containers, their ports, volume, env file, healthchecks, restart policy and start order in one file, and starts it all with one command on a shared network with DNS.
15. **What does the CI/CD pipeline do?** On every push: install dependencies and run pytest. Only if that passes: build the Docker image, start it and curl `/health`, then deploy it to Kubernetes with `scripts/deploy-k8s.sh`. That script loads the image into the kind cluster, creates the Secret from the pipeline's credentials, applies `k8s/` with the new image tag, waits for `kubectl rollout status` and curls `/health` through the Service. GitHub Actions also pushes the image to GHCR on `main`. Jenkins deploys to the cluster on this machine, so the app stays live at `localhost:30080`. A broken change stops at the first failing stage and never reaches the cluster.
16. **What is a rolling update?** Each build has a new image tag, so the Deployment changes. Kubernetes starts new pods, waits for their readiness probe, and only then removes old pods, so there is no downtime. A bad image never becomes ready, the rollout times out, the pipeline fails and the old pods keep serving.
17. **Why kind and not minikube?** kind runs the whole cluster as Docker containers, so any user who can use Docker (including the jenkins user and the GitHub runner) can create it, load images into it and get its kubeconfig. It is the same Kubernetes API as any real cluster.
18. **Why is secret.yaml not in kustomization?** Otherwise every deploy would overwrite the real key with the placeholder. The pipeline creates the Secret from Jenkins credentials or GitHub secrets, so the key is never in git.
19. **(Bonus) Why do 504 and 500 exist?** 504: the three LLM calls took longer than `REQUEST_TIMEOUT`. 500: the provider failed (for example a wrong key). The key is replaced with `[REDACTED]` in the message.

## 6. Demo script (under 2 minutes)

```bash
cd TriageBot
pytest -v                                   # 17 passed, no key needed
docker compose up -d --build
docker compose ps                           # api and ui both "(healthy)"
curl http://localhost:8000/health
```

Open **http://localhost:8000**, click **"Crash on photo upload"** (or paste the text below) and press **Triage this bug**:

> The Android app crashes as soon as I try to upload my profile photo. The photo is about 8 MB from my phone camera. App version 2.3.1 on a Samsung A52.

Expected: Severity around S2, the **Media Team**, a related issue of **BUG-104** (the known large-photo crash), tools called `search_known_issues, get_component_owner`, and a workaround ("crop the photo first").

Or from the terminal:

```bash
curl -s -X POST http://localhost:8000/triage -H "Content-Type: application/json" \
  -d '{"issue":"The Android app crashes as soon as I try to upload my profile photo. The photo is about 8 MB. App version 2.3.1."}'
```

Show the second container: open **http://localhost:8501** (the Streamlit UI calling the API over the compose network).

Show Kubernetes (deployed by Jenkins or by hand with `./scripts/deploy-k8s.sh triagebot:1.0`):

```bash
kubectl --context kind-triagebot -n triagebot get pods,svc     # 2 pods Running, NodePort 30080
curl http://localhost:30080/health
```

Show the pipelines: the green Jenkins build (all 5 stages) and the green GitHub Actions run.

Finish with `docker compose down`.
