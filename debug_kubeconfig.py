#!/usr/bin/env python3
"""
Debug script to check the kubeconfig stored in InfraInsights
"""
import os
import sys
import yaml
import json
import base64
from holmes.plugins.toolsets.infrainsights.infrainsights_client_v2 import (
    InfraInsightsClientV2,
    InfraInsightsConfig
)

# Configuration - UPDATE THESE VALUES
INFRAINSIGHTS_BASE_URL = os.getenv("INFRAINSIGHTS_URL", "http://your-infrainsights-url")
INFRAINSIGHTS_API_KEY = os.getenv("INFRAINSIGHTS_API_KEY", "your-api-key")
INSTANCE_NAME = "multitenant-prod"

def main():
    print("🔍 Debugging InfraInsights Kubeconfig...")
    print(f"   Base URL: {INFRAINSIGHTS_BASE_URL}")
    print(f"   Instance: {INSTANCE_NAME}\n")
    
    # Create InfraInsights client
    config = InfraInsightsConfig(
        base_url=INFRAINSIGHTS_BASE_URL,
        api_key=INFRAINSIGHTS_API_KEY,
        enable_name_lookup=True,
        use_v2_api=True
    )
    
    client = InfraInsightsClientV2(config)
    
    # Get all kubernetes instances
    print("📋 Fetching kubernetes instances...")
    instances = client.get_service_instances(service_type='kubernetes')
    
    if not instances:
        print("❌ No kubernetes instances found!")
        return 1
    
    print(f"✅ Found {len(instances)} kubernetes instance(s):")
    for inst in instances:
        print(f"   - {inst.name} (ID: {inst.instanceId})")
    print()
    
    # Find the specific instance
    target_instance = None
    for inst in instances:
        if inst.name == INSTANCE_NAME:
            target_instance = inst
            break
    
    if not target_instance:
        print(f"❌ Instance '{INSTANCE_NAME}' not found!")
        print(f"   Available instances: {[i.name for i in instances]}")
        return 1
    
    print(f"🎯 Found target instance: {target_instance.name}")
    print(f"   Instance ID: {target_instance.instanceId}")
    print(f"   Service Type: {target_instance.serviceType}")
    print()
    
    # Check kubeconfig
    if not target_instance.config:
        print("❌ No config found for this instance!")
        return 1
    
    if 'kubeconfig' not in target_instance.config:
        print("❌ No kubeconfig found in instance config!")
        print(f"   Available config keys: {list(target_instance.config.keys())}")
        return 1
    
    kubeconfig_data = target_instance.config['kubeconfig']
    print("✅ Kubeconfig found!")
    print(f"   Length: {len(kubeconfig_data)} characters\n")
    
    # Parse kubeconfig
    try:
        kubeconfig = yaml.safe_load(kubeconfig_data)
        print("📄 Kubeconfig Structure:")
        print(f"   Clusters: {len(kubeconfig.get('clusters', []))}")
        print(f"   Contexts: {len(kubeconfig.get('contexts', []))}")
        print(f"   Users: {len(kubeconfig.get('users', []))}")
        print(f"   Current Context: {kubeconfig.get('current-context', 'NOT SET')}\n")
        
        # Show user details
        print("👤 User Authentication Details:")
        for user in kubeconfig.get('users', []):
            user_name = user.get('name')
            user_info = user.get('user', {})
            print(f"\n   User: {user_name}")
            
            # Check auth method
            if 'client-certificate-data' in user_info:
                print("     ✅ Using client certificate authentication")
                # Try to decode and show subject
                try:
                    cert_data = base64.b64decode(user_info['client-certificate-data'])
                    # You could use cryptography library here to parse cert
                    print("     Certificate data present")
                except Exception as e:
                    print(f"     Could not decode cert: {e}")
            
            if 'token' in user_info:
                print("     ✅ Using token authentication")
                token = user_info['token']
                print(f"     Token length: {len(token)} chars")
                print(f"     Token prefix: {token[:20]}...")
                
                # Try to decode service account token
                if '.' in token:
                    try:
                        parts = token.split('.')
                        payload = base64.b64decode(parts[1] + '==')
                        token_data = json.loads(payload)
                        print(f"     Service Account: {token_data.get('kubernetes.io/serviceaccount/service-account.name', 'N/A')}")
                        print(f"     Namespace: {token_data.get('kubernetes.io/serviceaccount/namespace', 'N/A')}")
                    except Exception as e:
                        print(f"     Could not decode token: {e}")
            
            if 'username' in user_info:
                print(f"     ✅ Using basic auth - Username: {user_info['username']}")
            
            if 'exec' in user_info:
                print("     ✅ Using exec plugin authentication")
                print(f"     Command: {user_info['exec'].get('command')}")
            
            if not any(k in user_info for k in ['client-certificate-data', 'token', 'username', 'exec']):
                print("     ⚠️  No authentication method found!")
        
        # Show current context details
        current_context = kubeconfig.get('current-context')
        if current_context:
            print(f"\n🎯 Current Context: {current_context}")
            for ctx in kubeconfig.get('contexts', []):
                if ctx.get('name') == current_context:
                    print(f"   User: {ctx.get('context', {}).get('user')}")
                    print(f"   Cluster: {ctx.get('context', {}).get('cluster')}")
                    print(f"   Namespace: {ctx.get('context', {}).get('namespace', 'default')}")
        
        print("\n" + "="*80)
        print("\n📋 FULL KUBECONFIG (sanitized):")
        print("="*80)
        
        # Sanitize sensitive data
        sanitized = yaml.safe_load(kubeconfig_data)
        for user in sanitized.get('users', []):
            user_info = user.get('user', {})
            if 'client-certificate-data' in user_info:
                user_info['client-certificate-data'] = '<REDACTED>'
            if 'client-key-data' in user_info:
                user_info['client-key-data'] = '<REDACTED>'
            if 'token' in user_info:
                user_info['token'] = '<REDACTED>'
            if 'password' in user_info:
                user_info['password'] = '<REDACTED>'
        
        print(yaml.dump(sanitized, default_flow_style=False))
        
    except Exception as e:
        print(f"❌ Failed to parse kubeconfig: {e}")
        return 1
    
    print("\n" + "="*80)
    print("🔧 RECOMMENDED ACTION:")
    print("="*80)
    print("""
1. Check if the user/service account in the kubeconfig has events permissions
   Run this command on your cluster (replace USER_NAME with the user from above):
   
   kubectl auth can-i list events --as=USER_NAME
   
   For service accounts, use:
   kubectl auth can-i list events --as=system:serviceaccount:NAMESPACE:SA_NAME

2. If it returns 'no', you need to either:
   a) Grant the existing user/SA permissions, OR
   b) Update the kubeconfig in InfraInsights to use pod-wizardry-sa

3. To update the kubeconfig in InfraInsights:
   - Generate a new kubeconfig with pod-wizardry-sa credentials
   - Update the instance in InfraInsights with the new kubeconfig
    """)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())


