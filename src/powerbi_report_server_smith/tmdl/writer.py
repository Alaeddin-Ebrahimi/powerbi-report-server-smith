"""
Targeted TMDL edits.

Rather than re-serializing a whole parsed tree (risky — easy to subtly change
formatting TMDL/Desktop is picky about), these functions do minimal,
line-based surgery: find the exact header line for the object, then insert
or update just the lines that need to change. Everything else in the file is
byte-for-byte untouched.
"""
from __future__ import annotations

import re

from .parser import _indent_of, strip_quotes


def _object_name_from_header(line: str, header_prefix: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith(header_prefix):
        return None
    rest = stripped[len(header_prefix):]
    if rest.startswith("'"):
        m = re.match(r"'([^']*)'", rest)
        return m.group(1) if m else None
    # measures/partitions can have "= expr" after the name
    name_part = rest.split("=")[0].strip()
    return strip_quotes(name_part)


def _find_header_line(lines: list[str], header_prefix: str, object_name: str) -> int | None:
    for i, line in enumerate(lines):
        name = _object_name_from_header(line, header_prefix)
        if name == object_name:
            return i
    return None


def _block_end(lines: list[str], header_idx: int) -> int:
    """Index (exclusive) of where this object's block ends, based on indentation."""
    base_indent = _indent_of(lines[header_idx])
    for i in range(header_idx + 1, len(lines)):
        if not lines[i].strip():
            continue
        if _indent_of(lines[i]) <= base_indent:
            return i
    return len(lines)


def _indent_str(level: int) -> str:
    return "\t" * level


def set_description(text: str, header_prefix: str, object_name: str, description: str) -> str:
    """Insert or replace the `///` doc-comment directly above an object's header line."""
    lines = text.split("\n")
    idx = _find_header_line(lines, header_prefix, object_name)
    if idx is None:
        raise ValueError(f"Could not find {header_prefix.strip()} '{object_name}' in this file")

    header_indent = _indent_of(lines[idx])
    new_comment = f"{_indent_str(header_indent)}/// {description}"

    # Consume any existing /// lines directly above (contiguous, same indent).
    above = idx - 1
    while above >= 0 and lines[above].strip().startswith("///"):
        above -= 1
    existing_comment_start = above + 1

    new_lines = lines[:existing_comment_start] + [new_comment] + lines[idx:]
    return "\n".join(new_lines)


def set_property(text: str, header_prefix: str, object_name: str, prop_key: str, prop_value: str) -> str:
    """Insert or update a `key: value` property line inside an object's block."""
    lines = text.split("\n")
    idx = _find_header_line(lines, header_prefix, object_name)
    if idx is None:
        raise ValueError(f"Could not find {header_prefix.strip()} '{object_name}' in this file")

    header_indent = _indent_of(lines[idx])
    end = _block_end(lines, idx)
    prop_pattern = re.compile(rf"^\s*{re.escape(prop_key)}\s*:")

    for i in range(idx + 1, end):
        if prop_pattern.match(lines[i]):
            lines[i] = f"{_indent_str(header_indent + 1)}{prop_key}: {prop_value}"
            return "\n".join(lines)

    # Not found — insert right after the header line.
    new_line = f"{_indent_str(header_indent + 1)}{prop_key}: {prop_value}"
    new_lines = lines[:idx + 1] + [new_line] + lines[idx + 1:]
    return "\n".join(new_lines)


def append_relationship_block(text: str, relationship_id: str, from_table: str, from_column: str,
                               to_table: str, to_column: str,
                               cross_filtering_behavior: str = "automatic",
                               from_cardinality: str = "many", to_cardinality: str = "one") -> str:
    block = (
        f"\nrelationship {relationship_id}\n"
        f"\tfromColumn: {from_table}.{from_column}\n"
        f"\ttoColumn: {to_table}.{to_column}\n"
        f"\tcrossFilteringBehavior: {cross_filtering_behavior}\n"
        f"\tfromCardinality: {from_cardinality}\n"
        f"\ttoCardinality: {to_cardinality}\n"
    )
    return text.rstrip("\n") + "\n" + block
