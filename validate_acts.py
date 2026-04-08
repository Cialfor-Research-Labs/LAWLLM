"""
validate_acts.py — Validator for litigation-grade legal act JSON files.
Checks schema, required fields, empty chunks, and reports stats.
"""

import os
import json

JSON_DIR = "JSON_acts"

REQUIRED_FIELDS = [
    "document_id", "document_type", "title", "year", "domain",
    "jurisdiction", "act_name", "chapter", "section_number", "section_title",
    "source_path", "page_number", "chunk_id", "chunk_index",
    "total_chunks_in_section", "chunk_text", "citations",
    "cross_references", "entities", "keywords",
]

ENTITY_SUBFIELDS = ["statutes", "sections", "legal_terms"]


def validate_file(path: str) -> tuple[bool, list[str], int]:
    """Returns (is_valid, errors, record_count)."""
    errors = []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, [f"Load error: {e}"], 0

    if not isinstance(data, list):
        return False, ["Root element must be a list"], 0

    for idx, item in enumerate(data):
        # Required field presence and non-null
        for field in REQUIRED_FIELDS:
            if field not in item:
                errors.append(f"[record {idx}] Missing field '{field}'")
            elif item[field] is None:
                errors.append(f"[record {idx}] Field '{field}' is None")

        # Empty chunk_text is a hard failure
        chunk = item.get("chunk_text", "")
        if isinstance(chunk, str) and len(chunk.strip()) < 20:
            errors.append(f"[record {idx}] chunk_text is empty or too short (<20 chars)")

        # Entity sub-fields
        entities = item.get("entities", {})
        if not isinstance(entities, dict):
            errors.append(f"[record {idx}] 'entities' must be a dict")
        else:
            for sub in ENTITY_SUBFIELDS:
                if sub not in entities:
                    errors.append(f"[record {idx}] entities.'{sub}' missing")
                elif not isinstance(entities[sub], list):
                    errors.append(f"[record {idx}] entities.'{sub}' must be a list")

        # chunk_index / total sanity
        ci  = item.get("chunk_index", 0)
        tot = item.get("total_chunks_in_section", 0)
        if isinstance(ci, int) and isinstance(tot, int) and ci > tot:
            errors.append(f"[record {idx}] chunk_index ({ci}) > total_chunks_in_section ({tot})")

    return len(errors) == 0, errors, len(data)


def main():
    if not os.path.exists(JSON_DIR):
        print(f"Directory '{JSON_DIR}' not found.")
        return

    files = sorted(
        f for f in os.listdir(JSON_DIR)
        if f.endswith(".json") and not f.startswith(".")
    )

    total_files   = len(files)
    valid_count   = 0
    total_records = 0
    act_stats     = []

    print(f"Validating {total_files} JSON files in {JSON_DIR}/\n{'─'*60}")

    for filename in files:
        path = os.path.join(JSON_DIR, filename)
        ok, errors, n_records = validate_file(path)
        total_records += n_records
        act_stats.append((filename, n_records))

        if ok:
            print(f"  ✔  {filename}  ({n_records} records)")
            valid_count += 1
        else:
            print(f"  ✘  {filename}  ({n_records} records) — {len(errors)} error(s)")
            for e in errors[:5]:
                print(f"       • {e}")
            if len(errors) > 5:
                print(f"       • …and {len(errors) - 5} more")

    print(f"\n{'─'*60}")
    print(f"Files  : {valid_count}/{total_files} valid")
    print(f"Records: {total_records:,} total")

    print(f"\n{'─'*60} Record count per act:")
    for fname, cnt in sorted(act_stats, key=lambda x: -x[1]):
        bar = "█" * min(cnt // 50, 40)
        print(f"  {fname:<55} {cnt:>5}  {bar}")

    print()
    if valid_count == total_files:
        print("🚀  All files passed validation — litigation-grade dataset ready.")
    else:
        print(f"⚠️   {total_files - valid_count} file(s) failed — fix errors above before embedding.")


if __name__ == "__main__":
    main()
