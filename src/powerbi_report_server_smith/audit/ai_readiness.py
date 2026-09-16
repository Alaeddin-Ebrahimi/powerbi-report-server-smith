"""
AI-readiness scoring — how ready is this model for Fabric Copilot / Power BI
Data Agents to query well.

Covers what's actually reachable as TOM metadata (descriptions, hidden
technical columns, a marked date table) plus a presence check for the
PBIP-only Copilot config folder (AI instructions / AI data schema / Verified
Answers), which this tool can detect but — per the known limitation noted in
the plan — cannot safely author itself without a live Desktop/Fabric
round-trip to verify against.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..tmdl.model import SemanticModel


@dataclass
class AiReadinessReport:
    score: int
    table_description_coverage: float
    column_description_coverage: float
    measure_description_coverage: float
    has_marked_date_table: bool
    has_copilot_config: bool
    findings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "table_description_coverage": round(self.table_description_coverage, 2),
            "column_description_coverage": round(self.column_description_coverage, 2),
            "measure_description_coverage": round(self.measure_description_coverage, 2),
            "has_marked_date_table": self.has_marked_date_table,
            "has_copilot_config": self.has_copilot_config,
            "findings": self.findings,
        }


def score_ai_readiness(
    model: SemanticModel,
    classifications: dict[str, str],
    semantic_model_root: str | None = None,
) -> AiReadinessReport:
    findings: list[str] = []

    tables = list(model.tables.values())
    all_columns = [c for t in tables for c in t.columns.values() if not c.is_hidden]
    all_measures = [m for t in tables for m in t.measures.values()]

    def coverage(items, get_desc):
        if not items:
            return 1.0
        described = sum(1 for i in items if get_desc(i))
        return described / len(items)

    table_cov = coverage(tables, lambda t: t.description)
    column_cov = coverage(all_columns, lambda c: c.description)
    measure_cov = coverage(all_measures, lambda m: m.description)

    has_date = any(c == "date" for c in classifications.values())
    if not has_date:
        findings.append("No marked date dimension — time-based questions will be harder for Copilot to answer correctly.")

    has_copilot_config = False
    if semantic_model_root:
        copilot_dir = Path(semantic_model_root) / "Copilot"
        has_copilot_config = copilot_dir.is_dir()
        if not has_copilot_config:
            findings.append(
                "No Copilot/ config folder found (AI instructions, AI data schema, "
                "Verified Answers). These are PBIP-only and not editable via MCP — "
                "author them directly in Power BI Desktop once the model itself is clean."
            )

    if table_cov < 1.0:
        findings.append(f"{table_cov:.0%} of tables have descriptions — aim for 100%, Copilot uses these directly.")
    if column_cov < 0.8:
        findings.append(f"Only {column_cov:.0%} of visible columns have descriptions.")
    if measure_cov < 0.8 and all_measures:
        findings.append(f"Only {measure_cov:.0%} of measures have descriptions — these matter most for Copilot's DAX generation.")

    score = round(100 * (0.3 * table_cov + 0.25 * column_cov + 0.25 * measure_cov + 0.2 * (1.0 if has_date else 0.0)))

    return AiReadinessReport(
        score=score,
        table_description_coverage=table_cov,
        column_description_coverage=column_cov,
        measure_description_coverage=measure_cov,
        has_marked_date_table=has_date,
        has_copilot_config=has_copilot_config,
        findings=findings,
    )
