"""Unit tests for the InfraInsights Elasticsearch slow-query tool.

These cover the pure parsing/bounding logic (``_summarize_search_tasks``) and the
toolset wiring (tool registration + latency-investigation LLM instructions). They do
not require a live Elasticsearch cluster or InfraInsights backend.
"""

from holmes.plugins.toolsets.infrainsights.infrainsights_client_v2 import (
    InfraInsightsClientV2,
)
from holmes.plugins.toolsets.infrainsights.enhanced_elasticsearch_toolset import (
    EnhancedElasticsearchToolset,
    ELASTICSEARCH_LLM_INSTRUCTIONS,
)


def _tasks_response():
    """A representative _tasks?actions=*search*&detailed response."""
    return {
        "nodes": {
            "node-a": {
                "name": "data-0",
                "tasks": {
                    "t1": {
                        "action": "indices:data/read/search",
                        "running_time_in_nanos": 5_000_000_000,  # 5000 ms
                        "description": 'indices[orders], search_type[QUERY_THEN_FETCH], source[{"query":{"match_all":{}}}]',
                        "cancellable": True,
                    },
                    "t2": {
                        "action": "indices:data/read/search[phase/query]",
                        "running_time_in_nanos": 250_000_000,  # 250 ms
                        "description": "indices[products]",
                        "cancellable": True,
                    },
                    # Non-search task must be excluded even if the server returned it.
                    "t3": {
                        "action": "indices:data/write/bulk",
                        "running_time_in_nanos": 9_000_000_000,
                        "description": "requests[100]",
                        "cancellable": False,
                    },
                },
            },
            "node-b": {
                "name": "data-1",
                "tasks": {
                    "t4": {
                        "action": "indices:data/read/search",
                        "running_time_in_nanos": 1_000_000_000,  # 1000 ms
                        "description": "indices[logs-2026]",
                        "cancellable": True,
                    }
                },
            },
        }
    }


def test_summarize_sorts_by_duration_and_excludes_non_search():
    result = InfraInsightsClientV2._summarize_search_tasks(
        _tasks_response(), min_running_time_ms=0, top_n=20
    )

    tasks = result["slow_search_tasks"]
    # The bulk (write) task is excluded; only the 3 search tasks remain.
    assert result["total_running_search_tasks"] == 3
    assert [t["running_time_ms"] for t in tasks] == [5000.0, 1000.0, 250.0]
    # Slowest task carries the query body and target index for root-causing.
    assert tasks[0]["node"] == "data-0"
    assert "orders" in tasks[0]["description"]
    assert result["truncated"] is False


def test_summarize_min_running_time_filter():
    result = InfraInsightsClientV2._summarize_search_tasks(
        _tasks_response(), min_running_time_ms=900, top_n=20
    )
    # Only the 5000ms and 1000ms searches clear the 900ms floor.
    assert result["total_running_search_tasks"] == 2
    assert all(t["running_time_ms"] >= 900 for t in result["slow_search_tasks"])


def test_summarize_top_n_bounds_output():
    result = InfraInsightsClientV2._summarize_search_tasks(
        _tasks_response(), min_running_time_ms=0, top_n=1
    )
    assert len(result["slow_search_tasks"]) == 1
    assert result["returned"] == 1
    assert result["truncated"] is True
    # The single returned task is the slowest one.
    assert result["slow_search_tasks"][0]["running_time_ms"] == 5000.0


def test_summarize_handles_empty_response():
    assert InfraInsightsClientV2._summarize_search_tasks({}, 0, 20) == {
        "total_running_search_tasks": 0,
        "returned": 0,
        "truncated": False,
        "slow_search_tasks": [],
    }


def test_slow_queries_tool_registered():
    toolset = EnhancedElasticsearchToolset()
    tool_names = {t.name for t in toolset.tools}
    assert "elasticsearch_slow_queries" in tool_names


def test_latency_instructions_present_on_toolset():
    toolset = EnhancedElasticsearchToolset()
    # Instructions must be attached so they are injected into the system prompt.
    assert toolset.llm_instructions == ELASTICSEARCH_LLM_INSTRUCTIONS
    # Guards the two corrections that motivated this change.
    assert "thread_pool_stats" in toolset.llm_instructions
    assert "page cache" in toolset.llm_instructions
