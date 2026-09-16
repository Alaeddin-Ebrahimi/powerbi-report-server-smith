"""
Direct model-editing tools: create relationships, revise many-to-many,
and set descriptions. Thin wrappers around tmdl.writer with the file I/O
and re-validation glued on.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from .tmdl.loader import load_semantic_model
from .tmdl.writer import append_relationship_block, set_description, set_property


def create_relationship(
    definition_dir: str,
    from_table: str,
    from_column: str,
    to_table: str,
    to_column: str,
    cross_filtering_behavior: str = "automatic",
) -> dict:
    model = load_semantic_model(definition_dir)
    if from_table not in model.tables or to_table not in model.tables:
        return {"created": False, "reason": "one or both tables not found in model"}
    if from_column not in model.tables[from_table].columns:
        return {"created": False, "reason": f"{from_table}.{from_column} not found"}
    if to_column not in model.tables[to_table].columns:
        return {"created": False, "reason": f"{to_table}.{to_column} not found"}

    rel_file = Path(model.project_path) / "relationships.tmdl"
    text = rel_file.read_text(encoding="utf-8") if rel_file.exists() else ""
    new_id = str(uuid.uuid4())
    text = append_relationship_block(
        text, new_id, from_table, from_column, to_table, to_column,
        cross_filtering_behavior=cross_filtering_behavior,
    )
    rel_file.write_text(text, encoding="utf-8")
    return {"created": True, "relationship_id": new_id}


def revise_many_to_many(definition_dir: str, from_table: str, to_table: str) -> dict:
    """
    Doesn't silently rewrite the relationship — flags it and returns a
    recommendation, since resolving M:M properly means adding a bridge
    table, which is a modeling decision, not something to automate blind.
    """
    model = load_semantic_model(definition_dir)
    matches = [
        r for r in model.relationships
        if {r.from_table, r.to_table} == {from_table, to_table}
    ]
    if not matches:
        return {"found": False}

    return {
        "found": True,
        "relationship_ids": [r.id for r in matches],
        "recommendation": (
            f"Create a bridge table between {from_table} and {to_table} with a "
            "surrogate key referenced by both (many-to-one from each side), then "
            "mark the direct relationship inactive rather than leaving a raw M:M."
        ),
    }


def set_table_description(definition_dir: str, table_name: str, description: str) -> dict:
    model = load_semantic_model(definition_dir)
    if table_name not in model.tables:
        return {"updated": False, "reason": f"table '{table_name}' not found"}
    table_file = model.tables[table_name].source_file
    text = Path(table_file).read_text(encoding="utf-8")
    text = set_description(text, "table ", table_name, description)
    Path(table_file).write_text(text, encoding="utf-8")
    return {"updated": True}


def set_column_description(definition_dir: str, table_name: str, column_name: str, description: str) -> dict:
    model = load_semantic_model(definition_dir)
    if table_name not in model.tables or column_name not in model.tables[table_name].columns:
        return {"updated": False, "reason": f"{table_name}.{column_name} not found"}
    table_file = model.tables[table_name].source_file
    text = Path(table_file).read_text(encoding="utf-8")
    text = set_description(text, "column ", column_name, description)
    Path(table_file).write_text(text, encoding="utf-8")
    return {"updated": True}


def bulk_apply_descriptions(definition_dir: str, descriptions: dict[str, dict[str, str]]) -> dict:
    """
    descriptions shape: {"TableName": {"__table__": "...", "ColumnA": "...", "ColumnB": "..."}}
    "__table__" sets the table description itself; any other key is a column name.
    """
    results = {}
    for table_name, entries in descriptions.items():
        for key, desc in entries.items():
            if key == "__table__":
                results[f"{table_name}.__table__"] = set_table_description(definition_dir, table_name, desc)
            else:
                results[f"{table_name}.{key}"] = set_column_description(definition_dir, table_name, key, desc)
    return results
