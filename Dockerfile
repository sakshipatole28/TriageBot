# TriageBot container image
# Build:  docker build -t triagebot:1.0 .
# Run:    docker run --rm -p 8000:8000 --env-file .env triagebot:1.0

# 1. Small official Python image (Debian "slim" = no compilers, docs, etc.)
FROM python:3.11-slim

# 2. Python settings: no .pyc files, print logs immediately, no pip cache in the image.
#    Longer timeout + retries so pip survives a slow or flaky network.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10

WORKDIR /app

# 3. Create a normal (non-root) user. If the app is ever hacked, the attacker is not root.
RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --create-home --shell /usr/sbin/nologin appuser

# 4. Install dependencies FIRST. This layer is cached and only rebuilt
#    when requirements.txt changes, not on every code change.
#    The cache mount keeps downloaded wheels between builds (not in the image),
#    so a retry after a network timeout does not download everything again.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    env -u PIP_NO_CACHE_DIR pip install -r requirements.txt

# 5. Copy the application code (changes often, so it comes last)
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser streamlit_app.py .
COPY --chown=appuser:appuser .streamlit ./.streamlit

# 6. From here on, everything runs as the non-root user
USER appuser

# 7. Document the ports: 8000 = FastAPI, 8501 = Streamlit (optional UI)
EXPOSE 8000 8501

# 8. Docker checks /health every 30s and marks the container healthy/unhealthy.
#    We use Python instead of curl so we do not need to install extra packages.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1

# 9. Start the API. 0.0.0.0 = listen on all interfaces so the port mapping works.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
