#!/usr/bin/env python3
import csv
import json
import re
import uuid
from pathlib import Path


SPLIT_FRONT_RE = re.compile(r"^(?P<base>.+) \((?P<index>\d+)/(?P<total>\d+)\)$")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_rules() -> dict[str, dict]:
    config_path = repo_root() / "config" / "split_language_notes.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return {rule["front"]: rule for rule in data["rules"]}


def source_csv_path() -> Path:
    return repo_root() / "src" / "data" / "LanguageNotes.csv"


def ignored_csv_path() -> Path:
    return repo_root() / "src" / "data" / "LanguageNotesIgnored.csv"


def read_rows(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        return []
    with csv_path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(csv_path: Path, rows: list[dict]) -> None:
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["guid", "Language", "Topic", "Front", "Back", "tags"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def split_back(back: str, max_lines: int) -> list[str]:
    lines = back.splitlines(keepends=True)
    if len(lines) <= max_lines:
        return [back]
    return ["".join(lines[index:index + max_lines]) for index in range(0, len(lines), max_lines)]


def split_back_on_sections(back: str, heading_prefix: str) -> list[str]:
    lines = back.splitlines(keepends=True)
    section_indexes = [index for index, line in enumerate(lines) if line.startswith(heading_prefix)]
    if len(section_indexes) < 2:
        return [back]

    prefix = "".join(lines[:section_indexes[0]])
    chunks: list[str] = []
    for index, start in enumerate(section_indexes):
        end = section_indexes[index + 1] if index + 1 < len(section_indexes) else len(lines)
        chunk = "".join(lines[start:end])
        if index == 0 and prefix:
            chunk = prefix + chunk
        chunks.append(chunk)
    return chunks


def find_table_block(lines: list[str]) -> tuple[int, int] | None:
    separator_re = re.compile(r"^\|(?:\s*[-:]+\s*\|)+\s*$")
    for index in range(len(lines) - 2):
        if not lines[index].startswith("|"):
            continue
        if not separator_re.match(lines[index + 1].rstrip("\n")):
            continue

        end = index + 2
        while end < len(lines) and lines[end].startswith("|"):
            end += 1
        return index, end
    return None


def split_back_on_table_rows(back: str, rows_per_chunk: int) -> list[str]:
    lines = back.splitlines(keepends=True)
    table_block = find_table_block(lines)
    if table_block is None:
        return [back]

    start, end = table_block
    prefix = lines[:start]
    header = lines[start:start + 2]
    rows = lines[start + 2:end]
    suffix = lines[end:]
    if len(rows) <= rows_per_chunk:
        return [back]

    chunks: list[str] = []
    for index in range(0, len(rows), rows_per_chunk):
        row_group = rows[index:index + rows_per_chunk]
        chunk_lines: list[str] = []
        if index == 0:
            chunk_lines.extend(prefix)
        chunk_lines.extend(header)
        chunk_lines.extend(row_group)
        if index + rows_per_chunk >= len(rows):
            chunk_lines.extend(suffix)
        chunks.append("".join(chunk_lines))
    return chunks


def merge_rows(rows: list[dict], preferred_guid: str | None, rule: dict | None = None) -> dict:
    ordered_rows = sorted(
        rows,
        key=lambda row: int(SPLIT_FRONT_RE.match(row["Front"]).group("index")) if SPLIT_FRONT_RE.match(row["Front"]) else 1,
    )
    first = dict(ordered_rows[0])
    match = SPLIT_FRONT_RE.match(first["Front"])
    if match:
        first["Front"] = match.group("base")
    first["guid"] = preferred_guid or first["guid"]

    split_mode = rule.get("split_mode") if rule else None
    if split_mode == "markdown_table_rows":
        merged_parts = [ordered_rows[0]["Back"]]
        header = None
        first_lines = ordered_rows[0]["Back"].splitlines(keepends=True)
        table_block = find_table_block(first_lines)
        if table_block is not None:
            start, _ = table_block
            header = "".join(first_lines[start:start + 2])

        for row in ordered_rows[1:]:
            back = row["Back"]
            if header and back.startswith(header):
                back = back[len(header):]
            merged_parts.append(back)
        first["Back"] = "".join(merged_parts)
    else:
        first["Back"] = "".join(row["Back"] for row in ordered_rows)

    return first


def split_row(row: dict, rule: dict) -> list[dict]:
    split_mode = rule.get("split_mode", "line_count")
    if split_mode == "markdown_sections":
        chunks = split_back_on_sections(row["Back"], rule.get("heading_prefix", "## "))
    elif split_mode == "markdown_table_rows":
        chunks = split_back_on_table_rows(row["Back"], rule.get("table_rows_per_chunk", 25))
    else:
        chunks = split_back(row["Back"], rule.get("max_lines", 50))

    if len(chunks) == 1:
        row["guid"] = rule.get("guid", row["guid"])
        return [row]

    total = len(chunks)
    split_rows: list[dict] = []
    for index, chunk in enumerate(chunks, start=1):
        split_row_data = dict(row)
        split_row_data["guid"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{rule['guid']}:{index}"))
        split_row_data["Front"] = f"{row['Front']} ({index}/{total})"
        split_row_data["Back"] = chunk
        split_rows.append(split_row_data)
    return split_rows


def normalize_rows(rows: list[dict], rules: dict[str, dict]) -> list[dict]:
    grouped_split_rows: dict[str, list[dict]] = {}
    unsplit_rows: list[dict] = []

    for row in rows:
        match = SPLIT_FRONT_RE.match(row["Front"])
        if match:
            grouped_split_rows.setdefault(match.group("base"), []).append(row)
        else:
            unsplit_rows.append(row)

    normalized: list[dict] = []
    emitted_group_rows: set[str] = set()

    for row in unsplit_rows:
        rule = rules.get(row["Front"])
        if rule and rule["mode"] == "split":
            normalized.extend(split_row(dict(row), rule))
            continue

        if rule and rule["mode"] == "keep":
            row = dict(row)
            row["guid"] = rule.get("guid", row["guid"])

        normalized.append(row)
        emitted_group_rows.add(row["Front"])

    for base_front, split_rows in grouped_split_rows.items():
        if base_front in emitted_group_rows:
            continue

        rule = rules.get(base_front)
        merged_row = merge_rows(split_rows, rule.get("guid") if rule else None, rule)
        if rule and rule["mode"] == "split":
            normalized.extend(split_row(merged_row, rule))
        else:
            normalized.append(merged_row)

    return normalized


def main() -> int:
    rules = load_rules()
    rows = read_rows(source_csv_path()) + read_rows(ignored_csv_path())

    normalized_rows = normalize_rows(rows, rules)
    main_rows: list[dict] = []
    ignored_rows: list[dict] = []

    for row in normalized_rows:
        match = SPLIT_FRONT_RE.match(row["Front"])
        base_front = match.group("base") if match else row["Front"]
        rule = rules.get(base_front)
        if rule and rule["mode"] == "ignore":
            ignored_rows.append(row)
        else:
            main_rows.append(row)

    write_rows(source_csv_path(), main_rows)
    write_rows(ignored_csv_path(), ignored_rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
