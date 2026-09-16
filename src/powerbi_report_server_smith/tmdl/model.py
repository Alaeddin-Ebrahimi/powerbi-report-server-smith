"""
Plain data classes representing a parsed Power BI semantic model.

These are intentionally simple containers, not a full TOM re-implementation.
They hold exactly what the audit / workflow / modeling tools need.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Column:
    name: str
    table: str
    data_type: str | None = None
    source_column: str | None = None
    summarize_by: str | None = None
    is_hidden: bool = False
    description: str | None = None
    display_folder: str | None = None
    is_key: bool = False


@dataclass
class Measure:
    name: str
    table: str
    expression: str = ""
    description: str | None = None
    display_folder: str | None = None
    format_string: str | None = None


@dataclass
class Table:
    name: str
    columns: dict[str, Column] = field(default_factory=dict)
    measures: dict[str, Measure] = field(default_factory=dict)
    description: str | None = None
    is_hidden: bool = False
    source_file: str | None = None

    # Filled in by audits — not part of raw TMDL, computed at analysis time.
    classification: str | None = None  # "fact" | "dimension" | "bridge" | "disconnected" | "date"


@dataclass
class Relationship:
    id: str
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    cross_filtering_behavior: str = "singleDirection"  # or "bothDirections", "automatic"
    is_active: bool = True
    from_cardinality: str | None = None  # "many" | "one" — not always present in source
    to_cardinality: str | None = None


@dataclass
class SemanticModel:
    tables: dict[str, Table] = field(default_factory=dict)
    relationships: list[Relationship] = field(default_factory=list)
    project_path: str = ""

    def add_table(self, table: Table) -> None:
        self.tables[table.name] = table

    def relationships_for(self, table_name: str) -> list[Relationship]:
        return [
            r for r in self.relationships
            if r.from_table == table_name or r.to_table == table_name
        ]
