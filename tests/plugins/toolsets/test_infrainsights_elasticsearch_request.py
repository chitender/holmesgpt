"""Unit tests for the generic read-only elasticsearch_request tool.

The security-critical surface is the pure validator ``_validate_read_only_es_request`` -
it must reject anything that could mutate or create server-side state. These tests do not
require a live Elasticsearch cluster.
"""

import pytest

from holmes.plugins.toolsets.infrainsights.infrainsights_client_v2 import (
    InfraInsightsClientV2,
)
from holmes.plugins.toolsets.infrainsights.enhanced_elasticsearch_toolset import (
    EnhancedElasticsearchToolset,
    _coerce_dict,
)

validate = InfraInsightsClientV2._validate_read_only_es_request
bound = InfraInsightsClientV2._bound_search_request


# --- Allowed read requests ---------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "_cluster/health",
        "_cluster/allocation/explain",
        "_cat/indices",
        "_nodes/stats",
        "my-index/_stats",
        "_recovery",
        "_segments",
    ],
)
def test_get_is_always_allowed(path):
    method, norm = validate("GET", path)
    assert method == "GET"
    assert norm == path.strip("/")


@pytest.mark.parametrize(
    "path",
    ["_search", "orders/_search", "_msearch", "_count", "_field_caps", "logs/_explain/1"],
)
def test_post_allowed_for_search_family(path):
    method, _ = validate("POST", path)
    assert method == "POST"


def test_method_defaults_to_get():
    method, _ = validate(None, "_cluster/health")
    assert method == "GET"
    method, _ = validate("", "_cluster/health")
    assert method == "GET"


def test_method_is_case_insensitive():
    assert validate("get", "_cluster/health")[0] == "GET"
    assert validate("post", "_search")[0] == "POST"


# --- Rejected mutating / unsafe requests -------------------------------------------------


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE"])
def test_non_read_verbs_rejected(method):
    with pytest.raises(ValueError, match="read-only"):
        validate(method, "_cluster/health")


@pytest.mark.parametrize(
    "path",
    [
        "my-index/_doc/1",        # index a document
        "_bulk",                  # bulk write
        "my-index/_update/1",     # update
        "my-index/_update_by_query",
        "my-index/_delete_by_query",
        "_reindex",
        "my-index/_close",
        "my-index/_forcemerge",
        "_cluster/reroute",
        "_snapshot/repo/snap/_restore",
    ],
)
def test_post_rejected_for_non_read_endpoints(path):
    with pytest.raises(ValueError, match="search/read endpoints"):
        validate("POST", path)


@pytest.mark.parametrize("path", ["_search/scroll", "my-index/_pit", "_pit"])
def test_scroll_and_pit_rejected_even_on_get(path):
    with pytest.raises(ValueError, match="server-side state"):
        validate("GET", path)


def test_full_url_rejected():
    with pytest.raises(ValueError, match="not a full URL"):
        validate("GET", "http://es.internal:9200/_cluster/health")


def test_path_traversal_rejected():
    with pytest.raises(ValueError, match=r"\.\."):
        validate("GET", "_cat/../_bulk")


@pytest.mark.parametrize("path", ["", "   ", "/", None])
def test_empty_path_rejected(path):
    with pytest.raises(ValueError, match="path is required"):
        validate("GET", path)


def test_path_normalized_strips_slashes_and_query_string():
    _, norm = validate("GET", "/_cat/indices?v=true&format=json/")
    assert norm == "_cat/indices"


# --- Search hit bounding -----------------------------------------------------------------


def test_search_body_size_injected_when_absent():
    qp, body = bound("orders/_search", None, {"query": {"match_all": {}}}, max_hits=100)
    assert body["size"] == 100


def test_search_body_size_capped_when_too_large():
    qp, body = bound("orders/_search", None, {"size": 10000}, max_hits=100)
    assert body["size"] == 100


def test_search_body_size_preserved_when_within_cap():
    qp, body = bound("orders/_search", None, {"size": 5}, max_hits=100)
    assert body["size"] == 5


def test_search_size_capped_via_query_param_when_no_body():
    qp, body = bound("orders/_search", {"size": "9999"}, None, max_hits=100)
    assert qp["size"] == 100


def test_non_search_paths_are_not_bounded():
    qp, body = bound("_cluster/health", {"a": "b"}, None, max_hits=100)
    assert qp == {"a": "b"}
    assert body is None


# --- Param coercion ----------------------------------------------------------------------


def test_coerce_dict_accepts_dict_and_json_string_and_empty():
    assert _coerce_dict({"a": 1}) == {"a": 1}
    assert _coerce_dict('{"a": 1}') == {"a": 1}
    assert _coerce_dict(None) is None
    assert _coerce_dict("") is None


@pytest.mark.parametrize("bad", ["[1,2,3]", "not json", "42"])
def test_coerce_dict_rejects_non_objects(bad):
    with pytest.raises(ValueError, match="JSON object"):
        _coerce_dict(bad)


# --- Toolset wiring ----------------------------------------------------------------------


def test_request_tool_registered():
    toolset = EnhancedElasticsearchToolset()
    assert "elasticsearch_request" in {t.name for t in toolset.tools}
