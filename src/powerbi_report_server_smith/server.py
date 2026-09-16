"""
powerbi-report-server-smith — MCP server entrypoint.

Author: Ala (YouTube: Data With Ala)
Contact: ebrahimy.alaeddin@ebrahimy
License: MIT

Covers, end to end: model quality/naming audit -> staging/Dim/Fact workflow
-> relationships & gap analysis -> descriptions & AI-readiness -> deployment
to an on-premises Power BI Report Server.

Run directly for local (stdio) MCP use:
    python -m powerbi_report_server_smith.server
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from . import modeling, pbirs, workflow
from .audit.ai_readiness import score_ai_readiness
from .audit.naming import audit_naming
from .audit.relationships import relationship_gap_report
from .audit.star_schema import audit_star_schema
from .config import load_policies
from .tmdl.loader import load_semantic_model, resolve_project_paths

mcp = FastMCP("powerbi-report-server-smith")

_policies = load_policies()


def _read_only() -> bool:
    env_override = os.environ.get("PBIRS_SMITH_READONLY")
    if env_override is not None:
        return env_override.lower() == "true"
    return bool(_policies.get("safety", {}).get("read_only", False))


def _refuse_if_read_only() -> dict | None:
    if _read_only():
        return {"blocked": True, "reason": "Server is running in read-only mode (PBIRS_SMITH_READONLY=true)."}
    return None


# ---------------------------------------------------------------------------
# Audit tools (read-only, safe to run anytime)
# ---------------------------------------------------------------------------

@mcp.tool()
def star_schema_audit(project_path: str) -> dict:
    """
    Classify every table in the model as fact / dimension / bridge / date /
    disconnected, with a scored findings report (missing date table,
    fact-to-fact links, snowflaking, unclear tables). Accepts a .pbip root,
    a *.SemanticModel folder, or a definition/ folder directly.
    """
    model = load_semantic_model(project_path)
    return audit_star_schema(model).as_dict()


@mcp.tool()
def naming_audit(project_path: str) -> dict:
    """
    Report naming-convention violations (underscores, casing, raw
    abbreviations) and cross-table spelling inconsistencies for the same
    concept, plus a suggested rename plan.
    """
    model = load_semantic_model(project_path)
    rules = _policies.get("naming_rules")
    return audit_naming(model, rules=rules).as_dict()


@mcp.tool()
def relationship_gap_report_tool(project_path: str) -> dict:
    """
    Report disconnected tables, inactive relationships, many-to-many pairs
    needing a bridge table, whether a date table is missing, and candidate
    relationships suggested from matching column name/type across
    currently-unconnected tables.
    """
    model = load_semantic_model(project_path)
    classifications = audit_star_schema(model).classifications
    return relationship_gap_report(model, classifications).as_dict()


@mcp.tool()
def ai_readiness_score(project_path: str) -> dict:
    """
    Score how ready this model is for Fabric Copilot / Power BI Data Agents:
    description coverage on tables/columns/measures, presence of a marked
    date table, and whether a PBIP Copilot/ config folder exists (AI
    instructions / AI data schema / Verified Answers — those are PBIP-only
    and not editable by this server; author them directly in Desktop).
    """
    model = load_semantic_model(project_path)
    classifications = audit_star_schema(model).classifications
    _, semantic_model_root = resolve_project_paths(project_path)
    return score_ai_readiness(model, classifications, semantic_model_root).as_dict()


# ---------------------------------------------------------------------------
# Staging / Dim / Fact workflow
#
# KNOWN LIMITATION: group membership here is tracked in a sidecar state file
# plus the TOM displayFolder property — not Power Query Editor's own query
# group folders, which this server doesn't have verified write access to.
# See workflow.py docstring for the full explanation.
# ---------------------------------------------------------------------------

@mcp.tool()
def label_new_query_stage(project_path: str, table_name: str) -> dict:
    """Tag a table/query as belonging to the Staging group, pending cleanup."""
    _, root = resolve_project_paths(project_path)
    state = workflow.label_new_query_stage(root, table_name)
    return {"staging": state.staging}


@mcp.tool()
def list_staging_queries(project_path: str) -> dict:
    """List tables/queries currently sitting in the Staging group."""
    _, root = resolve_project_paths(project_path)
    return {"staging": workflow.list_staging_queries(root)}


@mcp.tool()
def create_query_group(project_path: str, group_name: str) -> dict:
    """Create a named group (e.g. 'Dim', 'Fact') to promote staged tables into."""
    if (blocked := _refuse_if_read_only()):
        return blocked
    _, root = resolve_project_paths(project_path)
    state = workflow.create_query_group(root, group_name)
    return {"groups": state.groups}


@mcp.tool()
def list_query_groups(project_path: str) -> dict:
    """List all groups and their current table membership."""
    _, root = resolve_project_paths(project_path)
    return {"groups": workflow.list_query_groups(root)}


@mcp.tool()
def promote_staging_to_group(project_path: str, table_name: str, group_name: str, force: bool = False) -> dict:
    """
    Promote a staged table into a Dim/Fact group. Refuses by default unless
    the star-schema audit classifies the table cleanly and no naming issues
    remain open for it — pass force=True to override the gate.
    """
    if (blocked := _refuse_if_read_only()):
        return blocked
    definition_dir, root = resolve_project_paths(project_path)
    return workflow.promote_staging_to_group(root, definition_dir, table_name, group_name, force=force)


# ---------------------------------------------------------------------------
# Relationships & metadata (write tools)
# ---------------------------------------------------------------------------

@mcp.tool()
def create_relationship(project_path: str, from_table: str, from_column: str,
                         to_table: str, to_column: str,
                         cross_filtering_behavior: str = "automatic") -> dict:
    """Create a new many-to-one relationship between two tables."""
    if (blocked := _refuse_if_read_only()):
        return blocked
    definition_dir, _ = resolve_project_paths(project_path)
    return modeling.create_relationship(definition_dir, from_table, from_column, to_table, to_column, cross_filtering_behavior)


@mcp.tool()
def revise_many_to_many(project_path: str, from_table: str, to_table: str) -> dict:
    """
    Look up an existing many-to-many relationship between two tables and
    return a bridge-table recommendation — does not silently rewrite it,
    since resolving M:M is a modeling decision.
    """
    definition_dir, _ = resolve_project_paths(project_path)
    return modeling.revise_many_to_many(definition_dir, from_table, to_table)


@mcp.tool()
def set_table_description(project_path: str, table_name: str, description: str) -> dict:
    """Set (or replace) a table's description."""
    if (blocked := _refuse_if_read_only()):
        return blocked
    definition_dir, _ = resolve_project_paths(project_path)
    return modeling.set_table_description(definition_dir, table_name, description)


@mcp.tool()
def set_column_description(project_path: str, table_name: str, column_name: str, description: str) -> dict:
    """Set (or replace) a column's description."""
    if (blocked := _refuse_if_read_only()):
        return blocked
    definition_dir, _ = resolve_project_paths(project_path)
    return modeling.set_column_description(definition_dir, table_name, column_name, description)


@mcp.tool()
def bulk_apply_descriptions(project_path: str, descriptions: dict) -> dict:
    """
    Apply many descriptions at once. Shape:
    {"TableName": {"__table__": "table desc", "ColumnA": "col desc"}}
    """
    if (blocked := _refuse_if_read_only()):
        return blocked
    definition_dir, _ = resolve_project_paths(project_path)
    return modeling.bulk_apply_descriptions(definition_dir, descriptions)


# ---------------------------------------------------------------------------
# Power BI Report Server deployment (on-prem, NTLM — see pbirs.py docstring:
# built to spec, not live-tested against a real PBIRS instance)
# ---------------------------------------------------------------------------

@mcp.tool()
def pbirs_list_folders(parent_path: str = "/") -> dict:
    """List folders in the Power BI Report Server catalog under parent_path."""
    return pbirs.pbirs_list_folders(parent_path)


@mcp.tool()
def pbirs_create_folder(parent_path: str, name: str) -> dict:
    """Create a folder in the Power BI Report Server catalog."""
    if (blocked := _refuse_if_read_only()):
        return blocked
    return pbirs.pbirs_create_folder(parent_path, name)


@mcp.tool()
def pbirs_list_catalog_items(folder_path: str) -> dict:
    """List reports/datasets/KPIs etc. inside a Report Server folder."""
    return pbirs.pbirs_list_catalog_items(folder_path)


@mcp.tool()
def pbirs_upload_report(folder_path: str, name: str, pbix_file_path: str) -> dict:
    """Upload a local .pbix file to a folder on the Report Server."""
    if (blocked := _refuse_if_read_only()):
        return blocked
    return pbirs.pbirs_upload_report(folder_path, name, pbix_file_path)


@mcp.tool()
def pbirs_list_subscriptions(item_id: str) -> dict:
    """List subscriptions configured for a Report Server catalog item."""
    return pbirs.pbirs_list_subscriptions(item_id)


@mcp.tool()
def pbirs_trigger_refresh_plan(refresh_plan_id: str) -> dict:
    """Trigger an existing refresh plan on the Report Server."""
    if (blocked := _refuse_if_read_only()):
        return blocked
    return pbirs.pbirs_trigger_refresh_plan(refresh_plan_id)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
