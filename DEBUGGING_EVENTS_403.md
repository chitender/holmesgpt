# Debugging Kubernetes Events 403 Forbidden Error

## 🎯 Problem Summary

HolmesGPT gets a **403 Forbidden** error when trying to access Kubernetes events, even though:
- ✅ The ClusterRole has full permissions (`apiGroups: ['*']`, `resources: ['*']`)
- ✅ Testing with `kubectl auth can-i` shows the service account CAN list events

## 🔍 Root Cause

**HolmesGPT uses the kubeconfig stored in InfraInsights**, NOT your local kubectl config:

```
┌─────────────────────────────────────────────────────────┐
│ Your Local kubectl                                       │
│ ├─ Uses: Your local kubeconfig context                  │
│ ├─ Service Account: pod-wizardry-sa                     │
│ └─ Result: ✅ Has permissions                           │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ HolmesGPT                                               │
│ ├─ Fetches instance from InfraInsights                  │
│ ├─ Uses: Kubeconfig from instance.config["kubeconfig"]  │
│ ├─ Service Account: ??? (Different from yours!)         │
│ └─ Result: ❌ 403 Forbidden                             │
└─────────────────────────────────────────────────────────┘
```

## 🛠️ Solution

You need to update the kubeconfig stored in InfraInsights to use credentials that have proper permissions.

---

## Step 1: Debug the Current Kubeconfig

First, let's see what kubeconfig InfraInsights is actually using:

```bash
# Set your InfraInsights credentials
export INFRAINSIGHTS_URL="http://your-infrainsights-url"
export INFRAINSIGHTS_API_KEY="your-api-key"

# Run the debug script
python3 debug_kubeconfig.py
```

This will show you:
- What user/service account is in the kubeconfig
- What authentication method is being used
- The full kubeconfig structure (sanitized)

**Look for the "User Authentication Details" section** to identify what credentials are being used.

---

## Step 2: Generate a New Kubeconfig with Correct Credentials

Use the provided script to generate a kubeconfig that uses your `pod-wizardry-sa` service account:

```bash
# Generate kubeconfig for pod-wizardry-sa
./generate_sa_kubeconfig.sh pod-wizardry-sa default multitenant-prod ./kubeconfig-holmes.yaml

# The script will:
# 1. Extract the service account token
# 2. Get cluster CA and server info
# 3. Generate a complete kubeconfig file
# 4. Test that it works
```

**Output:** `kubeconfig-holmes.yaml` - a kubeconfig file that uses pod-wizardry-sa

---

## Step 3: Update InfraInsights

Now update the instance in InfraInsights with the new kubeconfig:

### Option A: Using InfraInsights UI

1. Log into InfraInsights web interface
2. Navigate to Service Instances → Kubernetes
3. Find instance: **multitenant-prod** (ID: kubernetes-1751174496165)
4. Edit the instance
5. Update the `kubeconfig` field with contents of `kubeconfig-holmes.yaml`
6. Save

### Option B: Using InfraInsights API

```bash
# Read the kubeconfig file
KUBECONFIG_CONTENT=$(cat kubeconfig-holmes.yaml)

# Update via API (replace with your values)
curl -X PATCH "http://your-infrainsights-url/api/service-instances/kubernetes-1751174496165" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"config\": {
      \"kubeconfig\": $(jq -Rs . < kubeconfig-holmes.yaml)
    }
  }"
```

### Option C: Using InfraInsights CLI (if available)

```bash
infrainsights instances update kubernetes-1751174496165 \
  --kubeconfig-file kubeconfig-holmes.yaml
```

---

## Step 4: Verify the Fix

After updating InfraInsights:

### 4.1 Clear any caches

If InfraInsights has caching, wait 5 minutes or restart the InfraInsights service.

### 4.2 Test with HolmesGPT

Run an investigation that requires events:

```bash
# The logs should now show success instead of 403
# Look for these log lines:
✅ "Retrieved X events from raw API"
✅ "Successfully processed X events"

# Instead of:
❌ "API Exception in events: 403 - Forbidden"
```

---

## 📋 Verification Checklist

- [ ] Ran `debug_kubeconfig.py` and identified the current user/SA
- [ ] Generated new kubeconfig with `generate_sa_kubeconfig.sh`
- [ ] Tested the new kubeconfig locally:
  ```bash
  kubectl --kubeconfig=kubeconfig-holmes.yaml auth can-i list events --all-namespaces
  # Should return: yes
  ```
- [ ] Updated the instance in InfraInsights
- [ ] Waited for cache to clear (5 minutes)
- [ ] Tested HolmesGPT investigation
- [ ] Confirmed events are now accessible (no 403 error)

---

## 🔧 Alternative: Update Permissions for Existing User

If you **don't want to change the kubeconfig**, you can grant permissions to the existing user instead:

1. Run `debug_kubeconfig.py` to identify the current user/SA
2. Grant that user/SA the necessary permissions:

```bash
# If it's a service account:
kubectl create clusterrolebinding <name>-events-reader \
  --clusterrole=pod-wizardry-role \
  --serviceaccount=<namespace>:<service-account>

# If it's a user:
kubectl create clusterrolebinding <name>-events-reader \
  --clusterrole=pod-wizardry-role \
  --user=<username>
```

---

## 🐛 Troubleshooting

### Issue: "Service account has no secrets"

For Kubernetes >= 1.24, service accounts don't automatically get secrets. The script handles this by creating a token:

```bash
kubectl create token pod-wizardry-sa -n default --duration=8760h
```

### Issue: "Token expires"

If using `kubectl create token`, the token has an expiry. For production, consider:

1. Creating a permanent secret:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: pod-wizardry-sa-token
  namespace: default
  annotations:
    kubernetes.io/service-account.name: pod-wizardry-sa
type: kubernetes.io/service-account-token
```

2. Or set up a token rotation mechanism

### Issue: "Still getting 403 after update"

1. Check InfraInsights logs to see if it loaded the new config
2. Clear InfraInsights cache (restart or wait for TTL)
3. Verify the instance ID is correct: `kubernetes-1751174496165`
4. Double-check the kubeconfig is valid:
   ```bash
   kubectl --kubeconfig=kubeconfig-holmes.yaml get pods
   ```

---

## 📚 Additional Resources

- [Kubernetes RBAC Documentation](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [Service Account Tokens](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/)
- InfraInsights API Documentation (check your installation docs)

---

## 🎓 Understanding the Architecture

```
┌──────────────┐
│  HolmesGPT   │
└──────┬───────┘
       │
       │ 1. Request investigation
       ▼
┌──────────────────────┐
│   InfraInsights      │
│   ┌────────────────┐ │
│   │ Instance Store │ │
│   │  - ID: k8s-... │ │
│   │  - Name: multi │ │
│   │  - Config:     │ │
│   │    kubeconfig  │◄──── 2. Fetch instance & kubeconfig
│   └────────────────┘ │
└──────────────────────┘
       │
       │ 3. Use kubeconfig to connect
       ▼
┌──────────────────────┐
│  Kubernetes Cluster  │
│  ┌────────────────┐  │
│  │  API Server    │  │
│  │  RBAC Check    │  │◄── 4. Check permissions of kubeconfig user
│  │  Events API    │  │
│  └────────────────┘  │
└──────────────────────┘
       │
       │ 5. Return 403 if no permission
       │    Return events if permission exists
       ▼
    Result
```

**Key Point:** The RBAC check happens against the **user in the kubeconfig from InfraInsights**, not your local kubectl user.

---

## ✅ Success Indicators

After fixing, you should see logs like:

```
2025-10-15 XX:XX:XX INFO     ✅ Found instance by name: multitenant-prod
2025-10-15 XX:XX:XX INFO     🔍 Starting to fetch events for resource_type=pods
2025-10-15 XX:XX:XX INFO     🔍 Created Kubernetes client, fetching events using raw API...
2025-10-15 XX:XX:XX INFO     🔍 Retrieved 15 events from raw API
2025-10-15 XX:XX:XX INFO     🔍 Successfully processed 15 events
2025-10-15 XX:XX:XX INFO     🔍 Filtered to 3 events for pods/dap-hl7-tcp-receiver...
```

Instead of:

```
2025-10-15 XX:XX:XX ERROR    🔍 API Exception in events: 403 - Forbidden
```


