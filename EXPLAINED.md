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
| `PIP_DEFAULT_TIMEOUT=300`, `PIP_RETRIES=10` | Wait up to 5 minutes per download and retry 10 times, so a slow or flaky network doesn't fail the build with "Read timed out". |
| `WORKDIR /app` | All following commands run in `/app`, and it is created if missing. |
| `RUN groupadd ... useradd ...` | Create user `appuser` with UID 10001 and no login shell. |
| `COPY requirements.txt .` | Copy ONLY the dependency list first. |
| `RUN --mount=type=cache,target=/root/.cache/pip` | Give pip a download cache that lives on the build machine, not in the image. If a build fails halfway on a timeout, the next try reuses what already downloaded. |
| `env -u PIP_NO_CACHE_DIR pip install -r requirements.txt` | Install libraries. `env -u` switches off the "no cache" setting for this one command so the cache mount is used. Docker caches this layer and reuses it until `requirements.txt` changes, so code edits rebuild in seconds. |
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

### k8s/service.yaml and k8s/kind-cluster.yaml

| Line | Meaning |
|---|---|
| `type: NodePort` | Open the Service on a fixed port of the cluster node, so it can be reached from outside the cluster. |
| `port: 80`, `targetPort: http` | Inside the cluster the Service listens on 80 and forwards to the pod's port named `http` (8000). |
| `nodePort: 30080` | The port opened on the node. NodePorts must be between 30000 and 32767. |
| `extraPortMappings: containerPort 30080 -> hostPort 30080` | (kind config) The kind "node" is a Docker container; this publishes its port 30080 on your laptop, so `http://localhost:30080` reaches the Service. |

### scripts/deploy-k8s.sh (the deploy step both pipelines run)

| Line | Meaning |
|---|---|
| `set -euo pipefail` | Stop at the first failing command (`-e`), treat unset variables as errors (`-u`), and fail a pipe if any part fails (`pipefail`). A half-finished deploy never reports success. |
| `IMAGE="${1:?usage...}"` | The first argument is the image to deploy, e.g. `triagebot:42`. If it is missing, print the usage and stop. |
| `kind get clusters \| grep -qx "$CLUSTER"` / `kind create cluster ...` | Create the cluster only the first time; later runs reuse it. |
| `kind get kubeconfig ... > "$KUBECONFIG"` | Write the cluster's address and certificates to a temporary file, so kubectl knows where to connect. This works for any user in the docker group, including `jenkins`. |
| `trap 'rm -f "$KUBECONFIG"' EXIT` | Delete that temporary file when the script ends, even on failure. |
| `kind load docker-image "$IMAGE"` | Copy the image from your Docker into the cluster node. No registry (Docker Hub) is needed. |
| `kubectl apply -f k8s/namespace.yaml` | Create the namespace first, because the Secret lives inside it. |
| `kubectl create secret generic ... --dry-run=client -o yaml \| kubectl apply -f -` | Build the Secret from the pipeline's key without sending it yet (`--dry-run=client -o yaml` prints it), then `apply` creates or updates it. This "create or update" trick works on every run. |
| `kubectl kustomize k8s/ \| sed "s\|image: triagebot:1.0\|image: $IMAGE\|" \| kubectl apply -f -` | Combine all manifests, swap in the image tag this build made, and apply them. The changed tag starts a rolling update. |
| `kubectl rollout status ... --timeout=180s` | Wait until the new pods pass their readiness probe. If they don't within 3 minutes, print pod details and logs and fail the pipeline. |
| `curl -fsS http://localhost:30080/health` (retry loop) | Final smoke test through the NodePort, the same way a user reaches the app. `-f` makes curl fail on an HTTP error. |

### .github/workflows/ci.yml

| Line | Meaning |
|---|---|
| `on: push, pull_request` | Run on every push to any branch and on every pull request. |
| `permissions: packages: write` | Let the built-in `GITHUB_TOKEN` push images to GitHub Container Registry. |
| `jobs: test` | Fresh Ubuntu machine: checkout, install Python 3.11, install requirements, run pytest. |
| `deploy: needs: test` | Only runs if `test` passed. |
| `docker build -t "$IMAGE"` | Build the image, tagged with the commit id (`github.sha`), so every version is unique. |
| `docker run ... curl /health` | Prove the container starts and answers before deploying it. |
| `if: github.event_name == 'push' && github.ref == 'refs/heads/main'` | Push the image to `ghcr.io` only for pushes to `main`, not for other branches or pull requests. |
| `${GITHUB_REPOSITORY_OWNER,,}` | Bash for "lowercase this", because registry names must be lowercase. |
| `uses: helm/kind-action@v1` | Ready-made step that installs kind and kubectl and creates a cluster from `k8s/kind-cluster.yaml`. |
| `GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}` | Read the key from the repo's encrypted secrets. GitHub masks it as `***` in the logs. |
| `run: ./scripts/deploy-k8s.sh "$IMAGE"` | Deploy to that cluster and check it. The cluster is thrown away when the job ends; it proves the deploy works. |

### Jenkinsfile

| Line | Meaning |
|---|---|
| `pipeline { agent any` | Declarative pipeline that may run on any Jenkins machine (here, your laptop). |
| `triggers { pollSCM('H/5 * * * *') }` | Check GitHub for new commits about every 5 minutes. `H` spreads jobs out so they don't all start at the same second. Webhooks can't reach a laptop, so polling is used. |
| `environment { IMAGE = "triagebot:${BUILD_NUMBER}" }` | Each build gets its own image tag: build 7 makes `triagebot:7`. |
| `stage('Checkout') { checkout scm }` | Download the code from the repo configured in the job. |
| `stage('Test')` | Make a venv, install requirements, run pytest and save a JUnit XML report. |
| `stage('Docker Build')` | `docker build --network=host` so pip uses the laptop's network directly (avoids timeouts). |
| `stage('Run & Health Check')` | Start the image on port 8001 and curl `/health`. |
| `withCredentials([string(credentialsId: 'groq-api-key', ...)])` | Load the key from Jenkins' credential store into `$GROQ_API_KEY` for this step only, masked in the log. |
| `sh './scripts/deploy-k8s.sh "$IMAGE"'` | Deploy to the kind cluster on this machine. It stays running at `localhost:30080`. |
| `post { always { junit ...; docker rm -f ... } }` | Always publish the test report and remove the test container, even if a stage failed. |

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
20. **Kubernetes is a deployment tool, so why do we also need Jenkins?** They do different jobs. Kubernetes is a container *orchestrator*: given a description ("2 pods of image `triagebot:42`"), it runs them, restarts crashed ones, load-balances and does rolling updates. It never sees the code, never runs tests and never builds images, and it does not know a `git push` happened. Jenkins (and GitHub Actions) is the *CI/CD* tool: it notices the push, runs the tests, builds the image and then tells Kubernetes to use the new tag. One line: *"Kubernetes runs and heals the app; Jenkins tests, builds and rolls out each new version to Kubernetes."*

    ```
    git push -> Jenkins / GitHub Actions: pytest -> docker build -> container check -> kubectl apply (new tag)
                                                                                           |
                                                       Kubernetes: rolling update -> keep 2 pods healthy
    ```

    Without Jenkins, someone runs those steps by hand after every change. Without Kubernetes, Jenkins could only start one `docker run` container with no replicas, self-healing or zero-downtime updates. The Kubernetes object called `Deployment` is *what should run*; the CI/CD pipeline is the *process* that changes it.
21. **What is GitOps?** A third style where a tool inside the cluster (Argo CD, Flux) watches the git repo and applies the manifests itself. The pipeline then only tests, builds and pushes the image. Not used here, but it is the common next step.
22. **CI vs CD?** Continuous Integration: every push is automatically tested and built (our `test` job and the build stages). Continuous Delivery/Deployment: every passing build is automatically released (our deploy stage). We do both.

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

Expected: Severity S1 or S2 (the LLM's judgement varies between runs), the **Media Team**, a related issue of **BUG-104** (the known large-photo crash), tools called `search_known_issues, get_component_owner`, and a workaround ("crop the photo first").

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

Show self-healing: delete the pods and watch Kubernetes recreate them.

```bash
kubectl -n triagebot delete pod -l app=triagebot-api --wait=false
kubectl -n triagebot get pods -w          # new pods appear; Ctrl+C to stop watching
```

Finish with `docker compose down`.

## 7. Every command explained

### Python and tests

| Command | What it does |
|---|---|
| `python3 -m venv .venv` | Create a private Python folder `.venv` for this project, so its libraries don't mix with the system's. |
| `source .venv/bin/activate` | Use that venv in this terminal (the prompt shows `(.venv)`). `deactivate` leaves it. |
| `pip install -r requirements.txt` | Install every library at the exact version listed. |
| `pytest -v` | Run all tests; `-v` (verbose) prints each test name and PASSED/FAILED. |
| `uvicorn app.main:app --host 127.0.0.1 --port 8000` | Start the API without Docker. `app.main:app` means "the `app` object in `app/main.py`". `127.0.0.1` = only this computer can connect. |

### Docker

| Command | What it does |
|---|---|
| `docker build --network=host -t triagebot:1.0 .` | Build an image from the `Dockerfile` in `.` (this folder). `-t` names it `triagebot` with tag `1.0`. `--network=host` lets pip inside the build use the laptop's network directly, which avoids timeouts. |
| `docker run -d --name triagebot -p 8000:8000 --env-file .env triagebot:1.0` | Start a container from the image. `-d` = in the background, `--name` = a fixed name, `-p host:container` = publish the port, `--env-file` = pass the API keys as environment variables. |
| `docker ps` / `docker ps -a` | List running containers / all containers including stopped ones. |
| `docker logs triagebot` (`-f` to follow) | Show what the app printed. |
| `docker rm -f triagebot` | Stop and delete the container (`-f` = even if running). The image stays. |
| `docker images` | List images on this machine. |
| `sudo usermod -aG docker $USER` then `newgrp docker` | Add yourself to the `docker` group so docker works without `sudo` (`-aG` = append to group). `newgrp` applies it in this terminal; otherwise log out and in. |

Error you may see: **"port is already allocated"** means another container already uses that host port. Find it with `docker ps` and stop it, or pick another host port (`-p 8002:8000`).

### Docker Compose

| Command | What it does |
|---|---|
| `docker compose up -d --build` | Build the image if needed and start every service in `docker-compose.yml` in the background. |
| `docker compose up -d --force-recreate` | Recreate the containers even if nothing changed, e.g. after editing `.env` (containers only read it when they are created). |
| `docker compose ps` | Show the services and their health (`starting`, `healthy`, `unhealthy`). |
| `docker compose logs -f api` | Follow the api service's logs. |
| `docker compose down` | Stop and remove the containers and the network (images stay). |

### Kubernetes (kind and kubectl)

| Command | What it does |
|---|---|
| `kind create cluster --name triagebot --config k8s/kind-cluster.yaml` | Create a one-node Kubernetes cluster that runs as a Docker container. (The deploy script does this for you the first time.) |
| `kind get clusters` | List kind clusters. |
| `kind load docker-image triagebot:1.0 --name triagebot` | Copy an image from your Docker into the cluster, so pods can use it without a registry. |
| `kind delete cluster --name triagebot` | Delete the cluster and everything in it. |
| `./scripts/deploy-k8s.sh triagebot:1.0` | Our full deploy: cluster, image, Secret, manifests, rollout wait, `/health` check. Prefix it with `GROQ_API_KEY=...` to set the key. |
| `kubectl config get-contexts` | List the clusters kubectl knows. `kind-triagebot` is ours; `*` marks the current one. |
| `kubectl -n triagebot get pods,svc` | List pods and services in the `triagebot` namespace (`-n`). `--context kind-triagebot` picks the cluster explicitly. |
| `kubectl -n triagebot get pods -w` | Keep watching pods change (`-w` = watch). Good for showing rolling updates and self-healing. |
| `kubectl -n triagebot describe pod <name>` | Full details and recent events of one pod. The first place to look when a pod won't start. |
| `kubectl -n triagebot logs -l app=triagebot-api` | Logs of all pods with that label (`-l`). |
| `kubectl apply -k k8s/` | Create or update everything listed in `k8s/kustomization.yaml` (`-k` = kustomize folder). |
| `kubectl -n triagebot rollout status deployment/triagebot-api` | Wait until a rolling update finishes. |
| `kubectl -n triagebot rollout undo deployment/triagebot-api` | Go back to the previous version. |
| `kubectl -n triagebot scale deployment/triagebot-api --replicas=3` | Run 3 pods instead of 2 (the next deploy sets it back to 2 from the YAML). |
| `kubectl -n triagebot delete pod -l app=triagebot-api` | Delete the pods; the Deployment immediately creates new ones (self-healing demo). |
| `kubectl -n triagebot create secret generic triagebot-secrets --from-literal=KEY=value` | Create a Secret from values on the command line. |

Installing them (once): download the binary with `curl -Lo <file> <url>`, then `sudo install <file> /usr/local/bin/<name>` copies it into a folder on your `PATH` and makes it executable. Check with `kind version` and `kubectl version --client`.

### Git and GitHub

| Command | What it does |
|---|---|
| `git init` | Make this folder a git repository (creates `.git/`). |
| `git add .` | Stage every file for the next commit, except what `.gitignore` excludes (`.env`, `.venv`). |
| `git status` | Show what is staged, changed or untracked. Check that `.env` is NOT listed before committing. |
| `git commit -m "message"` | Save a snapshot with a message. `-am` also stages already-tracked changed files. |
| `git branch -M main` | Rename the current branch to `main`. |
| `git remote add origin https://github.com/<user>/TriageBot.git` | Remember the GitHub repo under the name `origin`. "remote origin already exists" just means you did this already; `git remote -v` shows it. |
| `git push -u origin main` | Upload commits to GitHub. `-u` remembers the link, so later just `git push`. The password it asks for is a **personal access token** (scopes `repo` and `workflow`), not your GitHub password. |
| `git config --global credential.helper store` | Save the token after the first push, so you aren't asked again (stored in plain text in `~/.git-credentials`). |
| `git log --oneline` | List commits, one per line. |

### Jenkins

| Command / action | What it does |
|---|---|
| `sudo usermod -aG docker jenkins` | Let the `jenkins` user run docker (and therefore kind). |
| `sudo systemctl restart jenkins` | Restart Jenkins so it picks up the new group. `systemctl status jenkins` shows if it is running. |
| `sudo apt install -y python3-venv` | Needed for the Test stage's `python3 -m venv`. |
| Manage Jenkins -> Credentials -> Add -> Secret text, ID `groq-api-key` | Stores the key encrypted; the Jenkinsfile reads it by that ID. |
| New Item -> Pipeline -> "Pipeline script from SCM" -> Git URL, branch `*/main`, path `Jenkinsfile` | Jenkins reads the pipeline from the repo, so the pipeline itself is version-controlled. |
| Build Now | Run the pipeline by hand. After that, `pollSCM` runs it on every new commit. |

### curl

| Command | What it does |
|---|---|
| `curl http://localhost:8000/health` | Send a GET request and print the reply. |
| `curl -s -X POST <url> -H "Content-Type: application/json" -d '{"issue":"..."}'` | Send a POST (`-X`) with a JSON body (`-d`) and the header (`-H`) saying it is JSON. `-s` hides the progress bar. |
| `curl -fsS` | `-f` fails on HTTP errors (so scripts notice), `-sS` is silent but still shows errors. |

## 8. Tools used and easier alternatives

What each tool does here, and what a beginner could use instead. The tools we chose are free, run on a laptop and are what most companies use, which is why they are worth learning.

| Job | We used | Easier alternative | Why it is easier / the trade-off |
|---|---|---|---|
| Web API | FastAPI | Flask | Fewer concepts (no type hints or async). FastAPI gives input validation and `/docs` for free. |
| Agents | Agno | Plain Groq/Gemini SDK calls, or CrewAI | Three plain API calls in a row are easy to read, but you write tool calling yourself. CrewAI has a very similar "agents + tasks" style. |
| LLM | Groq / Gemini free tier | Ollama (local model) | No key, no rate limits and no "high demand" errors, but it needs a strong laptop and gives weaker answers. |
| Second UI | Streamlit | Gradio | Even less code for a simple input/output form. |
| Containers | Docker | Docker Desktop (GUI) or Podman | Docker Desktop shows images, containers and logs in a window. Podman is a drop-in replacement that needs no background service or root. |
| Multi-container | Docker Compose | (none simpler) | Compose is already the easiest way to run several containers. |
| Local Kubernetes | kind | Docker Desktop's built-in Kubernetes, minikube, or k3d | Docker Desktop: tick one box and it is running. minikube: has `minikube dashboard` and `minikube service` helpers. k3d: like kind but with a lighter Kubernetes (k3s). kind is the easiest for CI because it only needs Docker. |
| Orchestration | Kubernetes | Docker Swarm, or a PaaS (Render, Railway, Fly.io) | Swarm reuses the compose file (`docker stack deploy`) and has replicas and rolling updates with far less YAML. A PaaS hides all of it: connect the GitHub repo and it builds and hosts the app. The trade-off is less control and Kubernetes is the industry standard. |
| Manifests | plain YAML + Kustomize | Helm, or just `kubectl apply -f k8s/` | Helm is not simpler, but it is popular for sharing apps. Plain `apply -f` is the simplest if you don't need overrides. |
| Cluster UI | `kubectl` | k9s, Lens / Headlamp, minikube dashboard | k9s is a terminal UI: arrow keys to see pods, logs and restart. Lens/Headlamp are desktop apps with a mouse. Good for demos. |
| CI/CD (cloud) | GitHub Actions | (already the easiest), or GitLab CI | Nothing to install or host; one YAML file in the repo. GitLab CI is the same idea on GitLab. |
| CI/CD (self-hosted) | Jenkins | GitHub Actions only, or Drone / Woodpecker CI | Jenkins needs installing, plugins, credentials and a job set up by hand. Using only GitHub Actions removes all of that. Woodpecker/Drone are small self-hosted tools with GitHub-Actions-like YAML. Jenkins is still very common in companies, which is why it is included. |
| Image registry | GitHub Container Registry (ghcr.io) | Docker Hub | Docker Hub is the default everyone knows (`docker login`, `docker push user/triagebot`). GHCR needs no extra account or token in Actions, because `GITHUB_TOKEN` already has access. |
| Automatic deploy into the cluster | the pipeline runs `kubectl apply` | Argo CD (GitOps) | Not simpler to set up, but it shows a live picture of what is deployed and fixes drift automatically. |
| Secrets | Kubernetes Secret + pipeline credentials | `.env` file only (Compose) | Simplest, but only works on one machine and must never be committed. |

**If you had to make it as simple as possible**, use GitHub Actions only (drop Jenkins), Docker Desktop's Kubernetes (or minikube) instead of kind, and k9s to look at the cluster. **The most hands-off option** is a PaaS like Render: push to GitHub and it builds the Dockerfile and hosts the app, with no Kubernetes or pipeline to maintain. But then you can't show Kubernetes, which this assignment needs.
