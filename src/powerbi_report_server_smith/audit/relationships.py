"""
Relationship-level audit: what's missing, what's inactive, what's flagged as
many-to-many and probably needs a bridge table, and — for genuinely
unconnected tables — a best-effort suggestion of where a relationship might
belong, based on matching key-like column names and types.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..tmdl.model import SemanticModel


@dataclass
class RelationshipGapReport:
    disconnected_tables: list[str] = field(default_factory=list)
    inactive_relationships: list[str] = field(default_factory=list)
    many_to_many_pairs: list[str] = field(default_factory=list)
    missing_date_table: bool = False
    suggested_relationships: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "disconnected_tables": self.disconnected_tables,
            "inactive_relationships": self.inactive_relationships,
            "many_to_many_pairs": self.many_to_many_pairs,
            "missing_date_table": self.missing_date_table,
            "suggested_relationships": self.suggested_relationships,
        }


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def suggest_relationships(model: SemanticModel) -> list[dict]:
    """
    For tables with no existing relationship between them, look for columns
    that share a normalized name and data type — a common signature of an
    unmodeled foreign key.
    """
    connected_pairs = {
        frozenset((r.from_table, r.to_table)) for r in model.relationships
    }
    suggestions: list[dict] = []
    table_names = list(model.tables.keys())

    for i, t1 in enumerate(table_names):
        for t2 in table_names[i + 1:]:
            if frozenset((t1, t2)) in connected_pairs:
                continue
            for c1 in model.tables[t1].columns.values():
                for c2 in model.tables[t2].columns.values():
                    if (
                        _normalize(c1.name) == _normalize(c2.name)
                        and c1.data_type == c2.data_type
                        and _normalize(c1.name) not in ("", "id")
                    ):
                        suggestions.append({
                            "from_table": t1, "from_column": c1.name,
                            "to_table": t2, "to_column": c2.name,
                            "reason": f"matching name/type: {c1.name} ({c1.data_type})",
                        })
    return suggestions


def relationship_gap_report(model: SemanticModel, classifications: dict[str, str]) -> RelationshipGapReport:
    report = RelationshipGapReport()

    connected = {
        t for r in model.relationships for t in (r.from_table, r.to_table)
    }
    report.disconnected_tables = [t for t in model.tables if t not in connected]

    for r in model.relationships:
        if not r.is_active:
            report.inactive_relationships.append(f"{r.from_table}.{r.from_column} -> {r.to_table}.{r.to_column}")
        if r.from_cardinality == "many" and r.to_cardinality == "many":
            report.many_to_many_pairs.append(f"{r.from_table} <-> {r.to_table}")

    report.missing_date_table = not any(c == "date" for c in classifications.values())
    report.suggested_relationships = suggest_relationships(model)
    return report
