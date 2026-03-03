import logging
from typing import Dict, List, Any, Optional

from holmes.core.tools import Toolset

logger = logging.getLogger(__name__)

# Import enhanced toolsets
from .enhanced_elasticsearch_toolset import EnhancedElasticsearchToolset
from .enhanced_mongodb_toolset import EnhancedMongoDBToolset
from .enhanced_redis_toolset import EnhancedRedisToolset
from .comprehensive_kafka_toolset import ComprehensiveKafkaToolset
from .comprehensive_kafka_connect_toolset import InfraInsightsKafkaConnectToolset
from .kfuse_tempo_toolset import KfuseTempoToolset
from .comprehensive_kubernetes_toolset import InfraInsightsKubernetesToolset

# List of available toolsets - used by the loader
AVAILABLE_TOOLSETS = {
    'enhanced_elasticsearch': EnhancedElasticsearchToolset,
    'enhanced_mongodb': EnhancedMongoDBToolset,
    'enhanced_redis': EnhancedRedisToolset,
    'comprehensive_kafka': ComprehensiveKafkaToolset,
    'comprehensive_kafka_connect': InfraInsightsKafkaConnectToolset,
    'kfuse_tempo': KfuseTempoToolset,
    'infrainsights_kubernetes': InfraInsightsKubernetesToolset,
}

def get_infrainsights_toolsets(config: Dict[str, Any] = None) -> List[Toolset]:
    """
    Get all available InfraInsights toolsets
    
    Config can be either:
    1. Direct toolset config dict: { "mongodb": { "enabled": True, "config": {...} } }
    2. Full toolsets dict from Helm: { "infrainsights_mongodb_enhanced": { "enabled": True, "config": {...} } }
    """
    toolsets = []
    
    if config is None:
        config = {}
    
    # Helper to extract config from toolset entry (handles both direct and nested structures)
    def get_toolset_config(toolset_name_variations: List[str]) -> Optional[Dict[str, Any]]:
        """Get toolset config, checking multiple key variations"""
        for key in toolset_name_variations:
            toolset_entry = config.get(key, {})
            if toolset_entry and isinstance(toolset_entry, dict):
                # Skip custom toolset entries (they have 'type': 'custom' but no InfraInsights config)
                # Only skip if it's a custom toolset AND doesn't have a nested 'config' key with InfraInsights settings
                if toolset_entry.get('type') == 'custom':
                    # Check if it has a nested config with InfraInsights settings
                    nested_config = toolset_entry.get('config', {})
                    if isinstance(nested_config, dict) and 'infrainsights_url' in nested_config:
                        # This custom toolset has InfraInsights config nested inside - use it
                        logger.debug(f"🔍 Found custom toolset '{key}' with nested InfraInsights config")
                    elif 'infrainsights_url' not in toolset_entry:
                        # This is a pure custom toolset, not an InfraInsights toolset
                        logger.debug(f"🔍 Skipping custom toolset entry '{key}' (not an InfraInsights toolset)")
                        continue
                
                # Check if enabled (default to True if not specified)
                if not toolset_entry.get('enabled', True):
                    continue
                
                # If entry has a 'config' key, use that; otherwise use the whole entry
                # This handles both: { "config": {...} } and { "infrainsights_url": ... }
                if 'config' in toolset_entry and isinstance(toolset_entry['config'], dict):
                    logger.debug(f"🔍 Found InfraInsights toolset '{key}' with nested config")
                    return toolset_entry['config']
                elif 'infrainsights_url' in toolset_entry:
                    # Flat structure with InfraInsights config
                    logger.debug(f"🔍 Found InfraInsights toolset '{key}' with flat config")
                    return toolset_entry
                else:
                    # Entry exists but doesn't look like InfraInsights config
                    logger.debug(f"🔍 Entry '{key}' exists but doesn't contain InfraInsights config")
        return None
    
    # Enhanced Elasticsearch toolset - check multiple key variations
    elasticsearch_configs = [
        get_toolset_config(['elasticsearch', 'infrainsights_elasticsearch', 'infrainsights_elasticsearch_enhanced']),
        config.get('elasticsearch', {})
    ]
    
    for es_config in elasticsearch_configs:
        if not es_config:
            continue
        # Handle both nested config structure and flat structure
        if 'config' in es_config and isinstance(es_config['config'], dict):
            actual_config = es_config['config']
        elif 'infrainsights_url' in es_config or 'enabled' in es_config:
            actual_config = es_config
        else:
            continue
        
        if actual_config.get('enabled', True):
            try:
                elasticsearch_toolset = EnhancedElasticsearchToolset()
                elasticsearch_toolset.configure(actual_config)
                toolsets.append(elasticsearch_toolset)
                logger.info("✅ Enhanced Elasticsearch toolset loaded")
                break
            except Exception as e:
                logger.error(f"❌ Failed to load Enhanced Elasticsearch toolset: {e}")
    
    # Enhanced MongoDB toolset - check multiple key variations
    # Note: 'mongodb' might be a custom toolset, so prioritize InfraInsights-specific keys
    mongodb_configs = [
        get_toolset_config(['infrainsights_mongodb_enhanced', 'infrainsights_mongodb', 'mongodb']),
    ]
    
    for mongo_config in mongodb_configs:
        if not mongo_config:
            continue
        # Handle both nested config structure and flat structure
        if 'config' in mongo_config and isinstance(mongo_config['config'], dict):
            # Nested: { "enabled": True, "config": { "infrainsights_url": ... } }
            actual_config = mongo_config['config']
        elif 'infrainsights_url' in mongo_config or 'enabled' in mongo_config:
            # Flat: { "infrainsights_url": ... } or already processed
            actual_config = mongo_config
        else:
            continue
        
        if actual_config.get('enabled', True):  # Default to enabled if not specified
            try:
                mongodb_toolset = EnhancedMongoDBToolset()
                mongodb_toolset.configure(actual_config)
                toolsets.append(mongodb_toolset)
                logger.info("✅ Enhanced MongoDB toolset loaded")
                break
            except Exception as e:
                logger.error(f"❌ Failed to load Enhanced MongoDB toolset: {e}")
    
    # Enhanced Redis toolset - support multiple config key variations
    # Note: 'redis' might be a custom toolset, so prioritize InfraInsights-specific keys
    redis_configs = [
        get_toolset_config(['infrainsights_redis_enhanced', 'infrainsights_redis', 'redis']),
    ]
    
    for redis_config in redis_configs:
        if not redis_config:
            continue
        # Handle both nested config structure and flat structure
        if 'config' in redis_config and isinstance(redis_config['config'], dict):
            actual_config = redis_config['config']
        elif 'infrainsights_url' in redis_config or 'enabled' in redis_config:
            actual_config = redis_config
        else:
            continue
        
        if actual_config.get('enabled', True):
            try:
                redis_toolset = EnhancedRedisToolset()
                redis_toolset.configure(actual_config)
                toolsets.append(redis_toolset)
                logger.info("✅ Enhanced Redis toolset loaded")
                break  # Only load one instance of Redis toolset
            except Exception as e:
                logger.error(f"❌ Failed to load Enhanced Redis toolset: {e}")
    
    # Comprehensive Kafka toolset - support multiple config key variations
    kafka_configs = [
        get_toolset_config(['kafka', 'infrainsights_kafka', 'infrainsights_kafka_enhanced', 'infrainsights_kafka_comprehensive']),
        config.get('kafka', {}),
        config.get('infrainsights_kafka', {}),
        config.get('infrainsights_kafka_comprehensive', {})
    ]
    
    for kafka_config in kafka_configs:
        if not kafka_config:
            continue
        # Handle both nested config structure and flat structure
        if 'config' in kafka_config and isinstance(kafka_config['config'], dict):
            actual_config = kafka_config['config']
        elif 'infrainsights_url' in kafka_config or 'enabled' in kafka_config:
            actual_config = kafka_config
        else:
            continue
        
        if actual_config.get('enabled', True):
            try:
                kafka_toolset = ComprehensiveKafkaToolset()
                kafka_toolset.configure(actual_config)
                toolsets.append(kafka_toolset)
                logger.info("✅ Comprehensive Kafka toolset loaded")
                break  # Only load one instance of Kafka toolset
            except Exception as e:
                logger.error(f"❌ Failed to load Comprehensive Kafka toolset: {e}")
    
    # Comprehensive Kafka Connect toolset - support multiple config key variations
    kafka_connect_configs = [
        config.get('kafka_connect', {}),
        config.get('infrainsights_kafka_connect', {}),
        config.get('comprehensive_kafka_connect', {})
    ]
    
    for kafka_connect_config in kafka_connect_configs:
        if not kafka_connect_config:
            continue
        # Handle both nested config structure and flat structure
        if 'config' in kafka_connect_config and isinstance(kafka_connect_config['config'], dict):
            actual_config = kafka_connect_config['config']
        elif 'infrainsights_url' in kafka_connect_config or 'enabled' in kafka_connect_config:
            actual_config = kafka_connect_config
        else:
            continue
        
        if actual_config.get('enabled', True):
            try:
                kafka_connect_toolset = InfraInsightsKafkaConnectToolset()
                kafka_connect_toolset.configure(actual_config)
                toolsets.append(kafka_connect_toolset)
                logger.info("✅ Comprehensive Kafka Connect toolset loaded")
                break  # Only load one instance of Kafka Connect toolset
            except Exception as e:
                logger.error(f"❌ Failed to load Comprehensive Kafka Connect toolset: {e}")
    
    # Kfuse Tempo toolset - support multiple config key variations
    tempo_configs = [
        config.get('kfuse_tempo', {}),
        config.get('infrainsights_kfuse_tempo', {}),
        config.get('tempo', {})
    ]
    
    for tempo_config in tempo_configs:
        # __init__.py (loader)
        if tempo_config.get('enabled', False):
            try:
                tempo_toolset = KfuseTempoToolset()
                tempo_toolset.configure(tempo_config)  # ✅ actually configure it
                toolsets.append(tempo_toolset)
                logger.info("✅ Kfuse Tempo toolset loaded")
            except Exception as e:
                logger.error(f"❌ Failed to load Kfuse Tempo toolset: {e}")
    
    # InfraInsights Kubernetes toolset - support multiple config key variations
    kubernetes_configs = [
        get_toolset_config(['kubernetes', 'infrainsights_kubernetes', 'infrainsights_kubernetes_enhanced', 'comprehensive_kubernetes', 'comprehensive_infrainsight_kubernetes_toolset']),
        config.get('kubernetes', {}),
        config.get('infrainsights_kubernetes', {}),
        config.get('comprehensive_kubernetes', {}),
        config.get('comprehensive_infrainsight_kubernetes_toolset', {})
    ]
    
    for kubernetes_config in kubernetes_configs:
        if not kubernetes_config:
            continue
        # Handle both nested config structure and flat structure
        if 'config' in kubernetes_config and isinstance(kubernetes_config['config'], dict):
            actual_config = kubernetes_config['config']
        elif 'infrainsights_url' in kubernetes_config or 'enabled' in kubernetes_config:
            actual_config = kubernetes_config
        else:
            continue
        
        if actual_config.get('enabled', True):
            try:
                kubernetes_toolset = InfraInsightsKubernetesToolset()
                kubernetes_toolset.configure(actual_config)
                toolsets.append(kubernetes_toolset)
                logger.info("✅ InfraInsights Kubernetes toolset loaded")
                break  # Only load one instance of Kubernetes toolset
            except Exception as e:
                logger.error(f"❌ Failed to load InfraInsights Kubernetes toolset: {e}")

    
    return toolsets 