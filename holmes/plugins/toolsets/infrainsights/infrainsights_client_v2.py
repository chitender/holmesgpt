import requests
import logging
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

@dataclass
class InfraInsightsConfig:
    base_url: str
    api_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    timeout: int = 30
    enable_name_lookup: bool = True
    use_v2_api: bool = True

@dataclass 
class ServiceInstance:
    instanceId: str
    serviceType: str
    name: str
    description: str = ""
    environment: str = "production"
    status: str = "active"
    config: Dict[str, Any] = None
    ownerId: str = ""
    tags: List[str] = None
    healthCheck: Dict[str, Any] = None
    createdAt: str = ""
    updatedAt: str = ""

class InfraInsightsClientV2:
    """Updated InfraInsights client that supports name-based instance resolution"""
    
    def __init__(self, config: InfraInsightsConfig):
        self.config = config
        self.session = requests.Session()
        
        # Configure authentication
        if config.api_key:
            self.session.headers.update({
                'Authorization': f'Bearer {config.api_key}',
                'Content-Type': 'application/json'
            })
        elif config.username and config.password:
            self.session.auth = (config.username, config.password)
            self.session.headers.update({'Content-Type': 'application/json'})
        
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
        
        logger.info(f"InfraInsights Client V2 initialized - Name lookup: {config.enable_name_lookup}")

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to InfraInsights API"""
        url = f"{self.config.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        try:
            response = self.session.request(method, url, timeout=self.config.timeout, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"InfraInsights API request failed: {e}")
            raise Exception(f"Failed to connect to InfraInsights API: {e}")

    def health_check(self) -> bool:
        """Check if InfraInsights API is accessible"""
        try:
            logger.info(f"🔍 Health check: Calling {self.config.base_url}/api/health")
            response = self._make_request('GET', '/api/health')
            logger.info(f"🔍 Health check response: {response}")
            is_healthy = response.get('status') == 'healthy' or 'status' in response
            logger.info(f"🔍 Health check result: {'✅ Healthy' if is_healthy else '❌ Unhealthy'}")
            return is_healthy
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def get_service_instances(self, service_type: Optional[str] = None, user_id: Optional[str] = None) -> List[ServiceInstance]:
        """Get service instances, optionally filtered by type and user access"""
        cache_key = f"instances:{service_type}:{user_id}"
        
        # Check cache
        if cache_key in self._cache:
            cached_data, timestamp = self._cache[cache_key]
            if datetime.now() - timestamp < timedelta(seconds=self._cache_ttl):
                return cached_data

        try:
            # Build API endpoint
            if service_type:
                endpoint = f'/api/service-instances/{service_type}'
            else:
                endpoint = '/api/service-instances'
            
            # Make API request
            params = {}
            if user_id:
                params['userId'] = user_id
                
            data = self._make_request('GET', endpoint, params=params)
            
            # Parse response - handle both old and new response formats
            instances_data = data.get('data', data.get('instances', []))
            
            instances = []
            for instance_data in instances_data:
                try:
                    # Handle both old and new field names
                    instance = ServiceInstance(
                        instanceId=instance_data.get('instanceId', instance_data.get('id', '')),
                        serviceType=instance_data.get('serviceType', service_type or ''),
                        name=instance_data.get('name', ''),
                        description=instance_data.get('description', ''),
                        environment=instance_data.get('environment', 'production'),
                        status=instance_data.get('status', 'active'),
                        config=instance_data.get('config', {}),
                        ownerId=instance_data.get('ownerId', ''),
                        tags=instance_data.get('tags', []),
                        healthCheck=instance_data.get('healthCheck', {}),
                        createdAt=instance_data.get('createdAt', ''),
                        updatedAt=instance_data.get('updatedAt', '')
                    )
                    instances.append(instance)
                except Exception as e:
                    logger.warning(f"Failed to parse service instance: {e}")

            # Cache result
            self._cache[cache_key] = (instances, datetime.now())
            
            logger.info(f"Retrieved {len(instances)} {service_type or 'service'} instances")
            return instances
            
        except Exception as e:
            logger.error(f"Failed to get service instances: {e}")
            return []

    def get_instance_by_id(self, instance_id: str, include_config: bool = True) -> Optional[ServiceInstance]:
        """Get a specific instance by ID"""
        try:
            params = {'includeConfig': 'true'} if include_config else {}
            data = self._make_request('GET', f'/api/service-instances/{instance_id}', params=params)
            
            instance_data = data.get('data', data)
            if instance_data:
                return ServiceInstance(
                    instanceId=instance_data.get('instanceId', instance_data.get('id', '')),
                    serviceType=instance_data.get('serviceType', ''),
                    name=instance_data.get('name', ''),
                    description=instance_data.get('description', ''),
                    environment=instance_data.get('environment', 'production'),
                    status=instance_data.get('status', 'active'),
                    config=instance_data.get('config', {}),
                    ownerId=instance_data.get('ownerId', ''),
                    tags=instance_data.get('tags', []),
                    healthCheck=instance_data.get('healthCheck', {}),
                    createdAt=instance_data.get('createdAt', ''),
                    updatedAt=instance_data.get('updatedAt', '')
                )
            return None
        except Exception as e:
            logger.error(f"Failed to get instance by ID {instance_id}: {e}")
            return None

    def get_instance_by_name_and_type(self, service_type: str, name: str, include_config: bool = True) -> Optional[ServiceInstance]:
        """Get a specific instance by name and service type (NEW API ENDPOINT)"""
        if not self.config.enable_name_lookup:
            logger.warning("Name-based lookup is disabled")
            return None
            
        try:
            # Use the new backend endpoint that supports name lookup
            params = {'includeConfig': 'true'} if include_config else {}
            endpoint = f'/api/service-instances/{service_type}/{name}'
            
            logger.info(f"🔍 Constructing URL with service_type='{service_type}', name='{name}'")
            logger.info(f"🔍 Final endpoint: {endpoint}")
            logger.info(f"🔍 Full URL: {self.config.base_url}{endpoint}")
            data = self._make_request('GET', endpoint, params=params)
            
            # CRITICAL DEBUG: Show raw API response
            logger.info(f"🔍 RAW API RESPONSE: {json.dumps(data, indent=2)}")
            
            instance_data = data.get('data', data)
            if instance_data:
                # CRITICAL DEBUG: Show instance data before ServiceInstance creation
                logger.info(f"🔍 INSTANCE DATA: {json.dumps(instance_data, indent=2)}")
                logger.info(f"🔍 CONFIG IN INSTANCE DATA: {instance_data.get('config', {})}")
                instance = ServiceInstance(
                    instanceId=instance_data.get('instanceId', instance_data.get('id', '')),
                    serviceType=instance_data.get('serviceType', service_type),
                    name=instance_data.get('name', name),
                    description=instance_data.get('description', ''),
                    environment=instance_data.get('environment', 'production'),
                    status=instance_data.get('status', 'active'),
                    config=instance_data.get('config', {}),
                    ownerId=instance_data.get('ownerId', ''),
                    tags=instance_data.get('tags', []),
                    healthCheck=instance_data.get('healthCheck', {}),
                    createdAt=instance_data.get('createdAt', ''),
                    updatedAt=instance_data.get('updatedAt', '')
                )
                logger.info(f"✅ Found instance by name: {name} -> {instance.instanceId}")
                return instance
            return None
        except Exception as e:
            logger.error(f"Failed to get instance by name {name} in service type {service_type}: {e}")
            return None

    def resolve_instance(self, service_type: str, identifier: str, user_id: Optional[str] = None) -> Optional[ServiceInstance]:
        """
        Resolve an instance by identifier (could be ID or name)
        This method tries multiple strategies to find the instance
        """
        logger.info(f"Resolving {service_type} instance: '{identifier}'")
        
        # Strategy 1: Try direct ID lookup first
        try:
            instance = self.get_instance_by_id(identifier, include_config=True)
            if instance and instance.serviceType == service_type:
                logger.info(f"✅ Resolved by ID: {identifier}")
                return instance
        except Exception as e:
            logger.debug(f"ID lookup failed: {e}")

        # Strategy 2: Try name-based lookup (if enabled)
        if self.config.enable_name_lookup:
            try:
                instance = self.get_instance_by_name_and_type(service_type, identifier, include_config=True)
                if instance:
                    logger.info(f"✅ Resolved by name: {identifier} -> {instance.instanceId}")
                    return instance
            except Exception as e:
                logger.debug(f"Name lookup failed: {e}")

        # Strategy 3: Search through all instances of the service type
        try:
            instances = self.get_service_instances(service_type, user_id)
            
            # Try exact name match
            for instance in instances:
                if instance.name == identifier:
                    logger.info(f"✅ Resolved by search (exact name): {identifier}")
                    return instance
            
            # Try case-insensitive name match
            identifier_lower = identifier.lower()
            for instance in instances:
                if instance.name.lower() == identifier_lower:
                    logger.info(f"✅ Resolved by search (case-insensitive): {identifier}")
                    return instance
            
            # Try partial name match
            for instance in instances:
                if identifier_lower in instance.name.lower():
                    logger.info(f"✅ Resolved by search (partial match): {identifier} -> {instance.name}")
                    return instance
                    
        except Exception as e:
            logger.error(f"Search through instances failed: {e}")

        logger.warning(f"❌ Could not resolve instance: {identifier}")
        return None

    def identify_instance_from_prompt(self, prompt: str, service_type: str, user_id: Optional[str] = None) -> Optional[ServiceInstance]:
        """Identify instance from user prompt using smart parsing"""
        if not prompt:
            return None

        try:
            # Simple pattern matching for instance names
            import re
            
            # Enhanced patterns to capture instance names in various formats
            patterns = [
                # Specific name patterns with colons (highest priority)
                r'cluster_name:\s*([a-zA-Z0-9\-_]+)',
                r'instance_name:\s*([a-zA-Z0-9\-_]+)',
                r'service_name:\s*([a-zA-Z0-9\-_]+)',
                
                # Direct mentions with service types
                r'([a-zA-Z0-9\-_]+)\s+elasticsearch(?:\s+cluster)?',
                r'([a-zA-Z0-9\-_]+)\s+kafka(?:\s+cluster)?',
                r'([a-zA-Z0-9\-_]+)\s+mongodb(?:\s+cluster)?',
                r'([a-zA-Z0-9\-_]+)\s+redis(?:\s+cluster)?',
                r'([a-zA-Z0-9\-_]+)\s+kubernetes(?:\s+cluster)?',
                
                # "my" patterns
                r'my\s+([a-zA-Z0-9\-_]+)(?:\s+(?:instance|cluster|service))?',
                
                # Generic patterns (lower priority)
                r'(?:instance|cluster|service)\s+([a-zA-Z0-9\-_]+)',
                r'([a-zA-Z0-9\-_]{3,})(?:\s+(?:instance|cluster|service))',
            ]
            
            logger.info(f"🔍 Parsing prompt for {service_type} instance: '{prompt}'")
            
            for i, pattern in enumerate(patterns):
                matches = re.findall(pattern, prompt.lower())
                logger.info(f"🔍 Pattern {i+1}: '{pattern}' -> matches: {matches}")
                
                for match in matches:
                    if len(match) > 2:  # Skip very short matches
                        logger.info(f"🔍 Trying to resolve: '{match}'")
                        instance = self.resolve_instance(service_type, match, user_id)
                        if instance:
                            logger.info(f"✅ SUCCESS: Identified from prompt: '{match}' -> {instance.name}")
                            return instance
                        else:
                            logger.info(f"❌ No instance found for: '{match}'")
            
            return None
        except Exception as e:
            logger.error(f"Failed to identify instance from prompt: {e}")
            return None

    def get_service_instance_summary(self, service_type: str) -> Dict[str, Any]:
        """Get a summary of available instances for a service type"""
        try:
            instances = self.get_service_instances(service_type)
            
            summary = {
                "service_type": service_type,
                "total_instances": len(instances),
                "active_instances": len([i for i in instances if i.status == 'active']),
                "environments": list(set(i.environment for i in instances if i.environment)),
                "instance_names": [i.name for i in instances],
                "api_accessible": True,
                "name_lookup_enabled": self.config.enable_name_lookup
            }
            
            return summary
        except Exception as e:
            return {
                "service_type": service_type,
                "total_instances": 0,
                "active_instances": 0,
                "environments": [],
                "instance_names": [],
                "api_accessible": False,
                "name_lookup_enabled": self.config.enable_name_lookup,
                "error": str(e)
            }

    def get_elasticsearch_health(self, instance: ServiceInstance) -> Dict[str, Any]:
        """Get Elasticsearch/OpenSearch cluster health for a specific instance"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            es_url = instance.config.get('elasticsearchUrl')
            username = instance.config.get('username')
            password = instance.config.get('password')
            service_type = instance.config.get('type', 'elasticsearch').lower()
            
            if not es_url:
                raise Exception("Elasticsearch/OpenSearch URL not found in instance configuration")
            
            logger.info(f"🔍 Detected service type: {service_type}")
            
            # Configure client based on service type
            client_config = {
                'hosts': [es_url],
                'verify_certs': False,
                'request_timeout': 30
            }
            
            # Create appropriate client based on service type
            if service_type == 'opensearch':
                logger.info("🔍 Using OpenSearch client")
                try:
                    from opensearchpy import OpenSearch
                    
                    # OpenSearch client uses different auth parameter format
                    if username and password:
                        client_config['http_auth'] = (username, password)
                        logger.info(f"🔍 OpenSearch auth configured: username={username}")
                    
                    config_display = {k: ('***' if k == 'http_auth' else v) for k, v in client_config.items()}
                    logger.info(f"🔍 OpenSearch client config: {config_display}")
                    client = OpenSearch(**client_config)
                except ImportError:
                    logger.warning("OpenSearch client not available, falling back to direct HTTP requests")
                    # For OpenSearch, we can use requests directly or try compatibility mode
                    import requests
                    import json as json_lib
                    
                    # Use direct HTTP request for OpenSearch compatibility
                    auth = (username, password) if username and password else None
                    health_url = f"{es_url.rstrip('/')}/_cluster/health"
                    
                    response = requests.get(health_url, auth=auth, verify=False, timeout=30)
                    response.raise_for_status()
                    health_response = response.json()
                    
                    return {
                        'instance_name': instance.name,
                        'instance_id': instance.instanceId,
                        'cluster_name': health_response.get('cluster_name'),
                        'status': health_response.get('status'),
                        'number_of_nodes': health_response.get('number_of_nodes'),
                        'active_primary_shards': health_response.get('active_primary_shards'),
                        'active_shards': health_response.get('active_shards'),
                        'relocating_shards': health_response.get('relocating_shards'),
                        'initializing_shards': health_response.get('initializing_shards'),
                        'unassigned_shards': health_response.get('unassigned_shards'),
                        'delayed_unassigned_shards': health_response.get('delayed_unassigned_shards'),
                        'number_of_pending_tasks': health_response.get('number_of_pending_tasks'),
                        'number_of_in_flight_fetch': health_response.get('number_of_in_flight_fetch'),
                        'task_max_waiting_in_queue_millis': health_response.get('task_max_waiting_in_queue_millis'),
                        'active_shards_percent_as_number': health_response.get('active_shards_percent_as_number'),
                        'service_type': 'opensearch'
                    }
            else:
                logger.info("🔍 Using Elasticsearch client")
                from elasticsearch import Elasticsearch
                
                # Elasticsearch client uses basic_auth parameter
                if username and password:
                    client_config['basic_auth'] = (username, password)
                    logger.info(f"🔍 Elasticsearch auth configured: username={username}")
                
                config_display = {k: ('***' if k == 'basic_auth' else v) for k, v in client_config.items()}
                logger.info(f"🔍 Elasticsearch client config: {config_display}")
                client = Elasticsearch(**client_config)
            
            # Get cluster health using the appropriate client
            if service_type != 'opensearch' or 'client' in locals():
                health_response = client.cluster.health()
                
                return {
                    'instance_name': instance.name,
                    'instance_id': instance.instanceId,
                    'cluster_name': health_response.get('cluster_name'),
                    'status': health_response.get('status'),
                    'number_of_nodes': health_response.get('number_of_nodes'),
                    'active_primary_shards': health_response.get('active_primary_shards'),
                    'active_shards': health_response.get('active_shards'),
                    'relocating_shards': health_response.get('relocating_shards'),
                    'initializing_shards': health_response.get('initializing_shards'),
                    'unassigned_shards': health_response.get('unassigned_shards'),
                    'delayed_unassigned_shards': health_response.get('delayed_unassigned_shards'),
                    'number_of_pending_tasks': health_response.get('number_of_pending_tasks'),
                    'number_of_in_flight_fetch': health_response.get('number_of_in_flight_fetch'),
                    'task_max_waiting_in_queue_millis': health_response.get('task_max_waiting_in_queue_millis'),
                    'active_shards_percent_as_number': health_response.get('active_shards_percent_as_number'),
                    'service_type': service_type
                }
            
        except Exception as e:
            logger.error(f"Failed to get Elasticsearch/OpenSearch health for {instance.name}: {e}")
            raise Exception(f"Failed to get Elasticsearch/OpenSearch cluster health: {str(e)}")

    def get_elasticsearch_indices(self, instance: ServiceInstance) -> Dict[str, Any]:
        """Get Elasticsearch/OpenSearch indices for a specific instance"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            es_url = instance.config.get('elasticsearchUrl')
            username = instance.config.get('username')
            password = instance.config.get('password')
            service_type = instance.config.get('type', 'elasticsearch').lower()
            
            if not es_url:
                raise Exception("Elasticsearch/OpenSearch URL not found in instance configuration")
            
            logger.info(f"🔍 Detected service type: {service_type}")
            
            # Configure client based on service type
            client_config = {
                'hosts': [es_url],
                'verify_certs': False,
                'request_timeout': 30
            }
            
            # Create appropriate client based on service type
            if service_type == 'opensearch':
                logger.info("🔍 Using OpenSearch-compatible approach")
                try:
                    from opensearchpy import OpenSearch
                    
                    # OpenSearch client uses different auth parameter format
                    if username and password:
                        client_config['http_auth'] = (username, password)
                        logger.info(f"🔍 OpenSearch auth configured: username={username}")
                    
                    config_display = {k: ('***' if k == 'http_auth' else v) for k, v in client_config.items()}
                    logger.info(f"🔍 OpenSearch client config: {config_display}")
                    client = OpenSearch(**client_config)
                    indices_response = client.cat.indices(format='json', v=True)
                except ImportError:
                    logger.warning("OpenSearch client not available, using direct HTTP request")
                    # Use direct HTTP request for OpenSearch compatibility
                    import requests
                    
                    auth = (username, password) if username and password else None
                    indices_url = f"{es_url.rstrip('/')}/_cat/indices?format=json&v=true"
                    
                    response = requests.get(indices_url, auth=auth, verify=False, timeout=30)
                    response.raise_for_status()
                    indices_response = response.json()
            else:
                logger.info("🔍 Using Elasticsearch client")
                from elasticsearch import Elasticsearch
                
                # Elasticsearch client uses basic_auth parameter
                if username and password:
                    client_config['basic_auth'] = (username, password)
                    logger.info(f"🔍 Elasticsearch auth configured: username={username}")
                
                config_display = {k: ('***' if k == 'basic_auth' else v) for k, v in client_config.items()}
                logger.info(f"🔍 Elasticsearch client config: {config_display}")
                client = Elasticsearch(**client_config)
                indices_response = client.cat.indices(format='json', v=True)
            
            # Format indices data (same format for both)
            indices = []
            for index_info in indices_response:
                indices.append({
                    'index': index_info.get('index'),
                    'health': index_info.get('health'),
                    'status': index_info.get('status'),
                    'docs_count': index_info.get('docs.count'),
                    'docs_deleted': index_info.get('docs.deleted'),
                    'store_size': index_info.get('store.size'),
                    'pri_store_size': index_info.get('pri.store.size')
                })
            
            return {
                'instance_name': instance.name,
                'instance_id': instance.instanceId,
                'total_indices': len(indices),
                'indices': indices,
                'service_type': service_type
            }
            
        except Exception as e:
            logger.error(f"Failed to get Elasticsearch/OpenSearch indices for {instance.name}: {e}")
            raise Exception(f"Failed to get Elasticsearch/OpenSearch indices: {str(e)}")

    def get_elasticsearch_cluster_stats(self, instance: ServiceInstance) -> Dict[str, Any]:
        """Get Elasticsearch/OpenSearch cluster-wide statistics"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            es_url = instance.config.get('elasticsearchUrl')
            username = instance.config.get('username')
            password = instance.config.get('password')
            service_type = instance.config.get('type', 'elasticsearch').lower()
            
            if not es_url:
                raise Exception("Elasticsearch/OpenSearch URL not found in instance configuration")
            
            logger.info(f"🔍 Detected service type: {service_type}")
            
            # Configure client based on service type
            client_config = {
                'hosts': [es_url],
                'verify_certs': False,
                'request_timeout': 30
            }
            
            # Create appropriate client based on service type
            if service_type == 'opensearch':
                logger.info("🔍 Using OpenSearch-compatible approach")
                try:
                    from opensearchpy import OpenSearch
                    
                    # OpenSearch client uses different auth parameter format
                    if username and password:
                        client_config['http_auth'] = (username, password)
                    
                    client = OpenSearch(**client_config)
                    stats_response = client.cluster.stats()
                except ImportError:
                    logger.warning("OpenSearch client not available, using direct HTTP request")
                    import requests
                    
                    auth = (username, password) if username and password else None
                    stats_url = f"{es_url.rstrip('/')}/_cluster/stats"
                    
                    response = requests.get(stats_url, auth=auth, verify=False, timeout=30)
                    response.raise_for_status()
                    stats_response = response.json()
            else:
                logger.info("🔍 Using Elasticsearch client")
                from elasticsearch import Elasticsearch
                
                # Elasticsearch client uses basic_auth parameter
                if username and password:
                    client_config['basic_auth'] = (username, password)
                
                client = Elasticsearch(**client_config)
                stats_response = client.cluster.stats()
            
            return {
                'instance_name': instance.name,
                'instance_id': instance.instanceId,
                'cluster_stats': stats_response,
                'service_type': service_type
            }
            
        except Exception as e:
            logger.error(f"Failed to get Elasticsearch/OpenSearch cluster stats for {instance.name}: {e}")
            raise Exception(f"Failed to get Elasticsearch/OpenSearch cluster stats: {str(e)}")

    def get_elasticsearch_node_stats(self, instance: ServiceInstance) -> Dict[str, Any]:
        """Get Elasticsearch/OpenSearch node statistics"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            es_url = instance.config.get('elasticsearchUrl')
            username = instance.config.get('username')
            password = instance.config.get('password')
            service_type = instance.config.get('type', 'elasticsearch').lower()
            
            if not es_url:
                raise Exception("Elasticsearch/OpenSearch URL not found in instance configuration")
            
            logger.info(f"🔍 Detected service type: {service_type}")
            
            # Configure client based on service type
            client_config = {
                'hosts': [es_url],
                'verify_certs': False,
                'request_timeout': 30
            }
            
            # Create appropriate client based on service type
            if service_type == 'opensearch':
                logger.info("🔍 Using OpenSearch-compatible approach")
                try:
                    from opensearchpy import OpenSearch
                    
                    if username and password:
                        client_config['http_auth'] = (username, password)
                    
                    client = OpenSearch(**client_config)
                    stats_response = client.nodes.stats()
                except ImportError:
                    logger.warning("OpenSearch client not available, using direct HTTP request")
                    import requests
                    
                    auth = (username, password) if username and password else None
                    stats_url = f"{es_url.rstrip('/')}/_nodes/stats"
                    
                    response = requests.get(stats_url, auth=auth, verify=False, timeout=30)
                    response.raise_for_status()
                    stats_response = response.json()
            else:
                logger.info("🔍 Using Elasticsearch client")
                from elasticsearch import Elasticsearch
                
                if username and password:
                    client_config['basic_auth'] = (username, password)
                
                client = Elasticsearch(**client_config)
                stats_response = client.nodes.stats()
            
            return {
                'instance_name': instance.name,
                'instance_id': instance.instanceId,
                'node_stats': stats_response,
                'service_type': service_type
            }
            
        except Exception as e:
            logger.error(f"Failed to get Elasticsearch/OpenSearch node stats for {instance.name}: {e}")
            raise Exception(f"Failed to get Elasticsearch/OpenSearch node stats: {str(e)}")

    def get_elasticsearch_index_stats(self, instance: ServiceInstance, index_name: Optional[str] = None) -> Dict[str, Any]:
        """Get Elasticsearch/OpenSearch index statistics"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            es_url = instance.config.get('elasticsearchUrl')
            username = instance.config.get('username')
            password = instance.config.get('password')
            service_type = instance.config.get('type', 'elasticsearch').lower()
            
            if not es_url:
                raise Exception("Elasticsearch/OpenSearch URL not found in instance configuration")
            
            logger.info(f"🔍 Detected service type: {service_type}")
            
            # Configure client based on service type
            client_config = {
                'hosts': [es_url],
                'verify_certs': False,
                'request_timeout': 30
            }
            
            # Create appropriate client based on service type
            if service_type == 'opensearch':
                logger.info("🔍 Using OpenSearch-compatible approach")
                try:
                    from opensearchpy import OpenSearch
                    
                    if username and password:
                        client_config['http_auth'] = (username, password)
                    
                    client = OpenSearch(**client_config)
                    if index_name:
                        stats_response = client.indices.stats(index=index_name)
                    else:
                        stats_response = client.indices.stats()
                except ImportError:
                    logger.warning("OpenSearch client not available, using direct HTTP request")
                    import requests
                    
                    auth = (username, password) if username and password else None
                    if index_name:
                        stats_url = f"{es_url.rstrip('/')}/{index_name}/_stats"
                    else:
                        stats_url = f"{es_url.rstrip('/')}/_stats"
                    
                    response = requests.get(stats_url, auth=auth, verify=False, timeout=30)
                    response.raise_for_status()
                    stats_response = response.json()
            else:
                logger.info("🔍 Using Elasticsearch client")
                from elasticsearch import Elasticsearch
                
                if username and password:
                    client_config['basic_auth'] = (username, password)
                
                client = Elasticsearch(**client_config)
                if index_name:
                    stats_response = client.indices.stats(index=index_name)
                else:
                    stats_response = client.indices.stats()
            
            return {
                'instance_name': instance.name,
                'instance_id': instance.instanceId,
                'index_name': index_name or 'all',
                'index_stats': stats_response,
                'service_type': service_type
            }
            
        except Exception as e:
            logger.error(f"Failed to get Elasticsearch/OpenSearch index stats for {instance.name}: {e}")
            raise Exception(f"Failed to get Elasticsearch/OpenSearch index stats: {str(e)}")

    def get_elasticsearch_shard_allocation(self, instance: ServiceInstance, index_name: Optional[str] = None) -> Dict[str, Any]:
        """Get Elasticsearch/OpenSearch shard allocation information"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            es_url = instance.config.get('elasticsearchUrl')
            username = instance.config.get('username')
            password = instance.config.get('password')
            service_type = instance.config.get('type', 'elasticsearch').lower()
            
            if not es_url:
                raise Exception("Elasticsearch/OpenSearch URL not found in instance configuration")
            
            logger.info(f"🔍 Detected service type: {service_type}")
            
            # Configure client based on service type
            client_config = {
                'hosts': [es_url],
                'verify_certs': False,
                'request_timeout': 30
            }
            
            # Create appropriate client based on service type
            if service_type == 'opensearch':
                logger.info("🔍 Using OpenSearch-compatible approach")
                try:
                    from opensearchpy import OpenSearch
                    
                    if username and password:
                        client_config['http_auth'] = (username, password)
                    
                    client = OpenSearch(**client_config)
                    if index_name:
                        shards_response = client.cat.shards(index=index_name, format='json', v=True)
                    else:
                        shards_response = client.cat.shards(format='json', v=True)
                except ImportError:
                    logger.warning("OpenSearch client not available, using direct HTTP request")
                    import requests
                    
                    auth = (username, password) if username and password else None
                    if index_name:
                        shards_url = f"{es_url.rstrip('/')}/_cat/shards/{index_name}?v&format=json"
                    else:
                        shards_url = f"{es_url.rstrip('/')}/_cat/shards?v&format=json"
                    
                    response = requests.get(shards_url, auth=auth, verify=False, timeout=30)
                    response.raise_for_status()
                    shards_response = response.json()
            else:
                logger.info("🔍 Using Elasticsearch client")
                from elasticsearch import Elasticsearch
                
                if username and password:
                    client_config['basic_auth'] = (username, password)
                
                client = Elasticsearch(**client_config)
                if index_name:
                    shards_response = client.cat.shards(index=index_name, format='json', v=True)
                else:
                    shards_response = client.cat.shards(format='json', v=True)
            
            return {
                'instance_name': instance.name,
                'instance_id': instance.instanceId,
                'index_name': index_name or 'all',
                'shard_allocation': shards_response,
                'service_type': service_type
            }
            
        except Exception as e:
            logger.error(f"Failed to get Elasticsearch/OpenSearch shard allocation for {instance.name}: {e}")
            raise Exception(f"Failed to get Elasticsearch/OpenSearch shard allocation: {str(e)}")

    def get_elasticsearch_tasks(self, instance: ServiceInstance) -> Dict[str, Any]:
        """Get Elasticsearch/OpenSearch running tasks"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            es_url = instance.config.get('elasticsearchUrl')
            username = instance.config.get('username')
            password = instance.config.get('password')
            service_type = instance.config.get('type', 'elasticsearch').lower()
            
            if not es_url:
                raise Exception("Elasticsearch/OpenSearch URL not found in instance configuration")
            
            logger.info(f"🔍 Detected service type: {service_type}")
            
            # Configure client based on service type
            client_config = {
                'hosts': [es_url],
                'verify_certs': False,
                'request_timeout': 30
            }
            
            # Create appropriate client based on service type
            if service_type == 'opensearch':
                logger.info("🔍 Using OpenSearch-compatible approach")
                try:
                    from opensearchpy import OpenSearch
                    
                    if username and password:
                        client_config['http_auth'] = (username, password)
                    
                    client = OpenSearch(**client_config)
                    tasks_response = client.tasks.list(detailed=True)
                except ImportError:
                    logger.warning("OpenSearch client not available, using direct HTTP request")
                    import requests
                    
                    auth = (username, password) if username and password else None
                    tasks_url = f"{es_url.rstrip('/')}/_tasks?detailed"
                    
                    response = requests.get(tasks_url, auth=auth, verify=False, timeout=30)
                    response.raise_for_status()
                    tasks_response = response.json()
            else:
                logger.info("🔍 Using Elasticsearch client")
                from elasticsearch import Elasticsearch
                
                if username and password:
                    client_config['basic_auth'] = (username, password)
                
                client = Elasticsearch(**client_config)
                tasks_response = client.tasks.list(detailed=True)
            
            return {
                'instance_name': instance.name,
                'instance_id': instance.instanceId,
                'tasks': tasks_response,
                'service_type': service_type
            }
            
        except Exception as e:
            logger.error(f"Failed to get Elasticsearch/OpenSearch tasks for {instance.name}: {e}")
            raise Exception(f"Failed to get Elasticsearch/OpenSearch tasks: {str(e)}")

    def get_elasticsearch_pending_tasks(self, instance: ServiceInstance) -> Dict[str, Any]:
        """Get Elasticsearch/OpenSearch pending tasks"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            es_url = instance.config.get('elasticsearchUrl')
            username = instance.config.get('username')
            password = instance.config.get('password')
            service_type = instance.config.get('type', 'elasticsearch').lower()
            
            if not es_url:
                raise Exception("Elasticsearch/OpenSearch URL not found in instance configuration")
            
            logger.info(f"🔍 Detected service type: {service_type}")
            
            # Configure client based on service type
            client_config = {
                'hosts': [es_url],
                'verify_certs': False,
                'request_timeout': 30
            }
            
            # Create appropriate client based on service type
            if service_type == 'opensearch':
                logger.info("🔍 Using OpenSearch-compatible approach")
                try:
                    from opensearchpy import OpenSearch
                    
                    if username and password:
                        client_config['http_auth'] = (username, password)
                    
                    client = OpenSearch(**client_config)
                    pending_response = client.cluster.pending_tasks()
                except ImportError:
                    logger.warning("OpenSearch client not available, using direct HTTP request")
                    import requests
                    
                    auth = (username, password) if username and password else None
                    pending_url = f"{es_url.rstrip('/')}/_cluster/pending_tasks"
                    
                    response = requests.get(pending_url, auth=auth, verify=False, timeout=30)
                    response.raise_for_status()
                    pending_response = response.json()
            else:
                logger.info("🔍 Using Elasticsearch client")
                from elasticsearch import Elasticsearch
                
                if username and password:
                    client_config['basic_auth'] = (username, password)
                
                client = Elasticsearch(**client_config)
                pending_response = client.cluster.pending_tasks()
            
            return {
                'instance_name': instance.name,
                'instance_id': instance.instanceId,
                'pending_tasks': pending_response,
                'service_type': service_type
            }
            
        except Exception as e:
            logger.error(f"Failed to get Elasticsearch/OpenSearch pending tasks for {instance.name}: {e}")
            raise Exception(f"Failed to get Elasticsearch/OpenSearch pending tasks: {str(e)}")

    def get_elasticsearch_thread_pool_stats(self, instance: ServiceInstance) -> Dict[str, Any]:
        """Get Elasticsearch/OpenSearch thread pool statistics"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            es_url = instance.config.get('elasticsearchUrl')
            username = instance.config.get('username')
            password = instance.config.get('password')
            service_type = instance.config.get('type', 'elasticsearch').lower()
            
            if not es_url:
                raise Exception("Elasticsearch/OpenSearch URL not found in instance configuration")
            
            logger.info(f"🔍 Detected service type: {service_type}")
            
            # Configure client based on service type
            client_config = {
                'hosts': [es_url],
                'verify_certs': False,
                'request_timeout': 30
            }
            
            # Create appropriate client based on service type
            if service_type == 'opensearch':
                logger.info("🔍 Using OpenSearch-compatible approach")
                try:
                    from opensearchpy import OpenSearch
                    
                    if username and password:
                        client_config['http_auth'] = (username, password)
                    
                    client = OpenSearch(**client_config)
                    stats_response = client.nodes.stats(metric='thread_pool')
                except ImportError:
                    logger.warning("OpenSearch client not available, using direct HTTP request")
                    import requests
                    
                    auth = (username, password) if username and password else None
                    stats_url = f"{es_url.rstrip('/')}/_nodes/stats/thread_pool"
                    
                    response = requests.get(stats_url, auth=auth, verify=False, timeout=30)
                    response.raise_for_status()
                    stats_response = response.json()
            else:
                logger.info("🔍 Using Elasticsearch client")
                from elasticsearch import Elasticsearch
                
                if username and password:
                    client_config['basic_auth'] = (username, password)
                
                client = Elasticsearch(**client_config)
                stats_response = client.nodes.stats(metric='thread_pool')
            
            return {
                'instance_name': instance.name,
                'instance_id': instance.instanceId,
                'thread_pool_stats': stats_response,
                'service_type': service_type
            }
            
        except Exception as e:
            logger.error(f"Failed to get Elasticsearch/OpenSearch thread pool stats for {instance.name}: {e}")
            raise Exception(f"Failed to get Elasticsearch/OpenSearch thread pool stats: {str(e)}")

    def get_elasticsearch_index_mapping(self, instance: ServiceInstance, index_name: str) -> Dict[str, Any]:
        """Get Elasticsearch/OpenSearch index mapping"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            es_url = instance.config.get('elasticsearchUrl')
            username = instance.config.get('username')
            password = instance.config.get('password')
            service_type = instance.config.get('type', 'elasticsearch').lower()
            
            if not es_url:
                raise Exception("Elasticsearch/OpenSearch URL not found in instance configuration")
            
            logger.info(f"🔍 Detected service type: {service_type}")
            
            # Configure client based on service type
            client_config = {
                'hosts': [es_url],
                'verify_certs': False,
                'request_timeout': 30
            }
            
            # Create appropriate client based on service type
            if service_type == 'opensearch':
                logger.info("🔍 Using OpenSearch-compatible approach")
                try:
                    from opensearchpy import OpenSearch
                    
                    if username and password:
                        client_config['http_auth'] = (username, password)
                    
                    client = OpenSearch(**client_config)
                    mapping_response = client.indices.get_mapping(index=index_name)
                except ImportError:
                    logger.warning("OpenSearch client not available, using direct HTTP request")
                    import requests
                    
                    auth = (username, password) if username and password else None
                    mapping_url = f"{es_url.rstrip('/')}/{index_name}/_mapping"
                    
                    response = requests.get(mapping_url, auth=auth, verify=False, timeout=30)
                    response.raise_for_status()
                    mapping_response = response.json()
            else:
                logger.info("🔍 Using Elasticsearch client")
                from elasticsearch import Elasticsearch
                
                if username and password:
                    client_config['basic_auth'] = (username, password)
                
                client = Elasticsearch(**client_config)
                mapping_response = client.indices.get_mapping(index=index_name)
            
            return {
                'instance_name': instance.name,
                'instance_id': instance.instanceId,
                'index_name': index_name,
                'mapping': mapping_response,
                'service_type': service_type
            }
            
        except Exception as e:
            logger.error(f"Failed to get Elasticsearch/OpenSearch index mapping for {instance.name}: {e}")
            raise Exception(f"Failed to get Elasticsearch/OpenSearch index mapping: {str(e)}")

    def get_elasticsearch_index_settings(self, instance: ServiceInstance, index_name: str) -> Dict[str, Any]:
        """Get Elasticsearch/OpenSearch index settings"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            es_url = instance.config.get('elasticsearchUrl')
            username = instance.config.get('username')
            password = instance.config.get('password')
            service_type = instance.config.get('type', 'elasticsearch').lower()
            
            if not es_url:
                raise Exception("Elasticsearch/OpenSearch URL not found in instance configuration")
            
            logger.info(f"🔍 Detected service type: {service_type}")
            
            # Configure client based on service type
            client_config = {
                'hosts': [es_url],
                'verify_certs': False,
                'request_timeout': 30
            }
            
            # Create appropriate client based on service type
            if service_type == 'opensearch':
                logger.info("🔍 Using OpenSearch-compatible approach")
                try:
                    from opensearchpy import OpenSearch
                    
                    if username and password:
                        client_config['http_auth'] = (username, password)
                    
                    client = OpenSearch(**client_config)
                    settings_response = client.indices.get_settings(index=index_name)
                except ImportError:
                    logger.warning("OpenSearch client not available, using direct HTTP request")
                    import requests
                    
                    auth = (username, password) if username and password else None
                    settings_url = f"{es_url.rstrip('/')}/{index_name}/_settings"
                    
                    response = requests.get(settings_url, auth=auth, verify=False, timeout=30)
                    response.raise_for_status()
                    settings_response = response.json()
            else:
                logger.info("🔍 Using Elasticsearch client")
                from elasticsearch import Elasticsearch
                
                if username and password:
                    client_config['basic_auth'] = (username, password)
                
                client = Elasticsearch(**client_config)
                settings_response = client.indices.get_settings(index=index_name)
            
            return {
                'instance_name': instance.name,
                'instance_id': instance.instanceId,
                'index_name': index_name,
                'settings': settings_response,
                'service_type': service_type
            }
            
        except Exception as e:
            logger.error(f"Failed to get Elasticsearch/OpenSearch index settings for {instance.name}: {e}")
            raise Exception(f"Failed to get Elasticsearch/OpenSearch index settings: {str(e)}")

    def get_elasticsearch_hot_threads(self, instance: ServiceInstance, node_name: Optional[str] = None) -> Dict[str, Any]:
        """Get Elasticsearch/OpenSearch hot threads analysis"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            es_url = instance.config.get('elasticsearchUrl')
            username = instance.config.get('username')
            password = instance.config.get('password')
            service_type = instance.config.get('type', 'elasticsearch').lower()
            
            if not es_url:
                raise Exception("Elasticsearch/OpenSearch URL not found in instance configuration")
            
            logger.info(f"🔍 Detected service type: {service_type}")
            
            # Configure client based on service type
            client_config = {
                'hosts': [es_url],
                'verify_certs': False,
                'request_timeout': 30
            }
            
            # Create appropriate client based on service type
            if service_type == 'opensearch':
                logger.info("🔍 Using OpenSearch-compatible approach")
                try:
                    from opensearchpy import OpenSearch
                    
                    if username and password:
                        client_config['http_auth'] = (username, password)
                    
                    client = OpenSearch(**client_config)
                    if node_name:
                        hot_threads_response = client.nodes.hot_threads(node_id=node_name, threads=3)
                    else:
                        hot_threads_response = client.nodes.hot_threads(threads=3)
                except ImportError:
                    logger.warning("OpenSearch client not available, using direct HTTP request")
                    import requests
                    
                    auth = (username, password) if username and password else None
                    if node_name:
                        hot_threads_url = f"{es_url.rstrip('/')}/_nodes/{node_name}/hot_threads?threads=3"
                    else:
                        hot_threads_url = f"{es_url.rstrip('/')}/_nodes/hot_threads?threads=3"
                    
                    response = requests.get(hot_threads_url, auth=auth, verify=False, timeout=30)
                    response.raise_for_status()
                    hot_threads_response = response.text  # Hot threads returns text, not JSON
            else:
                logger.info("🔍 Using Elasticsearch client")
                from elasticsearch import Elasticsearch
                
                if username and password:
                    client_config['basic_auth'] = (username, password)
                
                client = Elasticsearch(**client_config)
                if node_name:
                    hot_threads_response = client.nodes.hot_threads(node_id=node_name, threads=3)
                else:
                    hot_threads_response = client.nodes.hot_threads(threads=3)
            
            return {
                'instance_name': instance.name,
                'instance_id': instance.instanceId,
                'node_name': node_name or 'all',
                'hot_threads': hot_threads_response,
                'service_type': service_type
            }
            
        except Exception as e:
            logger.error(f"Failed to get Elasticsearch/OpenSearch hot threads for {instance.name}: {e}")
            raise Exception(f"Failed to get Elasticsearch/OpenSearch hot threads: {str(e)}")

    def get_elasticsearch_snapshot_status(self, instance: ServiceInstance) -> Dict[str, Any]:
        """Get Elasticsearch/OpenSearch snapshot status"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            es_url = instance.config.get('elasticsearchUrl')
            username = instance.config.get('username')
            password = instance.config.get('password')
            service_type = instance.config.get('type', 'elasticsearch').lower()
            
            if not es_url:
                raise Exception("Elasticsearch/OpenSearch URL not found in instance configuration")
            
            logger.info(f"🔍 Detected service type: {service_type}")
            
            # Configure client based on service type
            client_config = {
                'hosts': [es_url],
                'verify_certs': False,
                'request_timeout': 30
            }
            
            # Create appropriate client based on service type
            if service_type == 'opensearch':
                logger.info("🔍 Using OpenSearch-compatible approach")
                try:
                    from opensearchpy import OpenSearch
                    
                    if username and password:
                        client_config['http_auth'] = (username, password)
                    
                    client = OpenSearch(**client_config)
                    snapshot_response = client.snapshot.status()
                except ImportError:
                    logger.warning("OpenSearch client not available, using direct HTTP request")
                    import requests
                    
                    auth = (username, password) if username and password else None
                    snapshot_url = f"{es_url.rstrip('/')}/_snapshot/_status"
                    
                    response = requests.get(snapshot_url, auth=auth, verify=False, timeout=30)
                    response.raise_for_status()
                    snapshot_response = response.json()
            else:
                logger.info("🔍 Using Elasticsearch client")
                from elasticsearch import Elasticsearch
                
                if username and password:
                    client_config['basic_auth'] = (username, password)
                
                client = Elasticsearch(**client_config)
                snapshot_response = client.snapshot.status()
            
            return {
                'instance_name': instance.name,
                'instance_id': instance.instanceId,
                'snapshot_status': snapshot_response,
                'service_type': service_type
            }
            
        except Exception as e:
            logger.error(f"Failed to get Elasticsearch/OpenSearch snapshot status for {instance.name}: {e}")
            raise Exception(f"Failed to get Elasticsearch/OpenSearch snapshot status: {str(e)}")

    # MongoDB client methods
    def get_mongodb_health(self, instance: ServiceInstance) -> Dict[str, Any]:
        """Get MongoDB instance health and server status"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            connection_string = instance.config.get('connectionString')
            database = instance.config.get('database', 'admin')
            
            if not connection_string:
                raise Exception("MongoDB connection string not found in instance configuration")
            
            logger.info(f"🔍 Connecting to MongoDB instance: {instance.name}")
            
            try:
                from pymongo import MongoClient
                from pymongo.errors import ServerSelectionTimeoutError, OperationFailure
                
                # Parse connection string and create client
                client = MongoClient(connection_string, serverSelectionTimeoutMS=30000)
                
                # Test connection and get server status
                db = client[database]
                server_status = db.command("serverStatus")
                is_master = db.command("isMaster")
                
                # Get basic health metrics
                health_data = {
                    'instance_name': instance.name,
                    'instance_id': instance.instanceId,
                    'connection_status': 'healthy',
                    'server_status': {
                        'version': server_status.get('version'),
                        'uptime': server_status.get('uptime'),
                        'connections': server_status.get('connections'),
                        'mem': server_status.get('mem'),
                        'extra_info': server_status.get('extra_info'),
                        'host': server_status.get('host'),
                        'process': server_status.get('process')
                    },
                    'replica_set_status': {
                        'ismaster': is_master.get('ismaster'),
                        'secondary': is_master.get('secondary'),
                        'setName': is_master.get('setName'),
                        'hosts': is_master.get('hosts', []),
                        'primary': is_master.get('primary')
                    },
                    'timestamp': server_status.get('localTime')
                }
                
                client.close()
                return health_data
                
            except ImportError:
                raise Exception("pymongo library not available. Please install: pip install pymongo")
            except ServerSelectionTimeoutError:
                raise Exception("Failed to connect to MongoDB server - timeout")
            except OperationFailure as e:
                raise Exception(f"MongoDB operation failed: {str(e)}")
            
        except Exception as e:
            logger.error(f"Failed to get MongoDB health for {instance.name}: {e}")
            raise Exception(f"Failed to get MongoDB health: {str(e)}")

    def get_mongodb_databases(self, instance: ServiceInstance) -> Dict[str, Any]:
        """Get list of databases in MongoDB instance"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            connection_string = instance.config.get('connectionString')
            
            if not connection_string:
                raise Exception("MongoDB connection string not found in instance configuration")
            
            logger.info(f"🔍 Getting databases for MongoDB instance: {instance.name}")
            
            try:
                from pymongo import MongoClient
                
                client = MongoClient(connection_string, serverSelectionTimeoutMS=30000)
                
                # List all databases
                db_list = client.list_database_names()
                
                databases_info = []
                for db_name in db_list:
                    db = client[db_name]
                    try:
                        stats = db.command("dbStats")
                        db_info = {
                            'name': db_name,
                            'sizeOnDisk': stats.get('storageSize', 0),
                            'dataSize': stats.get('dataSize', 0),
                            'indexSize': stats.get('indexSize', 0),
                            'collections': stats.get('collections', 0),
                            'objects': stats.get('objects', 0),
                            'avgObjSize': stats.get('avgObjSize', 0),
                            'indexes': stats.get('indexes', 0)
                        }
                        databases_info.append(db_info)
                    except Exception as e:
                        # Some databases might not allow dbStats
                        databases_info.append({
                            'name': db_name,
                            'error': f"Unable to get stats: {str(e)}"
                        })
                
                client.close()
                
                return {
                    'instance_name': instance.name,
                    'instance_id': instance.instanceId,
                    'total_databases': len(databases_info),
                    'databases': databases_info
                }
                
            except ImportError:
                raise Exception("pymongo library not available. Please install: pip install pymongo")
            
        except Exception as e:
            logger.error(f"Failed to get MongoDB databases for {instance.name}: {e}")
            raise Exception(f"Failed to get MongoDB databases: {str(e)}")

    def get_mongodb_collection_stats(self, instance: ServiceInstance, database_name: str, collection_name: Optional[str] = None) -> Dict[str, Any]:
        """Get MongoDB collection statistics"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            connection_string = instance.config.get('connectionString')
            
            if not connection_string:
                raise Exception("MongoDB connection string not found in instance configuration")
            
            logger.info(f"🔍 Getting collection stats for MongoDB instance: {instance.name}, database: {database_name}")
            
            try:
                from pymongo import MongoClient
                
                client = MongoClient(connection_string, serverSelectionTimeoutMS=30000)
                db = client[database_name]
                
                collections_stats = []
                
                if collection_name:
                    # Get stats for specific collection
                    collection_names = [collection_name]
                else:
                    # Get stats for all collections
                    collection_names = db.list_collection_names()
                
                for coll_name in collection_names:
                    try:
                        collection = db[coll_name]
                        stats = db.command("collStats", coll_name)
                        
                        # Get index information
                        indexes = list(collection.list_indexes())
                        
                        coll_stats = {
                            'name': coll_name,
                            'count': stats.get('count', 0),
                            'size': stats.get('size', 0),
                            'storageSize': stats.get('storageSize', 0),
                            'totalIndexSize': stats.get('totalIndexSize', 0),
                            'avgObjSize': stats.get('avgObjSize', 0),
                            'nindexes': stats.get('nindexes', 0),
                            'indexes': [
                                {
                                    'name': idx.get('name'),
                                    'key': idx.get('key'),
                                    'unique': idx.get('unique', False),
                                    'sparse': idx.get('sparse', False)
                                } for idx in indexes
                            ]
                        }
                        collections_stats.append(coll_stats)
                        
                    except Exception as e:
                        collections_stats.append({
                            'name': coll_name,
                            'error': f"Unable to get stats: {str(e)}"
                        })
                
                client.close()
                
                return {
                    'instance_name': instance.name,
                    'instance_id': instance.instanceId,
                    'database_name': database_name,
                    'collection_name': collection_name or 'all',
                    'total_collections': len(collections_stats),
                    'collections': collections_stats
                }
                
            except ImportError:
                raise Exception("pymongo library not available. Please install: pip install pymongo")
            
        except Exception as e:
            logger.error(f"Failed to get MongoDB collection stats for {instance.name}: {e}")
            raise Exception(f"Failed to get MongoDB collection stats: {str(e)}")

    def get_mongodb_performance_metrics(self, instance: ServiceInstance) -> Dict[str, Any]:
        """Get MongoDB performance metrics and server statistics"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            connection_string = instance.config.get('connectionString')
            database = instance.config.get('database', 'admin')
            
            if not connection_string:
                raise Exception("MongoDB connection string not found in instance configuration")
            
            logger.info(f"🔍 Getting performance metrics for MongoDB instance: {instance.name}")
            
            try:
                from pymongo import MongoClient
                
                client = MongoClient(connection_string, serverSelectionTimeoutMS=30000)
                db = client[database]
                
                # Get comprehensive server status
                server_status = db.command("serverStatus")
                
                # Extract key performance metrics
                performance_metrics = {
                    'instance_name': instance.name,
                    'instance_id': instance.instanceId,
                    'opcounters': server_status.get('opcounters', {}),
                    'opcountersRepl': server_status.get('opcountersRepl', {}),
                    'connections': server_status.get('connections', {}),
                    'memory': server_status.get('mem', {}),
                    'globalLock': server_status.get('globalLock', {}),
                    'locks': server_status.get('locks', {}),
                    'network': server_status.get('network', {}),
                    'metrics': {
                        'cursor': server_status.get('metrics', {}).get('cursor', {}),
                        'document': server_status.get('metrics', {}).get('document', {}),
                        'operation': server_status.get('metrics', {}).get('operation', {}),
                        'queryExecutor': server_status.get('metrics', {}).get('queryExecutor', {}),
                        'repl': server_status.get('metrics', {}).get('repl', {})
                    },
                    'wiredTiger': server_status.get('wiredTiger', {}),
                    'extra_info': server_status.get('extra_info', {}),
                    'timestamp': server_status.get('localTime')
                }
                
                client.close()
                return performance_metrics
                
            except ImportError:
                raise Exception("pymongo library not available. Please install: pip install pymongo")
            
        except Exception as e:
            logger.error(f"Failed to get MongoDB performance metrics for {instance.name}: {e}")
            raise Exception(f"Failed to get MongoDB performance metrics: {str(e)}")

    def get_mongodb_slow_queries(self, instance: ServiceInstance, database_name: Optional[str] = None, slow_threshold_ms: int = 100) -> Dict[str, Any]:
        """Get MongoDB slow queries analysis"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            connection_string = instance.config.get('connectionString')
            admin_db = instance.config.get('database', 'admin')
            
            if not connection_string:
                raise Exception("MongoDB connection string not found in instance configuration")
            
            logger.info(f"🔍 Analyzing slow queries for MongoDB instance: {instance.name}")
            
            try:
                from pymongo import MongoClient
                
                client = MongoClient(connection_string, serverSelectionTimeoutMS=30000)
                
                # Set profiling level to capture slow operations
                if database_name:
                    databases = [database_name]
                else:
                    databases = client.list_database_names()
                
                slow_queries_data = {
                    'instance_name': instance.name,
                    'instance_id': instance.instanceId,
                    'slow_threshold_ms': slow_threshold_ms,
                    'databases_analyzed': [],
                    'total_slow_queries': 0
                }
                
                for db_name in databases:
                    if db_name in ['admin', 'local', 'config']:
                        continue
                        
                    try:
                        db = client[db_name]
                        
                        # Check current profiling status
                        profile_status = db.command("profile", -1)
                        
                        # Get profiler data if available
                        if 'system.profile' in db.list_collection_names():
                            profile_collection = db['system.profile']
                            
                            # Query for slow operations
                            slow_ops = list(profile_collection.find({
                                'millis': {'$gte': slow_threshold_ms}
                            }).sort('ts', -1).limit(50))
                            
                            db_analysis = {
                                'database': db_name,
                                'profiling_level': profile_status.get('was'),
                                'slow_operations_count': len(slow_ops),
                                'slow_operations': [
                                    {
                                        'timestamp': op.get('ts'),
                                        'operation': op.get('op'),
                                        'namespace': op.get('ns'),
                                        'duration_ms': op.get('millis'),
                                        'command': op.get('command', {}),
                                        'docsExamined': op.get('docsExamined'),
                                        'docsReturned': op.get('docsReturned'),
                                        'planSummary': op.get('planSummary')
                                    } for op in slow_ops
                                ]
                            }
                            
                            slow_queries_data['databases_analyzed'].append(db_analysis)
                            slow_queries_data['total_slow_queries'] += len(slow_ops)
                        
                    except Exception as e:
                        slow_queries_data['databases_analyzed'].append({
                            'database': db_name,
                            'error': f"Unable to analyze: {str(e)}"
                        })
                
                client.close()
                return slow_queries_data
                
            except ImportError:
                raise Exception("pymongo library not available. Please install: pip install pymongo")
            
        except Exception as e:
            logger.error(f"Failed to analyze MongoDB slow queries for {instance.name}: {e}")
            raise Exception(f"Failed to analyze MongoDB slow queries: {str(e)}")

    def get_mongodb_index_analysis(self, instance: ServiceInstance, database_name: str, collection_name: Optional[str] = None) -> Dict[str, Any]:
        """Get MongoDB index analysis and optimization recommendations"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            connection_string = instance.config.get('connectionString')
            
            if not connection_string:
                raise Exception("MongoDB connection string not found in instance configuration")
            
            logger.info(f"🔍 Analyzing indexes for MongoDB instance: {instance.name}, database: {database_name}")
            
            try:
                from pymongo import MongoClient
                
                client = MongoClient(connection_string, serverSelectionTimeoutMS=30000)
                db = client[database_name]
                
                if collection_name:
                    collection_names = [collection_name]
                else:
                    collection_names = db.list_collection_names()
                
                index_analysis = {
                    'instance_name': instance.name,
                    'instance_id': instance.instanceId,
                    'database_name': database_name,
                    'collection_name': collection_name or 'all',
                    'collections_analyzed': []
                }
                
                for coll_name in collection_names:
                    try:
                        collection = db[coll_name]
                        
                        # Get all indexes
                        indexes = list(collection.list_indexes())
                        
                        # Get index usage statistics if available
                        try:
                            index_stats = db.command("collStats", coll_name, indexDetails=True)
                        except:
                            index_stats = {}
                        
                        collection_analysis = {
                            'collection': coll_name,
                            'total_indexes': len(indexes),
                            'indexes': [
                                {
                                    'name': idx.get('name'),
                                    'key': idx.get('key'),
                                    'unique': idx.get('unique', False),
                                    'sparse': idx.get('sparse', False),
                                    'partialFilterExpression': idx.get('partialFilterExpression'),
                                    'expireAfterSeconds': idx.get('expireAfterSeconds'),
                                    'background': idx.get('background', False)
                                } for idx in indexes
                            ],
                            'recommendations': []
                        }
                        
                        # Add basic recommendations
                        if len(indexes) == 1:  # Only _id index
                            collection_analysis['recommendations'].append(
                                "Consider adding indexes for frequently queried fields"
                            )
                        elif len(indexes) > 10:
                            collection_analysis['recommendations'].append(
                                "High number of indexes detected - review if all are necessary"
                            )
                        
                        index_analysis['collections_analyzed'].append(collection_analysis)
                        
                    except Exception as e:
                        index_analysis['collections_analyzed'].append({
                            'collection': coll_name,
                            'error': f"Unable to analyze: {str(e)}"
                        })
                
                client.close()
                return index_analysis
                
            except ImportError:
                raise Exception("pymongo library not available. Please install: pip install pymongo")
            
        except Exception as e:
            logger.error(f"Failed to analyze MongoDB indexes for {instance.name}: {e}")
            raise Exception(f"Failed to analyze MongoDB indexes: {str(e)}")

    def get_mongodb_replica_set_status(self, instance: ServiceInstance) -> Dict[str, Any]:
        """Get MongoDB replica set status and configuration"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            connection_string = instance.config.get('connectionString')
            database = instance.config.get('database', 'admin')
            
            if not connection_string:
                raise Exception("MongoDB connection string not found in instance configuration")
            
            logger.info(f"🔍 Getting replica set status for MongoDB instance: {instance.name}")
            
            try:
                from pymongo import MongoClient
                
                client = MongoClient(connection_string, serverSelectionTimeoutMS=30000)
                db = client[database]
                
                try:
                    # Get replica set status
                    rs_status = db.command("replSetGetStatus")
                    rs_config = db.command("replSetGetConfig")
                    
                    replica_set_data = {
                        'instance_name': instance.name,
                        'instance_id': instance.instanceId,
                        'replica_set_name': rs_status.get('set'),
                        'status': {
                            'ok': rs_status.get('ok'),
                            'date': rs_status.get('date'),
                            'myState': rs_status.get('myState'),
                            'term': rs_status.get('term'),
                            'heartbeatIntervalMillis': rs_status.get('heartbeatIntervalMillis')
                        },
                        'members': [
                            {
                                'name': member.get('name'),
                                'health': member.get('health'),
                                'state': member.get('state'),
                                'stateStr': member.get('stateStr'),
                                'uptime': member.get('uptime'),
                                'optimeDate': member.get('optimeDate'),
                                'lastHeartbeat': member.get('lastHeartbeat'),
                                'lastHeartbeatRecv': member.get('lastHeartbeatRecv'),
                                'pingMs': member.get('pingMs'),
                                'electionTime': member.get('electionTime'),
                                'electionDate': member.get('electionDate')
                            } for member in rs_status.get('members', [])
                        ],
                        'config': {
                            'version': rs_config.get('config', {}).get('version'),
                            'members': [
                                {
                                    'id': member.get('_id'),
                                    'host': member.get('host'),
                                    'priority': member.get('priority'),
                                    'votes': member.get('votes'),
                                    'arbiterOnly': member.get('arbiterOnly', False),
                                    'hidden': member.get('hidden', False)
                                } for member in rs_config.get('config', {}).get('members', [])
                            ]
                        }
                    }
                    
                except Exception as rs_error:
                    # Not a replica set or no access
                    replica_set_data = {
                        'instance_name': instance.name,
                        'instance_id': instance.instanceId,
                        'replica_set_status': 'standalone_or_no_access',
                        'error': str(rs_error)
                    }
                
                client.close()
                return replica_set_data
                
            except ImportError:
                raise Exception("pymongo library not available. Please install: pip install pymongo")
            
        except Exception as e:
            logger.error(f"Failed to get MongoDB replica set status for {instance.name}: {e}")
            raise Exception(f"Failed to get MongoDB replica set status: {str(e)}")

    def get_mongodb_connection_analysis(self, instance: ServiceInstance) -> Dict[str, Any]:
        """Get MongoDB connection analysis and statistics"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            connection_string = instance.config.get('connectionString')
            database = instance.config.get('database', 'admin')
            
            if not connection_string:
                raise Exception("MongoDB connection string not found in instance configuration")
            
            logger.info(f"🔍 Analyzing connections for MongoDB instance: {instance.name}")
            
            try:
                from pymongo import MongoClient
                
                client = MongoClient(connection_string, serverSelectionTimeoutMS=30000)
                db = client[database]
                
                # Get server status for connection info
                server_status = db.command("serverStatus")
                
                # Get current operations to see active connections
                try:
                    current_ops = db.command("currentOp", True)
                except:
                    current_ops = {'inprog': []}
                
                connections_data = {
                    'instance_name': instance.name,
                    'instance_id': instance.instanceId,
                    'connection_stats': server_status.get('connections', {}),
                    'network_stats': server_status.get('network', {}),
                    'active_operations': len(current_ops.get('inprog', [])),
                    'operations_by_type': {},
                    'operations_by_client': {},
                    'long_running_operations': []
                }
                
                # Analyze current operations
                for op in current_ops.get('inprog', []):
                    op_type = op.get('op', 'unknown')
                    client_addr = op.get('client', 'unknown')
                    duration = op.get('secs_running', 0)
                    
                    # Count by operation type
                    connections_data['operations_by_type'][op_type] = connections_data['operations_by_type'].get(op_type, 0) + 1
                    
                    # Count by client
                    connections_data['operations_by_client'][client_addr] = connections_data['operations_by_client'].get(client_addr, 0) + 1
                    
                    # Track long-running operations (>30 seconds)
                    if duration > 30:
                        connections_data['long_running_operations'].append({
                            'operation': op_type,
                            'duration_seconds': duration,
                            'client': client_addr,
                            'description': op.get('desc', ''),
                            'namespace': op.get('ns', '')
                        })
                
                client.close()
                return connections_data
                
            except ImportError:
                raise Exception("pymongo library not available. Please install: pip install pymongo")
            
        except Exception as e:
            logger.error(f"Failed to analyze MongoDB connections for {instance.name}: {e}")
            raise Exception(f"Failed to analyze MongoDB connections: {str(e)}")

    def get_mongodb_operations_analysis(self, instance: ServiceInstance, operation_threshold_ms: int = 1000) -> Dict[str, Any]:
        """Get MongoDB operations analysis and current operations"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            connection_string = instance.config.get('connectionString')
            database = instance.config.get('database', 'admin')
            
            if not connection_string:
                raise Exception("MongoDB connection string not found in instance configuration")
            
            logger.info(f"🔍 Analyzing operations for MongoDB instance: {instance.name}")
            
            try:
                from pymongo import MongoClient
                
                client = MongoClient(connection_string, serverSelectionTimeoutMS=30000)
                db = client[database]
                
                # Get current operations
                try:
                    current_ops = db.command("currentOp", True)
                except:
                    current_ops = {'inprog': []}
                
                # Get server status for operation counters
                server_status = db.command("serverStatus")
                
                operations_data = {
                    'instance_name': instance.name,
                    'instance_id': instance.instanceId,
                    'operation_threshold_ms': operation_threshold_ms,
                    'total_active_operations': len(current_ops.get('inprog', [])),
                    'operation_counters': server_status.get('opcounters', {}),
                    'operation_counters_repl': server_status.get('opcountersRepl', {}),
                    'current_operations': [],
                    'long_running_operations': [],
                    'operations_by_type': {},
                    'operations_by_database': {}
                }
                
                # Analyze current operations
                for op in current_ops.get('inprog', []):
                    op_info = {
                        'opid': op.get('opid'),
                        'operation': op.get('op'),
                        'namespace': op.get('ns'),
                        'duration_seconds': op.get('secs_running', 0),
                        'client': op.get('client'),
                        'description': op.get('desc'),
                        'command': op.get('command', {}),
                        'waiting_for_lock': op.get('waitingForLock', False),
                        'lock_stats': op.get('lockStats', {})
                    }
                    
                    operations_data['current_operations'].append(op_info)
                    
                    # Count by type
                    op_type = op.get('op', 'unknown')
                    operations_data['operations_by_type'][op_type] = operations_data['operations_by_type'].get(op_type, 0) + 1
                    
                    # Count by database
                    namespace = op.get('ns', '')
                    if '.' in namespace:
                        db_name = namespace.split('.')[0]
                        operations_data['operations_by_database'][db_name] = operations_data['operations_by_database'].get(db_name, 0) + 1
                    
                    # Track long-running operations
                    duration_ms = op.get('secs_running', 0) * 1000
                    if duration_ms >= operation_threshold_ms:
                        operations_data['long_running_operations'].append(op_info)
                
                client.close()
                return operations_data
                
            except ImportError:
                raise Exception("pymongo library not available. Please install: pip install pymongo")
            
        except Exception as e:
            logger.error(f"Failed to analyze MongoDB operations for {instance.name}: {e}")
            raise Exception(f"Failed to analyze MongoDB operations: {str(e)}")

    def get_mongodb_security_audit(self, instance: ServiceInstance) -> Dict[str, Any]:
        """Perform MongoDB security audit and best practices check"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            connection_string = instance.config.get('connectionString')
            database = instance.config.get('database', 'admin')
            
            if not connection_string:
                raise Exception("MongoDB connection string not found in instance configuration")
            
            logger.info(f"🔍 Performing security audit for MongoDB instance: {instance.name}")
            
            try:
                from pymongo import MongoClient
                
                client = MongoClient(connection_string, serverSelectionTimeoutMS=30000)
                db = client[database]
                
                security_audit = {
                    'instance_name': instance.name,
                    'instance_id': instance.instanceId,
                    'authentication': {},
                    'authorization': {},
                    'encryption': {},
                    'security_recommendations': [],
                    'compliance_checks': {}
                }
                
                # Check authentication mechanism
                try:
                    build_info = db.command("buildInfo")
                    security_audit['authentication']['mongodb_version'] = build_info.get('version')
                    
                    # Check if authentication is enabled
                    try:
                        users = db.command("usersInfo")
                        security_audit['authentication']['auth_enabled'] = True
                        security_audit['authentication']['total_users'] = len(users.get('users', []))
                    except:
                        security_audit['authentication']['auth_enabled'] = False
                        security_audit['security_recommendations'].append(
                            "Authentication is not enabled - consider enabling authentication"
                        )
                    
                    # Check SSL/TLS
                    server_status = db.command("serverStatus")
                    security_audit['encryption']['ssl_mode'] = server_status.get('transportSecurity', {}).get('mode', 'disabled')
                    
                    if security_audit['encryption']['ssl_mode'] == 'disabled':
                        security_audit['security_recommendations'].append(
                            "SSL/TLS encryption is not enabled - consider enabling for data in transit"
                        )
                    
                    # Check for default database names
                    db_names = client.list_database_names()
                    if 'test' in db_names:
                        security_audit['security_recommendations'].append(
                            "Default 'test' database exists - consider removing if not needed"
                        )
                    
                    # Basic compliance checks
                    security_audit['compliance_checks'] = {
                        'authentication_enabled': security_audit['authentication']['auth_enabled'],
                        'encryption_in_transit': security_audit['encryption']['ssl_mode'] != 'disabled',
                        'no_default_databases': 'test' not in db_names,
                        'mongodb_version_supported': True  # Would need to check against EOL versions
                    }
                    
                except Exception as audit_error:
                    security_audit['error'] = f"Security audit incomplete: {str(audit_error)}"
                
                client.close()
                return security_audit
                
            except ImportError:
                raise Exception("pymongo library not available. Please install: pip install pymongo")
            
        except Exception as e:
            logger.error(f"Failed to perform MongoDB security audit for {instance.name}: {e}")
            raise Exception(f"Failed to perform MongoDB security audit: {str(e)}")

    def get_mongodb_backup_analysis(self, instance: ServiceInstance) -> Dict[str, Any]:
        """Analyze MongoDB backup status and strategies"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            connection_string = instance.config.get('connectionString')
            database = instance.config.get('database', 'admin')
            
            if not connection_string:
                raise Exception("MongoDB connection string not found in instance configuration")
            
            logger.info(f"🔍 Analyzing backup status for MongoDB instance: {instance.name}")
            
            try:
                from pymongo import MongoClient
                
                client = MongoClient(connection_string, serverSelectionTimeoutMS=30000)
                db = client[database]
                
                backup_analysis = {
                    'instance_name': instance.name,
                    'instance_id': instance.instanceId,
                    'backup_recommendations': [],
                    'point_in_time_recovery': {},
                    'storage_analysis': {}
                }
                
                # Check if oplog exists (needed for point-in-time recovery)
                try:
                    oplog_stats = db.command("collStats", "oplog.rs")
                    backup_analysis['point_in_time_recovery'] = {
                        'oplog_available': True,
                        'oplog_size_mb': oplog_stats.get('size', 0) / (1024 * 1024),
                        'oplog_max_size_mb': oplog_stats.get('maxSize', 0) / (1024 * 1024),
                        'oplog_usage_percent': (oplog_stats.get('size', 0) / max(oplog_stats.get('maxSize', 1), 1)) * 100
                    }
                    
                    if backup_analysis['point_in_time_recovery']['oplog_usage_percent'] > 80:
                        backup_analysis['backup_recommendations'].append(
                            "Oplog usage is high - consider increasing oplog size for better point-in-time recovery"
                        )
                        
                except:
                    backup_analysis['point_in_time_recovery'] = {
                        'oplog_available': False
                    }
                    backup_analysis['backup_recommendations'].append(
                        "Oplog not available - point-in-time recovery may not be possible"
                    )
                
                # Get storage information
                try:
                    db_stats = db.command("dbStats")
                    backup_analysis['storage_analysis'] = {
                        'data_size_mb': db_stats.get('dataSize', 0) / (1024 * 1024),
                        'storage_size_mb': db_stats.get('storageSize', 0) / (1024 * 1024),
                        'index_size_mb': db_stats.get('indexSize', 0) / (1024 * 1024),
                        'total_collections': db_stats.get('collections', 0)
                    }
                except:
                    pass
                
                # Add general backup recommendations
                backup_analysis['backup_recommendations'].extend([
                    "Implement regular automated backups",
                    "Test backup restoration procedures regularly",
                    "Store backups in geographically distributed locations",
                    "Monitor backup success and failure rates",
                    "Document backup and recovery procedures"
                ])
                
                client.close()
                return backup_analysis
                
            except ImportError:
                raise Exception("pymongo library not available. Please install: pip install pymongo")
            
        except Exception as e:
            logger.error(f"Failed to analyze MongoDB backup status for {instance.name}: {e}")
            raise Exception(f"Failed to analyze MongoDB backup status: {str(e)}")

    def get_mongodb_capacity_planning(self, instance: ServiceInstance, projection_days: int = 30) -> Dict[str, Any]:
        """Analyze MongoDB capacity and provide growth projections"""
        try:
            if not instance.config:
                raise Exception("Instance configuration not available")
            
            connection_string = instance.config.get('connectionString')
            
            if not connection_string:
                raise Exception("MongoDB connection string not found in instance configuration")
            
            logger.info(f"🔍 Analyzing capacity planning for MongoDB instance: {instance.name}")
            
            try:
                from pymongo import MongoClient
                from datetime import datetime, timedelta
                
                client = MongoClient(connection_string, serverSelectionTimeoutMS=30000)
                
                capacity_analysis = {
                    'instance_name': instance.name,
                    'instance_id': instance.instanceId,
                    'projection_days': projection_days,
                    'current_usage': {},
                    'database_breakdown': [],
                    'growth_projections': {},
                    'capacity_recommendations': []
                }
                
                # Get current storage usage
                total_data_size = 0
                total_storage_size = 0
                total_index_size = 0
                
                db_names = client.list_database_names()
                
                for db_name in db_names:
                    if db_name in ['admin', 'local', 'config']:
                        continue
                    
                    try:
                        db = client[db_name]
                        db_stats = db.command("dbStats")
                        
                        db_info = {
                            'database': db_name,
                            'data_size_mb': db_stats.get('dataSize', 0) / (1024 * 1024),
                            'storage_size_mb': db_stats.get('storageSize', 0) / (1024 * 1024),
                            'index_size_mb': db_stats.get('indexSize', 0) / (1024 * 1024),
                            'collections': db_stats.get('collections', 0),
                            'objects': db_stats.get('objects', 0)
                        }
                        
                        capacity_analysis['database_breakdown'].append(db_info)
                        
                        total_data_size += db_info['data_size_mb']
                        total_storage_size += db_info['storage_size_mb']
                        total_index_size += db_info['index_size_mb']
                        
                    except Exception as e:
                        capacity_analysis['database_breakdown'].append({
                            'database': db_name,
                            'error': f"Unable to get stats: {str(e)}"
                        })
                
                capacity_analysis['current_usage'] = {
                    'total_data_size_mb': total_data_size,
                    'total_storage_size_mb': total_storage_size,
                    'total_index_size_mb': total_index_size,
                    'total_size_mb': total_data_size + total_index_size,
                    'storage_efficiency_percent': (total_data_size / max(total_storage_size, 1)) * 100
                }
                
                # Simple growth projection (would be more sophisticated with historical data)
                # Assume 10% monthly growth as baseline
                monthly_growth_rate = 0.10
                daily_growth_rate = monthly_growth_rate / 30
                
                projected_size = total_data_size * (1 + (daily_growth_rate * projection_days))
                
                capacity_analysis['growth_projections'] = {
                    'current_size_mb': total_data_size,
                    'projected_size_mb': projected_size,
                    'growth_mb': projected_size - total_data_size,
                    'growth_percent': ((projected_size - total_data_size) / max(total_data_size, 1)) * 100,
                    'projection_date': (datetime.now() + timedelta(days=projection_days)).isoformat()
                }
                
                # Add capacity recommendations
                if capacity_analysis['current_usage']['storage_efficiency_percent'] < 50:
                    capacity_analysis['capacity_recommendations'].append(
                        "Low storage efficiency detected - consider running compact operations"
                    )
                
                if projected_size > total_data_size * 2:
                    capacity_analysis['capacity_recommendations'].append(
                        f"High growth projected - plan for {projected_size:.1f}MB capacity in {projection_days} days"
                    )
                
                capacity_analysis['capacity_recommendations'].extend([
                    "Monitor storage usage trends regularly",
                    "Plan for at least 20% buffer above projected usage",
                    "Consider archiving old data if growth is unsustainable",
                    "Review index usage and optimize if necessary"
                ])
                
                client.close()
                return capacity_analysis
                
            except ImportError:
                raise Exception("pymongo library not available. Please install: pip install pymongo")
            
        except Exception as e:
            logger.error(f"Failed to analyze MongoDB capacity planning for {instance.name}: {e}")
            raise Exception(f"Failed to analyze MongoDB capacity planning: {str(e)}") 