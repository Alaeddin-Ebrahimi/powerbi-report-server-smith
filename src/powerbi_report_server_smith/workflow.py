"""
Staging -> Dim/Fact workflow.

KNOWN v1 LIMITATION (documented up front, not hidden): Power BI's own
"query group" folders (the ones you see in the Power Query Editor's Queries
pane) are serialized in a part of the PBIP format this project doesn't have
verified, tested access to without a live Desktop round-trip. Rather than
guess at that syntax and risk writing something Desktop can't open, this
workflow tracks Staging / Dim / Fact membership in its own sidecar JSON file
(`.pbirs_smith/state.json`, next to the definition/ folder) AND, once a
table is promoted, sets the standard TOM `displayFolder` property on its
columns/measures — which IS a stable, well-documented property — so the
grouping is still visible to anyone browsing the model in Desktop or Tabular
Editor, even though it isn't literally the Power Query Editor folder.

If exact Power Query Editor query-group placement matters to you, treat the
sidecar state as the source of truth and set the matching Editor folder by
hand for now — see README.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .audit.naming import audit_naming
from .audit.star_schema import audit_star_schema
from .tmdl.loader import load_semantic_model
from .tmdl.writer import set_property

STATE_DIR_NAME = ".pbirs_smith"
STATE_FILE_NAME = "state.json"


@dataclass
class WorkflowState:
    staging: list[str] = field(default_factory=list)
    groups: dict[str, list[str]] = field(default_factory=dict)  # group name -> table names
    promotions: list[dict] = field(default_factory=list)


def _state_path(semantic_model_root: str) -> Path:
    return Path(semantic_model_root) / STATE_DIR_NAME / STATE_FILE_NAME


def load_state(semantic_model_root: str) -> WorkflowState:
    path = _state_path(semantic_model_root)
    if not path.exists():
        return WorkflowState()
    data = json.loads(path.read_text(encoding="utf-8"))
    return WorkflowState(**data)


def save_state(semantic_model_root: str, state: WorkflowState) -> None:
    path = _state_path(semantic_model_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")


def label_new_query_stage(semantic_model_root: str, table_name: str) -> WorkflowState:
    state = load_state(semantic_model_root)
    if table_name not in state.staging and not any(table_name in v for v in state.groups.values()):
        state.staging.append(table_name)
    save_state(semantic_model_root, state)
    return state


def list_staging_queries(semantic_model_root: str) -> list[str]:
    return load_state(semantic_model_root).staging


def create_query_group(semantic_model_root: str, group_name: str) -> WorkflowState:
    state = load_state(semantic_model_root)
    state.groups.setdefault(group_name, [])
    save_state(semantic_model_root, state)
    return state


def list_query_groups(semantic_model_root: str) -> dict[str, list[str]]:
    return load_state(semantic_model_root).groups


def promote_staging_to_group(
    semantic_model_root: str,
    definition_dir: str,
    table_name: str,
    group_name: str,
    force: bool = False,
) -> dict:
    """
    Gate: refuses to promote unless the star-schema audit classifies the
    table cleanly (not 'unclear'/'disconnected') and the naming audit has no
    open issues for it — unless force=True. Returns a dict with either
    {"promoted": True, ...} or {"promoted": False, "blocked_by": [...]}.
    """
    model = load_semantic_model(definition_dir)
    if table_name not in model.tables:
        return {"promoted": False, "blocked_by": [f"Table '{table_name}' not found in model"]}

    blockers: list[str] = []
    if not force:
        ss_report = audit_star_schema(model)
        classification = ss_report.classifications.get(table_name)
        if classification in ("unclear", "disconnected", None):
            blockers.append(
                f"Star-schema audit classifies '{table_name}' as "
                f"'{classification}' — resolve before promoting, or pass force=True."
            )

        naming_report = audit_naming(model)
        table_naming_issues = [i for i in naming_report.issues if i.table == table_name]
        if table_naming_issues:
            blockers.append(
                f"{len(table_naming_issues)} naming issue(s) still open for '{table_name}' — "
                "resolve before promoting, or pass force=True."
            )

    if blockers:
        return {"promoted": False, "blocked_by": blockers}

    # Apply: sidecar state + displayFolder on the table's fields.
    state = load_state(semantic_model_root)
    if table_name in state.staging:
        state.staging.remove(table_name)
    state.groups.setdefault(group_name, [])
    if table_name not in state.groups[group_name]:
        state.groups[group_name].append(table_name)
    state.promotions.append({"table": table_name, "group": group_name})
    save_state(semantic_model_root, state)

    table = model.tables[table_name]
    table_file = table.source_file
    if table_file:
        text = Path(table_file).read_text(encoding="utf-8")
        for col_name in table.columns:
            text = set_property(text, "column ", col_name, "displayFolder", group_name)
        for meas_name in table.measures:
            text = set_property(text, "measure ", meas_name, "displayFolder", group_name)
        Path(table_file).write_text(text, encoding="utf-8")

    return {"promoted": True, "table": table_name, "group": group_name}
