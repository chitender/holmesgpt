import logging
import os
import os.path
from typing import List, Optional

from holmes.core.supabase_dal import SupabaseDal
from holmes.plugins.toolsets.coralogix.toolset_coralogix_logs import (
    CoralogixLogsToolset,
)
from holmes.plugins.toolsets.datetime import DatetimeToolset
from holmes.plugins.toolsets.opensearch.opensearch_logs import OpenSearchLogsToolset
from holmes.plugins.toolsets.opensearch.opensearch_traces import OpenSearchTracesToolset
from holmes.plugins.toolsets.robusta import RobustaToolset
from holmes.plugins.toolsets.tempo_tool import KfuseTempoToolset
from holmes.plugins.toolsets.mongo import MongoToolset
from holmes.plugins.toolsets.redis import RedisToolset
from holmes.plugins.toolsets.grafana.toolset_grafana_loki import GrafanaLokiToolset
from holmes.plugins.toolsets.grafana.toolset_grafana_tempo import GrafanaTempoToolset
from holmes.plugins.toolsets.internet.internet import InternetToolset
from holmes.plugins.toolsets.internet.notion import NotionToolset
from holmes.plugins.toolsets.prometheus import PrometheusToolset
from holmes.plugins.toolsets.opensearch import OpenSearchToolset
from holmes.plugins.toolsets.kubernetes_cpu_throttling import KubernetesCPUThrottlingToolset
from holmes.plugins.toolsets.prometheus.prometheus import PrometheusToolset
from holmes.plugins.toolsets.opensearch.opensearch import OpenSearchToolset
from holmes.plugins.toolsets.kafka import KafkaToolset
from holmes.plugins.toolsets.kafka_connect import KafkaConnectToolset


from holmes.core.tools import Toolset, YAMLToolset
import yaml


THIS_DIR = os.path.abspath(os.path.dirname(__file__))


def load_toolsets_from_file(
    path: str, silent_fail: bool = False, is_default: bool = False
) -> List[YAMLToolset]:
    file_toolsets = []
    with open(path) as file:
        parsed_yaml = yaml.safe_load(file)
        toolsets = parsed_yaml.get("toolsets", {})
        for name, config in toolsets.items():
            try:
                toolset = YAMLToolset(**config, name=name, is_default=is_default)
                toolset.set_path(path)
                file_toolsets.append(YAMLToolset(**config, name=name))
            except Exception:
                if not silent_fail:
                    logging.error(
                        f"Error happened while loading {name} toolset from {path}",
                        exc_info=True,
                    )

    return file_toolsets


def load_python_toolsets(dal: Optional[SupabaseDal]) -> List[Toolset]:
    logging.debug("loading python toolsets")
    toolsets: list[Toolset] = [
        InternetToolset(),
        RobustaToolset(dal),
        OpenSearchToolset(),
        GrafanaLokiToolset(),
        GrafanaTempoToolset(),
        NotionToolset(),
        KafkaToolset(),
        PrometheusToolset(),
        DatetimeToolset(),
<<<<<<< HEAD
        KfuseTempoToolset(),
        MongoToolset(),
        RedisToolset(),
        KubernetesCPUThrottlingToolset(),
        PrometheusToolset(),
        KafkaConnectToolset(),

=======
        OpenSearchLogsToolset(),
        OpenSearchTracesToolset(),
        CoralogixLogsToolset(),
>>>>>>> 1e9d049effcd2d4964590f830ae1d3970f080a80
    ]

    return toolsets


def load_builtin_toolsets(dal: Optional[SupabaseDal] = None) -> List[Toolset]:
    all_toolsets = []
    logging.debug(f"loading toolsets from {THIS_DIR}")
    for filename in os.listdir(THIS_DIR):
        if not filename.endswith(".yaml"):
            continue
        path = os.path.join(THIS_DIR, filename)
        toolsets_from_file = load_toolsets_from_file(path, is_default=True)
        all_toolsets.extend(toolsets_from_file)

    all_toolsets.extend(load_python_toolsets(dal=dal))
    return all_toolsets
