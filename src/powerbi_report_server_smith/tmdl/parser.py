"""
A pragmatic TMDL parser.

TMDL is an indentation-based text format (tabs, conventionally). This module
does NOT attempt full spec fidelity for every TOM object type — it focuses on
the constructs the audit/workflow tools actually need: tables, columns,
measures, relationships, and `///` doc-comment descriptions.

Design choice: rather than guess at exact serialization for less-documented
constructs (e.g. Power Query "query group" folder assignment inside
expressions.tmdl), this parser sticks to well-established, stable TMDL
properties (dataType, sourceColumn, summarizeBy, displayFolder, isHidden,
fromColumn/toColumn, crossFilteringBehavior, isActive). See README for the
known v1 limitation around Power Query query groups.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class TmdlNode:
    """One line of a TMDL block, with its parsed children."""
    header: str                 # e.g. "table Sales" or "dataType: int64"
    indent: int
    description: str | None = None   # from a preceding /// comment, if any
    children: list["TmdlNode"] = field(default_factory=list)


def _indent_of(line: str) -> int:
    """TMDL indents with tabs by convention; tolerate 4-space indents too."""
    stripped = line.lstrip("\t ")
    raw = line[: len(line) - len(stripped)]
    if "\t" in raw:
        return raw.count("\t")
    return len(raw) // 4


def parse_tmdl_text(text: str) -> list[TmdlNode]:
    """Build a shallow indentation tree from raw TMDL text."""
    lines = text.replace("\r\n", "\n").split("\n")

    # Strip blank lines but keep /// description comments attached to the
    # next non-comment, non-blank line at the same indent.
    pending_description: str | None = None
    flat: list[tuple[int, str, str | None]] = []  # (indent, header, description)

    for raw_line in lines:
        if not raw_line.strip():
            continue
        indent = _indent_of(raw_line)
        content = raw_line.strip("\n").lstrip("\t ").rstrip()

        if content.startswith("///"):
            comment = content[3:].strip()
            pending_description = (
                comment if pending_description is None
                else f"{pending_description} {comment}"
            )
            continue

        flat.append((indent, content, pending_description))
        pending_description = None

    # Build the tree via a stack keyed on indent depth.
    root: list[TmdlNode] = []
    stack: list[tuple[int, list[TmdlNode]]] = [(-1, root)]

    for indent, header, description in flat:
        node = TmdlNode(header=header, indent=indent, description=description)
        while stack and indent <= stack[-1][0]:
            stack.pop()
        stack[-1][1].append(node)
        stack.append((indent, node.children))

    return root


_PROP_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\s*:\s*(.*)$")


def block_properties(node: TmdlNode) -> dict[str, str]:
    """
    Collect simple `key: value` children of a node into a flat dict.
    Bare flags (e.g. a lone `isHidden` line, no colon) are recorded as "true".
    """
    props: dict[str, str] = {}
    for child in node.children:
        m = _PROP_RE.match(child.header)
        if m:
            props[m.group(1)] = m.group(2).strip()
        elif re.match(r"^[A-Za-z][A-Za-z0-9_]*$", child.header):
            props[child.header] = "true"
    return props


def strip_quotes(name: str) -> str:
    name = name.strip()
    if len(name) >= 2 and name[0] == "'" and name[-1] == "'":
        return name[1:-1]
    return name
