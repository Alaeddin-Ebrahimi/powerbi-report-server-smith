"""
Walks a `<Name>.SemanticModel/definition/` folder (PBIP project format) and
builds a SemanticModel instance out of it.
"""
from __future__ import annotations

import re
from pathlib import Path

from .model import Column, Measure, Relationship, SemanticModel, Table
from .parser import TmdlNode, block_properties, parse_tmdl_text, strip_quotes


def _find_definition_dir(project_path: str) -> Path:
    """
    Accepts either the definition/ folder directly, the .SemanticModel folder,
    or the .pbip project root — locates definition/ in any case.
    """
    p = Path(project_path)
    candidates = [
        p,
        p / "definition",
    ]
    # If given the .pbip root, look for a *.SemanticModel subfolder.
    if p.is_dir():
        for child in p.iterdir():
            if child.is_dir() and child.name.endswith(".SemanticModel"):
                candidates.append(child / "definition")

    for c in candidates:
        if c.is_dir() and (c / "model.tmdl").exists():
            return c

    raise FileNotFoundError(
        f"Could not locate a semantic model 'definition' folder under {project_path} "
        "(expected to find model.tmdl)"
    )


def _parse_table_file(text: str, source_file: str) -> Table | None:
    roots = parse_tmdl_text(text)
    table_node = next((n for n in roots if n.header.startswith("table ")), None)
    if table_node is None:
        return None

    name = strip_quotes(table_node.header[len("table "):].strip())
    table_props = block_properties(table_node)
    table = Table(
        name=name,
        description=table_node.description,
        is_hidden=table_props.get("isHidden") == "true",
        source_file=source_file,
    )

    for child in table_node.children:
        if child.header.startswith("column "):
            col_name = strip_quotes(child.header[len("column "):].strip())
            props = block_properties(child)
            table.columns[col_name] = Column(
                name=col_name,
                table=name,
                data_type=props.get("dataType"),
                source_column=props.get("sourceColumn"),
                summarize_by=props.get("summarizeBy"),
                is_hidden=props.get("isHidden") == "true",
                description=child.description,
                display_folder=props.get("displayFolder"),
                is_key=props.get("isKey") == "true",
            )
        elif child.header.startswith("measure "):
            rest = child.header[len("measure "):]
            if "=" in rest:
                raw_name, expr = rest.split("=", 1)
            else:
                raw_name, expr = rest, ""
            m_name = strip_quotes(raw_name.strip())
            props = block_properties(child)
            # Multi-line DAX continuation: any child that isn't a recognised
            # property is treated as part of the expression body.
            extra_lines = [
                c.header for c in child.children
                if not re.match(r"^[A-Za-z][A-Za-z0-9_]*\s*:", c.header)
                and c.header not in ("true",)
            ]
            full_expr = expr.strip()
            if extra_lines:
                full_expr = (full_expr + "\n" + "\n".join(extra_lines)).strip()
            table.measures[m_name] = Measure(
                name=m_name,
                table=name,
                expression=full_expr,
                description=child.description,
                display_folder=props.get("displayFolder"),
                format_string=props.get("formatString"),
            )

    return table


def _parse_relationships_file(text: str) -> list[Relationship]:
    roots = parse_tmdl_text(text)
    rels: list[Relationship] = []
    for node in roots:
        if not node.header.startswith("relationship "):
            continue
        rel_id = node.header[len("relationship "):].strip()
        props = block_properties(node)

        from_col = props.get("fromColumn", "")
        to_col = props.get("toColumn", "")
        from_table, _, from_column = from_col.partition(".")
        to_table, _, to_column = to_col.partition(".")

        rels.append(Relationship(
            id=rel_id,
            from_table=from_table,
            from_column=from_column,
            to_table=to_table,
            to_column=to_column,
            cross_filtering_behavior=props.get("crossFilteringBehavior", "singleDirection"),
            is_active=props.get("isActive", "true") != "false",
            from_cardinality=props.get("fromCardinality"),
            to_cardinality=props.get("toCardinality"),
        ))
    return rels


def resolve_project_paths(project_path: str) -> tuple[str, str]:
    """
    Given any of: a definition/ folder, a *.SemanticModel folder, or a .pbip
    project root — return (definition_dir, semantic_model_root) as strings.
    semantic_model_root is the parent of definition/ (i.e. the
    *.SemanticModel folder), used for sidecar workflow state and Copilot/
    folder detection.
    """
    definition_dir = _find_definition_dir(project_path)
    return str(definition_dir), str(definition_dir.parent)


def load_semantic_model(project_path: str) -> SemanticModel:
    definition_dir = _find_definition_dir(project_path)
    model = SemanticModel(project_path=str(definition_dir))

    tables_dir = definition_dir / "tables"
    if tables_dir.is_dir():
        for tmdl_file in sorted(tables_dir.glob("*.tmdl")):
            text = tmdl_file.read_text(encoding="utf-8")
            table = _parse_table_file(text, source_file=str(tmdl_file))
            if table is not None:
                model.add_table(table)

    rel_file = definition_dir / "relationships.tmdl"
    if rel_file.exists():
        model.relationships = _parse_relationships_file(
            rel_file.read_text(encoding="utf-8")
        )

    return model
