# Fixes Applied - October 15, 2025

## 1. Docker Build Issue - Helm Installation ✅

**Problem:** Docker build failed with DNS resolution error for `baltocdn.com`
```
curl: (6) Could not resolve host: baltocdn.com
```

**Fix:** Replaced APT-based Helm installation with direct binary download from `get.helm.sh`
- More reliable (single network call)
- Faster (no APT repository updates)
- Platform-aware (arm64/amd64)
- Version pinned (v3.16.3)

**File Modified:** `Dockerfile` (lines 60-74)

---

## 2. Runtime Error - SupabaseDal Missing Client ✅

**Problem:** `AttributeError: 'SupabaseDal' object has no attribute 'client'`

**Root Cause:** When Robusta tokens aren't configured, `self.enabled = False` and `self.client` is never created, but `get_global_instructions_for_account()` tried to access it.

**Fix:** Added guard clause to check if client exists before use:
```python
def get_global_instructions_for_account(self) -> Optional[Instructions]:
    if not self.enabled or not hasattr(self, 'client'):
        return None
    # ... rest of method
```

**File Modified:** `holmes/core/supabase_dal.py` (line 384-385)

---

## 3. Runtime Error - Issue Object Missing Subject Attribute ✅

**Problem:** `jinja2.exceptions.UndefinedError: 'holmes.core.issue.Issue object' has no attribute 'subject'`

**Root Cause:** The Jinja2 template was accessing `issue.subject.name` but the `Issue` model doesn't have a `subject` attribute. According to the API spec, `subject` is part of the request payload stored in `issue.raw`.

**Fix:** Updated template to access nested data with fallbacks:
- `issue.subject.name` → `issue.raw.subject.name if issue.raw and issue.raw.subject else issue.name`
- `issue.subject.namespace` → `issue.raw.subject.namespace if issue.raw and issue.raw.subject and issue.raw.subject.namespace else 'N/A'`

**File Modified:** `holmes/plugins/prompts/alert_investigation_with_routing.jinja2` (lines 10-11, 43)

---

## 4. Tool Validation Error - Inconsistent Resource Kind Names ✅

**Problem:** 
```
"error": "Unsupported resource kind: pods. Supported kinds: pod, service, deployment"
```

**Root Cause:** Inconsistency between Kubernetes tools:
- `kubernetes_list_resources` expected **plural**: `pods`, `services`, `deployments`
- `kubernetes_describe_resource` expected **singular**: `pod`, `service`, `deployment`
- LLM was using both forms interchangeably

**Fix:** Added kind normalization to accept both singular and plural forms in both tools:

```python
# In _list_resources: normalize to plural
kind_mapping = {
    "pod": "pods", "pods": "pods",
    "service": "services", "services": "services", "svc": "services",
    "deployment": "deployments", "deployments": "deployments", "deploy": "deployments"
}

# In _describe_resource: normalize to singular  
kind_mapping = {
    "pods": "pod", "pod": "pod",
    "services": "service", "service": "service", "svc": "service",
    "deployments": "deployment", "deployment": "deployment", "deploy": "deployment"
}
```

**Files Modified:** `holmes/plugins/toolsets/infrainsights/comprehensive_kubernetes_toolset.py`
- Lines 466-477 (_list_resources)
- Lines 693-704 (_describe_resource)

**Updated error messages** to reflect both forms are supported:
- Old: `"Supported kinds: pod, service, deployment"`
- New: `"Supported kinds: pod/pods, service/services/svc, deployment/deployments/deploy"`

---

## 5. RBAC Permission Issue - Events Access Forbidden ⚠️

**Problem:**
```
"events": "Access to events for resource 'pods/...' in namespace '...' is forbidden. Check permissions."
```

**Status:** This is NOT a code bug - it's a Kubernetes RBAC configuration issue.

**Root Cause:** The service account used by HolmesGPT doesn't have permissions to read Kubernetes events.

**Solution:** 

**If using Helm:** The permissions are already defined in `helm/holmes/templates/holmesgpt-service-account.yaml` (line 33). The ClusterRole includes:
```yaml
- apiGroups: [""]
  resources: ["events", ...]
  verbs: ["get", "list", "watch"]
```

**If NOT using Helm or using custom kubeconfig:** Ensure your service account has events permissions:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: holmesgpt-events-reader
rules:
- apiGroups: [""]
  resources: ["events"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["events.k8s.io"]
  resources: ["events"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: holmesgpt-events-reader-binding
subjects:
- kind: ServiceAccount
  name: YOUR-SERVICE-ACCOUNT-NAME  # Replace with your service account name
  namespace: YOUR-NAMESPACE  # Replace with your namespace
roleRef:
  kind: ClusterRole
  name: holmesgpt-events-reader
  apiGroup: rbac.authorization.k8s.io
```

**Troubleshooting Steps:**
1. Verify which service account is being used: `kubectl get pods -n YOUR-NAMESPACE -o jsonpath='{.items[*].spec.serviceAccountName}'`
2. Check if the service account has events permissions: `kubectl auth can-i list events --as=system:serviceaccount:YOUR-NAMESPACE:YOUR-SA-NAME`
3. If using custom kubeconfig, ensure it has the necessary RBAC roles bound

**Code Behavior:** The code already handles this gracefully - it returns a clear error message instead of crashing.

---

## Summary

✅ **Fixed Issues:**
1. Docker build failure (Helm installation)
2. SupabaseDal client attribute error
3. Issue.subject attribute error
4. Kubernetes resource kind validation inconsistency

⚠️ **Configuration Needed:**
1. Grant Kubernetes events read permissions to HolmesGPT service account

## Testing Recommendations

1. **Rebuild Docker image** - Should complete without DNS errors
2. **Test without Robusta token** - Should not crash on global instructions lookup
3. **Test with investigation requests** - Templates should render correctly
4. **Test with both singular/plural kinds** - Both should work now:
   - `kubectl_describe pods` ✅
   - `kubectl_describe pod` ✅
   - `kubernetes_list_resources(kind="pod")` ✅
   - `kubernetes_list_resources(kind="pods")` ✅
5. **Grant events permissions** - Then retry investigations that need event access

