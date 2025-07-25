import logging
import os
import os.path
from typing import Any, List, Optional, Union

from holmes.common.env_vars import USE_LEGACY_KUBERNETES_LOGS
import yaml  # type: ignore
from pydantic import ValidationError

from holmes.plugins.toolsets.azure_sql.azure_sql_toolset import AzureSQLToolset
import holmes.utils.env as env_utils
from holmes.core.supabase_dal import SupabaseDal
from holmes.core.tools import Toolset, ToolsetType, ToolsetYamlFromConfig, YAMLToolset
from holmes.plugins.toolsets.coralogix.toolset_coralogix_logs import (
    CoralogixLogsToolset,
)
from holmes.plugins.toolsets.datadog.toolset_datadog_logs import DatadogLogsToolset
from holmes.plugins.toolsets.datadog.toolset_datadog_metrics import (
    DatadogMetricsToolset,
)
from holmes.plugins.toolsets.datadog.toolset_datadog_traces import (
    DatadogTracesToolset,
)
from holmes.plugins.toolsets.kubernetes_logs import KubernetesLogsToolset
from holmes.plugins.toolsets.git import GitToolset
from holmes.plugins.toolsets.grafana.toolset_grafana import GrafanaToolset
from holmes.plugins.toolsets.bash.bash_toolset import BashExecutorToolset
from holmes.plugins.toolsets.grafana.toolset_grafana_loki import GrafanaLokiToolset
from holmes.plugins.toolsets.grafana.toolset_grafana_tempo import GrafanaTempoToolset
from holmes.plugins.toolsets.internet.internet import InternetToolset
from holmes.plugins.toolsets.internet.notion import NotionToolset
from holmes.plugins.toolsets.kafka import KafkaToolset
from holmes.plugins.toolsets.mcp.toolset_mcp import RemoteMCPToolset
from holmes.plugins.toolsets.newrelic import NewRelicToolset
from holmes.plugins.toolsets.opensearch.opensearch import OpenSearchToolset
from holmes.plugins.toolsets.opensearch.opensearch_logs import OpenSearchLogsToolset
from holmes.plugins.toolsets.opensearch.opensearch_traces import OpenSearchTracesToolset
from holmes.plugins.toolsets.prometheus.prometheus import PrometheusToolset
from holmes.plugins.toolsets.rabbitmq.toolset_rabbitmq import RabbitMQToolset
from holmes.plugins.toolsets.robusta.robusta import RobustaToolset
from holmes.plugins.toolsets.atlas_mongodb.mongodb_atlas import MongoDBAtlasToolset
from holmes.plugins.toolsets.runbook.runbook_fetcher import RunbookToolset
from holmes.plugins.toolsets.servicenow.servicenow import ServiceNowToolset

# Enhanced InfraInsights toolsets
from holmes.plugins.toolsets.infrainsights.enhanced_elasticsearch_toolset import EnhancedElasticsearchToolset
from holmes.plugins.toolsets.infrainsights.comprehensive_kafka_toolset import ComprehensiveKafkaToolset
from holmes.plugins.toolsets.infrainsights.enhanced_mongodb_toolset import EnhancedMongoDBToolset
from holmes.plugins.toolsets.infrainsights.enhanced_redis_toolset import EnhancedRedisToolset
from holmes.plugins.toolsets.infrainsights.comprehensive_kubernetes_toolset import InfraInsightsKubernetesToolset

THIS_DIR = os.path.abspath(os.path.dirname(__file__))


def load_toolsets_from_file(
    toolsets_path: str, strict_check: bool = True
) -> List[Toolset]:
    toolsets = []
    with open(toolsets_path) as file:
        parsed_yaml = yaml.safe_load(file)
        if parsed_yaml is None:
            raise ValueError(
                f"Failed to load toolsets from {toolsets_path}: file is empty or invalid YAML."
            )
        toolsets_dict = parsed_yaml.get("toolsets", {})

        toolsets.extend(load_toolsets_from_config(toolsets_dict, strict_check))

    return toolsets


def load_python_toolsets(dal: Optional[SupabaseDal]) -> List[Toolset]:
    logging.debug("loading python toolsets")
    toolsets: list[Toolset] = [
        InternetToolset(),
        RobustaToolset(dal),
        OpenSearchToolset(),
        GrafanaLokiToolset(),
        GrafanaTempoToolset(),
        NewRelicToolset(),
        GrafanaToolset(),
        NotionToolset(),
        KafkaToolset(),
        DatadogLogsToolset(),
        DatadogMetricsToolset(),
        DatadogTracesToolset(),
        PrometheusToolset(),
        OpenSearchLogsToolset(),
        OpenSearchTracesToolset(),
        CoralogixLogsToolset(),
        RabbitMQToolset(),
        GitToolset(),
        BashExecutorToolset(),
        MongoDBAtlasToolset(),
        RunbookToolset(),
        AzureSQLToolset(),
        ServiceNowToolset(),
    ]
    if not USE_LEGACY_KUBERNETES_LOGS:
        toolsets.append(KubernetesLogsToolset())

    return toolsets


def load_builtin_toolsets(dal: Optional[SupabaseDal] = None) -> List[Toolset]:
    all_toolsets: List[Toolset] = []
    logging.debug(f"loading toolsets from {THIS_DIR}")

    # Handle YAML toolsets
    for filename in os.listdir(THIS_DIR):
        if not filename.endswith(".yaml"):
            continue

        if filename == "kubernetes_logs.yaml" and not USE_LEGACY_KUBERNETES_LOGS:
            continue

        path = os.path.join(THIS_DIR, filename)
        toolsets_from_file = load_toolsets_from_file(path, strict_check=True)
        all_toolsets.extend(toolsets_from_file)

    all_toolsets.extend(load_python_toolsets(dal=dal))  # type: ignore

    # disable built-in toolsets by default, and the user can enable them explicitly in config.
    for toolset in all_toolsets:
        toolset.type = ToolsetType.BUILTIN
        # dont' expose build-in toolsets path
        toolset.path = None

    return all_toolsets  # type: ignore


def is_old_toolset_config(
    toolsets: Union[dict[str, dict[str, Any]], List[dict[str, Any]]],
) -> bool:
    # old config is a list of toolsets
    if isinstance(toolsets, list):
        return True
    return False


def load_toolsets_from_config(
    toolsets: dict[str, dict[str, Any]],
    strict_check: bool = True,
) -> List[Toolset]:
    """
    Load toolsets from a dictionary or list of dictionaries.
    :param toolsets: Dictionary of toolsets or list of toolset configurations.
    :param strict_check: If True, all required fields for a toolset must be present.
    :return: List of validated Toolset objects.
    """
    
    logging.info("🚀🚀🚀 LOADING TOOLSETS FROM CONFIG - ENHANCED VERSION 🚀🚀🚀")
    logging.info(f"📝 Received toolsets config: {list(toolsets.keys()) if toolsets else 'None'}")

    if not toolsets:
        return []

    loaded_toolsets: list[Toolset] = []
    if is_old_toolset_config(toolsets):
        message = "Old toolset config format detected, please update to the new format: https://docs.robusta.dev/master/configuration/holmesgpt/custom_toolsets.html"
        logging.warning(message)
        raise ValueError(message)

    for name, config in toolsets.items():
        logging.info(f"🔧🔧🔧 PROCESSING TOOLSET: {name} 🔧🔧🔧")
        try:
            toolset_type = config.get("type", ToolsetType.BUILTIN.value)
            # MCP server is not a built-in toolset, so we need to set the type explicitly
            validated_toolset: Optional[Toolset] = None
            
            # Enhanced InfraInsights toolsets (support both naming conventions)
            if name == "infrainsights_elasticsearch_enhanced" or name == "infrainsights_elasticsearch_v2":
                logging.info(f"🔧 Loading enhanced Elasticsearch toolset: {name}")
                logging.info(f"🔧 Config received: {config}")
                validated_toolset = EnhancedElasticsearchToolset()
                validated_toolset.config = config.get("config")
                logging.info(f"🔧 Extracted config: {validated_toolset.config}")
                # Call configure method to initialize InfraInsights client with config
                if validated_toolset.config:
                    logging.info(f"🔧 Calling configure method with config: {validated_toolset.config}")
                    validated_toolset.configure(validated_toolset.config)
                else:
                    logging.warning(f"🔧 No config found for {name}, using defaults")
            elif name == "infrainsights_kafka_enhanced" or name == "infrainsights_kafka_v2" or name == "infrainsights_kafka_comprehensive":
                logging.info(f"🔧 Loading comprehensive Kafka toolset: {name}")
                validated_toolset = ComprehensiveKafkaToolset()
                validated_toolset.config = config.get("config")
                # Call configure method to initialize InfraInsights client with config
                if validated_toolset.config:
                    validated_toolset.configure(validated_toolset.config)
            elif name == "infrainsights_mongodb_enhanced" or name == "infrainsights_mongodb_v2":
                logging.info(f"🔧 Loading enhanced MongoDB toolset: {name}")
                logging.info(f"🔧 Config received: {config}")
                validated_toolset = EnhancedMongoDBToolset()
                validated_toolset.config = config.get("config")
                logging.info(f"🔧 Extracted config: {validated_toolset.config}")
                # Call configure method to initialize InfraInsights client with config
                if validated_toolset.config:
                    logging.info(f"🔧 Calling configure method with config: {validated_toolset.config}")
                    validated_toolset.configure(validated_toolset.config)
                else:
                    logging.warning(f"🔧 No config found for {name}, using defaults")
            elif name == "infrainsights_redis_enhanced" or name == "infrainsights_redis":
                logging.info(f"🔧 Loading enhanced Redis toolset: {name}")
                logging.info(f"🔧 Config received: {config}")
                validated_toolset = EnhancedRedisToolset()
                validated_toolset.config = config.get("config")
                logging.info(f"🔧 Extracted config: {validated_toolset.config}")
                
                # Safety check: Verify all tools are proper Tool objects
                logging.info(f"🔧 SAFETY CHECK: Verifying {len(validated_toolset.tools)} Redis tools")
                for i, tool in enumerate(validated_toolset.tools):
                    if not hasattr(tool, 'name'):
                        logging.error(f"🔧 SAFETY CHECK FAILED: Tool {i} is not a proper Tool object: {type(tool)}")
                        raise ValueError(f"Redis toolset tool {i} is not a proper Tool object: {type(tool)}")
                    logging.info(f"🔧 SAFETY CHECK: Tool {i} OK: {tool.name} ({type(tool).__name__})")
                
                # Call configure method to initialize InfraInsights client with config
                if validated_toolset.config:
                    logging.info(f"🔧 Calling configure method with config: {validated_toolset.config}")
                    validated_toolset.configure(validated_toolset.config)
                else:
                    logging.warning(f"🔧 No config found for {name}, using defaults")
            elif name == "infrainsights_kubernetes_enhanced" or name == "infrainsights_kubernetes_v2" or name == "infrainsights_kubernetes":
                logging.info(f"🔧 Loading enhanced Kubernetes toolset: {name}")
                logging.info(f"🔧 Config received: {config}")
                validated_toolset = InfraInsightsKubernetesToolset()
                validated_toolset.config = config.get("config")
                logging.info(f"🔧 Extracted config: {validated_toolset.config}")
                
                # Safety check: Verify all tools are proper Tool objects
                logging.info(f"🔧 SAFETY CHECK: Verifying {len(validated_toolset.tools)} Kubernetes tools")
                for i, tool in enumerate(validated_toolset.tools):
                    if not hasattr(tool, 'name'):
                        logging.error(f"🔧 SAFETY CHECK FAILED: Tool {i} is not a proper Tool object: {type(tool)}")
                        raise ValueError(f"Kubernetes toolset tool {i} is not a proper Tool object: {type(tool)}")
                    logging.info(f"🔧 SAFETY CHECK: Tool {i} OK: {tool.name} ({type(tool).__name__})")
                
                # Call configure method to initialize InfraInsights client with config
                if validated_toolset.config:
                    logging.info(f"🔧 Calling configure method with config: {validated_toolset.config}")
                    validated_toolset.configure(validated_toolset.config)
                else:
                    logging.warning(f"🔧 No config found for {name}, using defaults")
            elif toolset_type is ToolsetType.MCP:
                validated_toolset = RemoteMCPToolset(**config, name=name)
            elif strict_check:
                validated_toolset = YAMLToolset(**config, name=name)  # type: ignore
            else:
                validated_toolset = ToolsetYamlFromConfig(  # type: ignore
                    **config, name=name
                )

            if validated_toolset.config:
                validated_toolset.config = env_utils.replace_env_vars_values(
                    validated_toolset.config
                )
            loaded_toolsets.append(validated_toolset)
        except ValidationError as e:
            logging.warning(f"Toolset '{name}' is invalid: {e}")

        except Exception:
            logging.warning("Failed to load toolset: %s", name, exc_info=True)

    return loaded_toolsets
