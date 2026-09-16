"""
Star-schema classification and sanity check.

Heuristic (topology-first, matching how Power BI itself treats relationship
direction): the `from_table` side of a relationship is conventionally the
"many" side unless the TMDL explicitly says otherwise via fromCardinality/
toCardinality. We classify off that, then sanity-check with column shape
(mostly-numeric non-key columns => fact-like; mostly-descriptive/text
columns => dimension-like).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..tmdl.model import SemanticModel, Table

_DATE_TABLE_NAME_HINTS = ("date", "calendar", "datedim", "dimdate")
_NUMERIC_TYPES = {"int64", "double", "decimal", "currency"}


@dataclass
class TableFinding:
    table: str
    classification: str
    severity: str  # "info" | "warning" | "critical"
    message: str


@dataclass
class StarSchemaReport:
    score: int
    classifications: dict[str, str]
    findings: list[TableFinding] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "classifications": self.classifications,
            "findings": [
                {"table": f.table, "classification": f.classification,
                 "severity": f.severity, "message": f.message}
                for f in self.findings
            ],
        }


def _looks_like_date_table(table: Table) -> bool:
    if any(h in table.name.lower() for h in _DATE_TABLE_NAME_HINTS):
        return True
    date_cols = [c for c in table.columns.values() if c.data_type in ("dateTime", "date")]
    return len(date_cols) >= 1 and len(table.columns) <= 6


def _looks_like_bridge(table: Table, many_count: int, one_count: int) -> bool:
    if many_count == 0 or one_count == 0:
        return False
    non_key_cols = [c for c in table.columns.values() if not c.is_key]
    # A bridge table is mostly keys, with little or no descriptive payload.
    return len(non_key_cols) <= 1


def audit_star_schema(model: SemanticModel) -> StarSchemaReport:
    classifications: dict[str, str] = {}
    findings: list[TableFinding] = []
    score = 100

    many_counts: dict[str, int] = {t: 0 for t in model.tables}
    one_counts: dict[str, int] = {t: 0 for t in model.tables}

    for rel in model.relationships:
        is_many_from = (rel.from_cardinality or "many") == "many"
        is_one_to = (rel.to_cardinality or "one") == "one"
        if rel.from_table in many_counts and is_many_from:
            many_counts[rel.from_table] += 1
        if rel.to_table in one_counts and is_one_to:
            one_counts[rel.to_table] += 1

    for name, table in model.tables.items():
        many_ct = many_counts.get(name, 0)
        one_ct = one_counts.get(name, 0)
        total = many_ct + one_ct

        if total == 0:
            classifications[name] = "disconnected"
            findings.append(TableFinding(
                table=name, classification="disconnected", severity="warning",
                message="No relationships found — table is not connected to the model."
            ))
            score -= 8
            continue

        # Date-dimension check only applies to tables that behave like a
        # dimension (pure one-side). A fact table with a date column is
        # still a fact table, not a date dimension.
        if one_ct > 0 and many_ct == 0 and _looks_like_date_table(table):
            classifications[name] = "date"
            continue

        if _looks_like_bridge(table, many_ct, one_ct):
            classifications[name] = "bridge"
            findings.append(TableFinding(
                table=name, classification="bridge", severity="info",
                message="Mostly-key columns with relationships on both sides — "
                        "looks like a many-to-many bridge table."
            ))
            continue

        if many_ct > 0 and one_ct == 0:
            classifications[name] = "fact"
        elif one_ct > 0 and many_ct == 0:
            classifications[name] = "dimension"
        else:
            classifications[name] = "unclear"
            findings.append(TableFinding(
                table=name, classification="unclear", severity="warning",
                message=f"Participates as both many-side ({many_ct}) and "
                        f"one-side ({one_ct}) without looking like a bridge table — "
                        "review manually, may indicate a snowflake."
            ))
            score -= 10

        # Sanity-check fact/dimension against column shape.
        numeric_non_key = [
            c for c in table.columns.values()
            if c.data_type in _NUMERIC_TYPES and not c.is_key
        ]
        text_cols = [c for c in table.columns.values() if c.data_type == "string"]
        if classifications[name] == "fact" and not numeric_non_key:
            findings.append(TableFinding(
                table=name, classification="fact", severity="info",
                message="Classified as fact by topology, but has no numeric "
                        "non-key columns — check this is really a fact table."
            ))
        if classifications[name] == "dimension" and not text_cols:
            findings.append(TableFinding(
                table=name, classification="dimension", severity="info",
                message="Classified as dimension by topology, but has no "
                        "descriptive text columns — check this is really a dimension."
            ))

        if not table.description:
            findings.append(TableFinding(
                table=name, classification=classifications[name], severity="info",
                message="No table description set."
            ))
            score -= 2

    # Fact-to-fact and snowflake (dimension-to-dimension) relationship checks.
    for rel in model.relationships:
        from_cls = classifications.get(rel.from_table)
        to_cls = classifications.get(rel.to_table)
        if from_cls == "fact" and to_cls == "fact":
            findings.append(TableFinding(
                table=f"{rel.from_table}->{rel.to_table}", classification="fact-to-fact",
                severity="critical",
                message="Relationship connects two fact-classified tables directly — "
                        "usually should route through a shared dimension instead."
            ))
            score -= 15
        if from_cls == "dimension" and to_cls == "dimension":
            findings.append(TableFinding(
                table=f"{rel.from_table}->{rel.to_table}", classification="snowflake",
                severity="warning",
                message="Relationship connects two dimension-classified tables — "
                        "this is a snowflake pattern; consider flattening into one dimension."
            ))
            score -= 5

    if not any(c == "date" for c in classifications.values()):
        findings.append(TableFinding(
            table="(model)", classification="date", severity="warning",
            message="No table looks like a date dimension. Star schemas should "
                    "have one clearly-marked date table."
        ))
        score -= 10

    score = max(0, min(100, score))
    return StarSchemaReport(score=score, classifications=classifications, findings=findings)
