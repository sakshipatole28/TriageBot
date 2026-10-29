#!/usr/bin/env bash
# Deploys a TriageBot image to the local kind cluster and checks that it works.
# Used by BOTH pipelines (Jenkinsfile and .github/workflows/ci.yml), and by hand:
#   GROQ_API_KEY=gsk_... ./scripts/deploy-k8s.sh triagebot:1.0
#
# Needs on the machine: docker, kind, kubectl, curl.
# Reads (optional) GROQ_API_KEY / GEMINI_API_KEY from the environment for the Secret.
set -euo pipefail

IMAGE="${1:?usage: deploy-k8s.sh <image>   e.g. triagebot:1.0}"
CLUSTER="${KIND_CLUSTER:-triagebot}"
NAMESPACE="triagebot"
NODE_PORT="${NODE_PORT:-30080}"
cd "$(dirname "$0")/.."                       # run from the project root

# 1. Create the cluster the first time (later runs reuse it).
if ! kind get clusters | grep -qx "$CLUSTER"; then
    echo ">> Creating kind cluster '$CLUSTER'"
    kind create cluster --name "$CLUSTER" --config k8s/kind-cluster.yaml --wait 180s
fi

# kind writes the cluster's address and certificates; any user in the docker group can read them.
# A private kubeconfig file means this works for the jenkins user too.
KUBECONFIG="$(mktemp)"
export KUBECONFIG
trap 'rm -f "$KUBECONFIG"' EXIT
kind get kubeconfig --name "$CLUSTER" > "$KUBECONFIG"

# 2. Copy the image from the host's Docker into the cluster node (no registry needed).
echo ">> Loading $IMAGE into the cluster"
kind load docker-image "$IMAGE" --name "$CLUSTER"

# 3. Namespace first, because the Secret lives inside it.
kubectl apply -f k8s/namespace.yaml

# 4. API keys come from the pipeline's credentials, never from git.
#    No key given: keep the existing Secret, or create an empty one so pods can start
#    (the app then answers /health but /triage returns 503).
if [[ -n "${GROQ_API_KEY:-}" || -n "${GEMINI_API_KEY:-}" ]]; then
    echo ">> Updating Secret triagebot-secrets"
    kubectl -n "$NAMESPACE" create secret generic triagebot-secrets \
        --from-literal=GROQ_API_KEY="${GROQ_API_KEY:-}" \
        --from-literal=GEMINI_API_KEY="${GEMINI_API_KEY:-}" \
        --dry-run=client -o yaml | kubectl apply -f -
elif ! kubectl -n "$NAMESPACE" get secret triagebot-secrets >/dev/null 2>&1; then
    echo ">> No API key given; creating an empty Secret"
    kubectl -n "$NAMESPACE" create secret generic triagebot-secrets \
        --from-literal=GROQ_API_KEY= --from-literal=GEMINI_API_KEY=
fi

# 5. Apply all manifests, swapping in the image this pipeline just built.
#    A new tag changes the Deployment, so Kubernetes does a rolling update.
echo ">> Applying manifests with image $IMAGE"
kubectl kustomize k8s/ | sed "s|image: triagebot:1.0|image: $IMAGE|" | kubectl apply -f -

# 6. Wait until the new pods pass their readiness probe.
if ! kubectl -n "$NAMESPACE" rollout status deployment/triagebot-api --timeout=180s; then
    echo ">> Rollout failed"
    kubectl -n "$NAMESPACE" get pods -o wide
    kubectl -n "$NAMESPACE" describe pods -l app=triagebot-api | tail -40
    kubectl -n "$NAMESPACE" logs -l app=triagebot-api --tail=50 || true
    exit 1
fi
kubectl -n "$NAMESPACE" get pods,svc

# 7. Smoke test through the NodePort, the same way a user reaches it.
for i in $(seq 1 30); do
    if curl -fsS "http://localhost:$NODE_PORT/health"; then
        echo; echo ">> Deployed: http://localhost:$NODE_PORT"
        exit 0
    fi
    sleep 2
done
echo ">> /health did not answer on port $NODE_PORT"
exit 1
