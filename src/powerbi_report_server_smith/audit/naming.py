"""
Naming audit.

Two passes:
 1. Per-object convention check against configurable rules (default: no
    underscores, must start with a capital letter, no bare abbreviations).
 2. Cross-model consistency check: the same underlying concept spelled two
    different ways (e.g. "CustomerKey" in one table, "cust_key" in another)
    gets flagged so you can standardize before promoting out of Staging.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..tmdl.model import SemanticModel

DEFAULT_RULES = {
    "no_underscores": True,
    "must_start_uppercase": True,
    "no_all_lowercase": True,
    "max_consecutive_uppercase": 4,  # allows acronyms like "ID", "URL" but flags "CUSTNM"
}


@dataclass
class NamingIssue:
    object_type: str   # "table" | "column" | "measure"
    table: str
    name: str
    rule: str
    suggestion: str | None = None


@dataclass
class NamingReport:
    issues: list[NamingIssue] = field(default_factory=list)
    rename_plan: dict[str, str] = field(default_factory=dict)  # old -> suggested new

    def as_dict(self) -> dict:
        return {
            "issues": [
                {"object_type": i.object_type, "table": i.table, "name": i.name,
                 "rule": i.rule, "suggestion": i.suggestion}
                for i in self.issues
            ],
            "rename_plan": self.rename_plan,
        }


def _suggest_name(name: str) -> str:
    """Very small, conservative auto-suggestion: snake/kebab -> PascalCase-ish."""
    parts = re.split(r"[_\-\s]+", name)
    parts = [p for p in parts if p]
    if not parts:
        return name
    return "".join(p[:1].upper() + p[1:] for p in parts)


def _check_name(name: str, rules: dict) -> list[str]:
    problems = []
    if rules.get("no_underscores") and "_" in name:
        problems.append("contains underscore")
    if rules.get("must_start_uppercase") and name and not name[0].isupper():
        problems.append("does not start with a capital letter")
    if rules.get("no_all_lowercase") and name.islower():
        problems.append("all lowercase")
    max_upper = rules.get("max_consecutive_uppercase")
    if max_upper:
        run = 0
        longest = 0
        for ch in name:
            if ch.isupper():
                run += 1
                longest = max(longest, run)
            else:
                run = 0
        if longest > max_upper:
            problems.append(f"{longest} consecutive uppercase letters — looks like a raw abbreviation")
    return problems


def audit_naming(model: SemanticModel, rules: dict | None = None) -> NamingReport:
    rules = {**DEFAULT_RULES, **(rules or {})}
    issues: list[NamingIssue] = []
    rename_plan: dict[str, str] = {}

    # Pass 1 — per-object convention.
    for table_name, table in model.tables.items():
        for problem in _check_name(table_name, rules):
            issues.append(NamingIssue("table", table_name, table_name, problem,
                                       _suggest_name(table_name)))
        for col in table.columns.values():
            for problem in _check_name(col.name, rules):
                suggestion = _suggest_name(col.name)
                issues.append(NamingIssue("column", table_name, col.name, problem, suggestion))
                rename_plan[f"{table_name}.{col.name}"] = suggestion
        for meas in table.measures.values():
            for problem in _check_name(meas.name, rules):
                issues.append(NamingIssue("measure", table_name, meas.name, problem,
                                           _suggest_name(meas.name)))

    # Pass 2 — cross-model consistency: same normalized concept, different spelling.
    def normalize(n: str) -> str:
        return re.sub(r"[^a-z0-9]", "", n.lower())

    seen: dict[str, set[str]] = {}
    for table_name, table in model.tables.items():
        for col in table.columns.values():
            key = normalize(col.name)
            seen.setdefault(key, set()).add(col.name)

    for norm, spellings in seen.items():
        if len(spellings) > 1:
            issues.append(NamingIssue(
                object_type="column", table="(cross-model)", name="/".join(sorted(spellings)),
                rule="same concept spelled inconsistently across tables",
                suggestion=_suggest_name(sorted(spellings)[0]),
            ))

    return NamingReport(issues=issues, rename_plan=rename_plan)
