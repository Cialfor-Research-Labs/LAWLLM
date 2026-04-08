import json
import os
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

INPUT_FOLDER = "txt_acts"
OUTPUT_FOLDER = "New_JSON_acts"

SCHEMA_VERSION = "v2"
JURISDICTION = "India"

MAX_CHUNK_WORDS = 220
MIN_CHUNK_WORDS = 3

SECTION_RE = re.compile(r"(?m)^\s*(\d+[A-Za-z]?)\.\s+([^\n]+)")
CHAPTER_RE = re.compile(r"(?im)^\s*chapter\s+[ivxlcdm0-9]+\b")


# =========================
# IO
# =========================
def read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1") as f:
            return f.read()


# =========================
# NORMALIZATION
# =========================
def normalize_line(line: str) -> str:
    line = line.replace("\xad", "")
    line = line.replace("\u200b", "")
    line = re.sub(r"\s+", " ", line.strip())
    return line


def clean_inline(text: str) -> str:
    text = text.replace("\xad", "")
    text = text.replace("\u200b", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_block(text: str) -> str:
    lines = [normalize_line(x) for x in text.splitlines()]
    lines = [x for x in lines if x]
    return "\n".join(lines).strip()


# =========================
# STRUCTURAL PARSE (PASS A)
# =========================
def infer_title(raw_text: str, filename: str) -> str:
    pattern = re.compile(
        r"(?im)^\s*(The\s+.+?(?:Act|Code|Sanhita|Adhiniyam)(?:,\s*\d{4})?.*)$"
    )
    match = pattern.search(raw_text)
    if match:
        return clean_inline(match.group(1))
    return filename.replace(".txt", "")


def find_body_start(raw_text: str) -> int:
    chapter_match = CHAPTER_RE.search(raw_text)
    first_section_match = SECTION_RE.search(raw_text)

    if chapter_match:
        return chapter_match.start()

    if first_section_match:
        return first_section_match.start()

    return 0


def split_sections(raw_text: str) -> List[Dict[str, str]]:
    body_start = find_body_start(raw_text)
    body_text = raw_text[body_start:]

    matches = list(SECTION_RE.finditer(body_text))
    sections: List[Dict[str, str]] = []

    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body_text)

        section_num = match.group(1)
        section_title = clean_inline(match.group(2).rstrip(".:-— "))

        block = body_text[start:end].strip()
        body = block[(match.end() - start):].strip()

        sections.append(
            {
                "section_number": section_num,
                "section_title": section_title,
                "raw_block": block,
                "raw_body": body,
            }
        )

    return sections


def is_roman(label: str) -> bool:
    raw = label.strip("()").lower()
    return bool(raw) and len(raw) <= 8 and re.fullmatch(r"[ivxlcdm]+", raw) is not None


def extract_amendments(text: str) -> List[str]:
    candidates: List[str] = []

    bracketed = re.findall(r"\[(.*?)\]", text)
    for item in bracketed:
        item_clean = clean_inline(item)
        if re.search(r"\b(act|w\.e\.f\.|inserted|substituted|omitted|amended|ins\.|subs\.)\b", item_clean, re.IGNORECASE):
            candidates.append(item_clean)

    inline = re.findall(
        r"\b(?:Ins\.|Subs\.|Inserted|Substituted|Omitted|Amended)\s+by\s+Act[^.;\n]*",
        text,
        flags=re.IGNORECASE,
    )
    candidates.extend(clean_inline(x) for x in inline)

    seen = set()
    unique = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def make_context_path(section_number: str, subsection: Optional[str], clause: Optional[str], subclause: Optional[str]) -> str:
    parts = [f"Section {section_number}"]
    if subsection:
        parts.append(subsection)
    if clause:
        parts.append(clause)
    if subclause:
        parts.append(subclause)
    return " > ".join(parts)


def parent_from_context(section_number: str, subsection: Optional[str], clause: Optional[str], subclause: Optional[str], unit_type: str) -> Optional[str]:
    if unit_type == "section":
        return None

    if unit_type == "subsection":
        return make_context_path(section_number, None, None, None)

    if unit_type == "clause":
        if subsection:
            return make_context_path(section_number, subsection, None, None)
        return make_context_path(section_number, None, None, None)

    if unit_type == "subclause":
        if clause:
            return make_context_path(section_number, subsection, clause, None)
        if subsection:
            return make_context_path(section_number, subsection, None, None)
        return make_context_path(section_number, None, None, None)

    # proviso / explanation / illustration attach to deepest active node.
    if subclause:
        return make_context_path(section_number, subsection, clause, subclause)
    if clause:
        return make_context_path(section_number, subsection, clause, None)
    if subsection:
        return make_context_path(section_number, subsection, None, None)
    return make_context_path(section_number, None, None, None)


def parse_section_units(section: Dict[str, str]) -> List[Dict[str, Any]]:
    section_number = section["section_number"]
    section_title = section["section_title"]
    raw_body = section["raw_body"]

    lines = [normalize_line(x) for x in raw_body.splitlines()]

    units: List[Dict[str, Any]] = []
    subsection: Optional[str] = None
    clause: Optional[str] = None
    subclause: Optional[str] = None

    proviso_idx = 0
    explanation_idx = 0
    illustration_idx = 0

    current: Dict[str, Any] = {
        "unit_type": "section",
        "label": section_number,
        "subsection": None,
        "clause": None,
        "subclause": None,
        "text_parts": [],
    }

    def flush_current() -> None:
        nonlocal current
        text = clean_inline(" ".join(current["text_parts"]))
        if not text:
            current["text_parts"] = []
            return

        unit_type = current["unit_type"]
        context_path = make_context_path(
            section_number,
            current["subsection"],
            current["clause"],
            current["subclause"],
        )
        parent_context = parent_from_context(
            section_number,
            current["subsection"],
            current["clause"],
            current["subclause"],
            unit_type,
        )

        units.append(
            {
                "unit_id": str(uuid.uuid4()),
                "unit_type": unit_type,
                "label": current["label"],
                "section_number": section_number,
                "section_title": section_title,
                "subsection": current["subsection"],
                "clause": current["clause"],
                "subclause": current["subclause"],
                "context_path": context_path,
                "parent_context": parent_context,
                "text": text,
                "amendments": extract_amendments(text),
            }
        )

        current["text_parts"] = []

    for line in lines:
        if not line:
            continue

        m_subsection = re.match(r"^\((\d+[A-Za-z]?)\)\s*(.*)$", line)
        if m_subsection:
            flush_current()
            subsection = f"({m_subsection.group(1)})"
            clause = None
            subclause = None

            current = {
                "unit_type": "subsection",
                "label": subsection,
                "subsection": subsection,
                "clause": None,
                "subclause": None,
                "text_parts": [m_subsection.group(2)] if m_subsection.group(2) else [],
            }
            continue

        m_alpha = re.match(r"^\(([a-z]{1,3})\)\s*(.*)$", line)
        if m_alpha:
            marker = f"({m_alpha.group(1)})"
            tail = m_alpha.group(2)
            flush_current()

            if is_roman(marker) and clause is not None:
                subclause = marker
                current = {
                    "unit_type": "subclause",
                    "label": marker,
                    "subsection": subsection,
                    "clause": clause,
                    "subclause": subclause,
                    "text_parts": [tail] if tail else [],
                }
            else:
                clause = marker
                subclause = None
                current = {
                    "unit_type": "clause",
                    "label": marker,
                    "subsection": subsection,
                    "clause": clause,
                    "subclause": None,
                    "text_parts": [tail] if tail else [],
                }
            continue

        if re.match(r"^provided(?:\s+further)?\s+that\b", line, flags=re.IGNORECASE):
            flush_current()
            proviso_idx += 1
            current = {
                "unit_type": "proviso",
                "label": f"proviso_{proviso_idx}",
                "subsection": subsection,
                "clause": clause,
                "subclause": subclause,
                "text_parts": [line],
            }
            continue

        if re.match(r"^explanation(?:\s*\d+)?\b", line, flags=re.IGNORECASE):
            flush_current()
            explanation_idx += 1
            current = {
                "unit_type": "explanation",
                "label": f"explanation_{explanation_idx}",
                "subsection": subsection,
                "clause": clause,
                "subclause": subclause,
                "text_parts": [line],
            }
            continue

        if re.match(r"^illustrations?\b", line, flags=re.IGNORECASE):
            flush_current()
            illustration_idx += 1
            current = {
                "unit_type": "illustration",
                "label": f"illustration_{illustration_idx}",
                "subsection": subsection,
                "clause": clause,
                "subclause": subclause,
                "text_parts": [line],
            }
            continue

        current["text_parts"].append(line)

    flush_current()

    return units


def build_structure(raw_text: str, filename: str) -> Dict[str, Any]:
    title = infer_title(raw_text, filename)
    document_id = filename.replace(".txt", "")

    section_blocks = split_sections(raw_text)
    sections: List[Dict[str, Any]] = []

    for block in section_blocks:
        units = parse_section_units(block)
        full_section_text = normalize_block(block["raw_block"])
        sections.append(
            {
                "section_number": block["section_number"],
                "section_title": block["section_title"],
                "full_section_text": full_section_text,
                "units": units,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "document_id": document_id,
        "document_type": "act",
        "title": title,
        "jurisdiction": JURISDICTION,
        "source_file": filename,
        "sections": sections,
    }


# =========================
# RETRIEVAL CHUNKING (PASS B)
# =========================
def sentence_split(text: str) -> List[str]:
    pieces = re.split(r"(?<=[.!?;:])\s+", text)
    return [clean_inline(x) for x in pieces if clean_inline(x)]


def split_semantic(text: str, max_words: int = MAX_CHUNK_WORDS) -> List[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text]

    sentences = sentence_split(text)
    if not sentences:
        return [text]

    chunks: List[str] = []
    current: List[str] = []
    current_words = 0

    for sent in sentences:
        sent_words = len(sent.split())

        if sent_words > max_words:
            # Keep sentence integrity where possible; fallback to word slices.
            sent_tokens = sent.split()
            for i in range(0, len(sent_tokens), max_words):
                part = " ".join(sent_tokens[i : i + max_words]).strip()
                if part:
                    if current:
                        chunks.append(clean_inline(" ".join(current)))
                        current = []
                        current_words = 0
                    chunks.append(part)
            continue

        if current_words + sent_words > max_words and current:
            chunks.append(clean_inline(" ".join(current)))
            current = [sent]
            current_words = sent_words
        else:
            current.append(sent)
            current_words += sent_words

    if current:
        chunks.append(clean_inline(" ".join(current)))

    return [x for x in chunks if x]


def context_text_lookup(sections: List[Dict[str, Any]]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}

    for section in sections:
        section_context = f"Section {section['section_number']}"
        lookup[section_context] = section["full_section_text"]

        for unit in section["units"]:
            # Keep first encountered main node for a context key.
            key = unit["context_path"]
            if key not in lookup and unit["unit_type"] in {"section", "subsection", "clause", "subclause"}:
                lookup[key] = unit["text"]

    return lookup


def build_retrieval_chunks(structure: Dict[str, Any]) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    section_lookup = {s["section_number"]: s for s in structure["sections"]}
    context_lookup = context_text_lookup(structure["sections"])

    chunk_index = 0
    for section in structure["sections"]:
        section_number = section["section_number"]
        full_section_text = section["full_section_text"]

        for unit in section["units"]:
            parts = split_semantic(unit["text"], max_words=MAX_CHUNK_WORDS)
            part_total = len(parts)

            for part_idx, part in enumerate(parts, start=1):
                if len(part.split()) < MIN_CHUNK_WORDS:
                    continue

                parent_text = context_lookup.get(unit["parent_context"]) if unit["parent_context"] else None

                chunks.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "chunk_id": str(uuid.uuid4()),
                        "document_id": structure["document_id"],
                        "document_type": structure["document_type"],
                        "title": structure["title"],
                        "jurisdiction": structure["jurisdiction"],
                        "source_file": structure["source_file"],
                        "section_number": section_number,
                        "section_title": section_lookup[section_number]["section_title"],
                        "unit_id": unit["unit_id"],
                        "unit_type": unit["unit_type"],
                        "unit_label": unit["label"],
                        "hierarchy": {
                            "subsection": unit["subsection"],
                            "clause": unit["clause"],
                            "subclause": unit["subclause"],
                        },
                        "context_path": unit["context_path"],
                        "parent_context": unit["parent_context"],
                        "chunk_text": part,
                        "parent_text": parent_text,
                        "full_section_text": full_section_text,
                        "amendments": unit["amendments"],
                        "part_index_in_unit": part_idx,
                        "total_parts_in_unit": part_total,
                        "word_count": len(part.split()),
                        "chunk_index": chunk_index,
                    }
                )
                chunk_index += 1

    return chunks


# =========================
# MAIN
# =========================
def process_file(filename: str) -> Dict[str, Any]:
    raw_text = read_file(os.path.join(INPUT_FOLDER, filename))
    structure = build_structure(raw_text, filename)
    chunks = build_retrieval_chunks(structure)

    output = {
        "schema_version": SCHEMA_VERSION,
        "document": {
            "document_id": structure["document_id"],
            "document_type": structure["document_type"],
            "title": structure["title"],
            "jurisdiction": structure["jurisdiction"],
            "source_file": structure["source_file"],
            "sections_count": len(structure["sections"]),
            "chunks_count": len(chunks),
        },
        "sections": structure["sections"],
        "chunks": chunks,
    }

    return output


def process_all() -> None:
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    files = sorted(
        f for f in os.listdir(INPUT_FOLDER) if f.endswith(".txt") and not f.startswith(".")
    )

    print(f"Found {len(files)} acts")

    for filename in files:
        print(f"\nProcessing: {filename}")
        output = process_file(filename)

        out_path = os.path.join(OUTPUT_FOLDER, filename.replace(".txt", ".json"))
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(
            f"Saved: {out_path} | sections={output['document']['sections_count']} | chunks={output['document']['chunks_count']}"
        )


if __name__ == "__main__":
    process_all()
