#!/bin/bash
#
# Generate a kubeconfig for a service account that can be used by HolmesGPT
# This kubeconfig can then be uploaded to InfraInsights
#
# Usage: ./generate_sa_kubeconfig.sh <service-account-name> <namespace> <cluster-name> [output-file]
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check arguments
if [ "$#" -lt 3 ]; then
    error "Usage: $0 <service-account-name> <namespace> <cluster-name> [output-file]"
    echo ""
    echo "Example:"
    echo "  $0 pod-wizardry-sa default multitenant-prod ./kubeconfig-holmes.yaml"
    echo ""
    exit 1
fi

SERVICE_ACCOUNT=$1
NAMESPACE=$2
CLUSTER_NAME=$3
OUTPUT_FILE=${4:-"kubeconfig-${SERVICE_ACCOUNT}.yaml"}

info "Generating kubeconfig for service account: ${SERVICE_ACCOUNT}"
info "Namespace: ${NAMESPACE}"
info "Cluster: ${CLUSTER_NAME}"

# Check if service account exists
if ! kubectl get serviceaccount "${SERVICE_ACCOUNT}" -n "${NAMESPACE}" &>/dev/null; then
    error "Service account '${SERVICE_ACCOUNT}' not found in namespace '${NAMESPACE}'"
    exit 1
fi

# Get service account secret (works for k8s < 1.24)
SECRET_NAME=$(kubectl get serviceaccount "${SERVICE_ACCOUNT}" -n "${NAMESPACE}" -o jsonpath='{.secrets[0].name}' 2>/dev/null || echo "")

# For k8s >= 1.24, we need to create a token manually
if [ -z "$SECRET_NAME" ] || [ "$SECRET_NAME" == "null" ]; then
    info "No secret found (Kubernetes >= 1.24), creating a token..."
    
    # Create a temporary token (valid for 1 year)
    TOKEN=$(kubectl create token "${SERVICE_ACCOUNT}" -n "${NAMESPACE}" --duration=8760h)
    
    if [ -z "$TOKEN" ]; then
        error "Failed to create token"
        exit 1
    fi
else
    info "Using existing secret: ${SECRET_NAME}"
    TOKEN=$(kubectl get secret "${SECRET_NAME}" -n "${NAMESPACE}" -o jsonpath='{.data.token}' | base64 --decode)
fi

# Get cluster information from current context
CURRENT_CONTEXT=$(kubectl config current-context)
info "Using current context: ${CURRENT_CONTEXT}"

CLUSTER_SERVER=$(kubectl config view -o jsonpath="{.clusters[?(@.name==\"$(kubectl config view -o jsonpath="{.contexts[?(@.name==\"${CURRENT_CONTEXT}\")].context.cluster}")\")].cluster.server}")
CLUSTER_CA=$(kubectl config view --raw -o jsonpath="{.clusters[?(@.name==\"$(kubectl config view -o jsonpath="{.contexts[?(@.name==\"${CURRENT_CONTEXT}\")].context.cluster}")\")].cluster.certificate-authority-data}")

if [ -z "$CLUSTER_SERVER" ]; then
    error "Could not determine cluster server"
    exit 1
fi

info "Cluster server: ${CLUSTER_SERVER}"

# Generate kubeconfig
cat > "${OUTPUT_FILE}" <<EOF
apiVersion: v1
kind: Config
clusters:
- cluster:
    certificate-authority-data: ${CLUSTER_CA}
    server: ${CLUSTER_SERVER}
  name: ${CLUSTER_NAME}
contexts:
- context:
    cluster: ${CLUSTER_NAME}
    user: ${SERVICE_ACCOUNT}
    namespace: ${NAMESPACE}
  name: ${CLUSTER_NAME}
current-context: ${CLUSTER_NAME}
users:
- name: ${SERVICE_ACCOUNT}
  user:
    token: ${TOKEN}
EOF

info "✅ Kubeconfig generated: ${OUTPUT_FILE}"
echo ""

# Verify the kubeconfig works
info "Testing the kubeconfig..."
if kubectl --kubeconfig="${OUTPUT_FILE}" auth can-i list pods -n default &>/dev/null; then
    info "✅ Kubeconfig is valid and can list pods"
else
    warn "⚠️  Kubeconfig might not have sufficient permissions"
fi

# Test events permission specifically
if kubectl --kubeconfig="${OUTPUT_FILE}" auth can-i list events --all-namespaces &>/dev/null; then
    info "✅ Kubeconfig can list events"
else
    warn "⚠️  Kubeconfig cannot list events - you may need to grant permissions"
    echo ""
    warn "To grant events permissions, run:"
    echo ""
    echo "    kubectl create clusterrolebinding ${SERVICE_ACCOUNT}-events-reader \\"
    echo "      --clusterrole=pod-wizardry-role \\"
    echo "      --serviceaccount=${NAMESPACE}:${SERVICE_ACCOUNT}"
    echo ""
fi

echo ""
info "📋 Next steps:"
echo "   1. Review the generated kubeconfig: ${OUTPUT_FILE}"
echo "   2. Update the InfraInsights instance 'multitenant-prod' with this kubeconfig"
echo "   3. Test HolmesGPT again"
echo ""
info "To update InfraInsights, you can use their API or UI"
echo ""

# Show sample curl command to update
cat <<'CURL_EXAMPLE'
Example API call to update (replace with your values):

curl -X PATCH "http://your-infrainsights-url/api/service-instances/kubernetes-1751174496165" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "kubeconfig": "'"$(cat kubeconfig-pod-wizardry-sa.yaml)"'"
    }
  }'

CURL_EXAMPLE

info "Done! 🎉"


