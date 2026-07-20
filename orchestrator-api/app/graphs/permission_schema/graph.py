from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.graphs.permission_schema.nodes.build_allowed_resource_map import build_allowed_resource_map
from app.graphs.permission_schema.nodes.build_user_permission_schema import build_user_permission_schema
from app.graphs.permission_schema.nodes.cache_permission_schema import cache_permission_schema
from app.graphs.permission_schema.nodes.cache_validation import cache_validation
from app.graphs.permission_schema.nodes.emit_permission_schema import emit_permission_schema
from app.graphs.permission_schema.nodes.permission_cache_lookup import permission_cache_lookup
from app.graphs.permission_schema.nodes.request_intake import request_intake
from app.graphs.permission_schema.nodes.resolve_share_drive_permissions import resolve_share_drive_permissions
from app.graphs.permission_schema.nodes.resolve_trusted_identity import resolve_trusted_identity
from app.graphs.permission_schema.nodes.resolve_user_groups import resolve_user_groups
from app.graphs.permission_schema.nodes.validate_permission_schema import validate_permission_schema
from app.graphs.permission_schema.state import ACCESS_OK, PermissionSchemaState, STATUS_IN_PROGRESS


def _after_cache_lookup(state: PermissionSchemaState) -> Literal["cache_validation", "resolve_user_groups", "emit_permission_schema"]:
    if state.get("access_status") != STATUS_IN_PROGRESS:
        return "emit_permission_schema"
    if state.get("cached_permission_schema"):
        return "cache_validation"
    return "resolve_user_groups"


def _after_cache_validation(state: PermissionSchemaState) -> Literal["emit_permission_schema", "resolve_user_groups"]:
    if state.get("access_status") == ACCESS_OK or state.get("access_status") != STATUS_IN_PROGRESS:
        return "emit_permission_schema"
    return "resolve_user_groups"


def build_get_user_permission_schema_graph():
    graph = StateGraph(PermissionSchemaState)
    graph.add_node("request_intake", request_intake)
    graph.add_node("resolve_trusted_identity", resolve_trusted_identity)
    graph.add_node("permission_cache_lookup", permission_cache_lookup)
    graph.add_node("cache_validation", cache_validation)
    graph.add_node("resolve_user_groups", resolve_user_groups)
    graph.add_node("resolve_share_drive_permissions", resolve_share_drive_permissions)
    graph.add_node("build_allowed_resource_map", build_allowed_resource_map)
    graph.add_node("build_user_permission_schema", build_user_permission_schema)
    graph.add_node("validate_permission_schema", validate_permission_schema)
    graph.add_node("cache_permission_schema", cache_permission_schema)
    graph.add_node("emit_permission_schema", emit_permission_schema)

    graph.add_edge(START, "request_intake")
    graph.add_edge("request_intake", "resolve_trusted_identity")
    graph.add_edge("resolve_trusted_identity", "permission_cache_lookup")
    graph.add_conditional_edges("permission_cache_lookup", _after_cache_lookup)
    graph.add_conditional_edges("cache_validation", _after_cache_validation)
    graph.add_edge("resolve_user_groups", "resolve_share_drive_permissions")
    graph.add_edge("resolve_share_drive_permissions", "build_allowed_resource_map")
    graph.add_edge("build_allowed_resource_map", "build_user_permission_schema")
    graph.add_edge("build_user_permission_schema", "validate_permission_schema")
    graph.add_edge("validate_permission_schema", "cache_permission_schema")
    graph.add_edge("cache_permission_schema", "emit_permission_schema")
    graph.add_edge("emit_permission_schema", END)
    return graph.compile()


get_user_permission_schema_graph = build_get_user_permission_schema_graph()


def run_get_user_permission_schema(state: PermissionSchemaState) -> PermissionSchemaState:
    return get_user_permission_schema_graph.invoke(state)
