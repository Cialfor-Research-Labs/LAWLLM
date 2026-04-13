import argparse
import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

INPUT_FOLDER = "txt_acts"
OUTPUT_FOLDER = "JSON_acts"

SCHEMA_VERSION = "v2"
JURISDICTION = "India"

MAX_CHUNK_WORDS = 220
MIN_CHUNK_WORDS = 3

ENACTMENT_RE = re.compile(r"\bbe it enacted\b", re.IGNORECASE)
SECTION_LINE_RE = re.compile(r"^\s*(\d+[A-Za-z]?)\.\s+(.+)$")
CHAPTER_LINE_RE = re.compile(r"^\s*\[?\s*chapter\s+([ivxlcdm0-9a-z]+)\b\.?\s*(.*)$", re.IGNORECASE)
AMENDMENT_NOTE_RE = re.compile(
    r"^\s*\d+\.\s*(?:Subs\.|Ins\.|Inserted|Substituted|Omitted|Amended|Repealed|Renumbered|for clause|for section)\b",
    re.IGNORECASE,
)
EDITORIAL_NOTE_RE = re.compile(
    r"^\s*\[(?:this is the version|note:|published on|commenced on|last updated|as amended by)\b",
    re.IGNORECASE,
)


def read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1") as f:
            return f.read()


def _strip_wrapping_quotes(text: str) -> str:
    stripped = text.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
        return stripped[1:-1].strip()
    return stripped


def normalize_line(line: str) -> str:
    line = line.replace("\ufeff", "")
    line = line.replace("\xad", "")
    line = line.replace("\u200b", "")
    line = line.replace("\u2013", "-")
    line = line.replace("\u2014", "-")
    line = line.replace("\u2015", "-")
    line = line.replace("\u2018", "'")
    line = line.replace("\u2019", "'")
    line = line.replace("\u201c", '"')
    line = line.replace("\u201d", '"')
    line = line.replace("\u2212", "-")
    line = re.sub(r"\s+", " ", line.strip())
    line = _strip_wrapping_quotes(line)
    line = re.sub(
        r"^\d+\[(?=(\d+[A-Za-z]?\.)|\([A-Za-z0-9ivxlcdm]+\)|Chapter\b)",
        "",
        line,
        flags=re.IGNORECASE,
    )
    line = re.sub(r"^\[(?=Chapter\b)", "", line, flags=re.IGNORECASE)
    line = re.sub(r"\]$", "", line) if re.match(r"^(?:\(?\d+[A-Za-z]?\)?|Chapter\b)", line, re.IGNORECASE) else line
    return line.strip()


def clean_inline(text: str) -> str:
    text = normalize_line(text)
    text = text.replace("[", "").replace("]", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_block(lines: List[str]) -> str:
    cleaned = [clean_inline(line) for line in lines if clean_inline(line)]
    return "\n".join(cleaned).strip()


def slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", str(text or "").strip())
    slug = slug.strip("_").upper()
    return slug or "X"


def stable_id(*parts: str, prefix: str = "") -> str:
    joined = "||".join(str(p or "") for p in parts)
    digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}{digest}" if prefix else digest


def infer_title(lines: List[str], filename: str) -> str:
    title_pattern = re.compile(
        r"^\s*(The\s+.+?(?:Act|Code|Sanhita|Adhiniyam)(?:,\s*\d{4})?)\s*$",
        re.IGNORECASE,
    )
    for line in lines[:40]:
        if not line or line.upper() in {"ARRANGEMENT OF SECTIONS", "SECTIONS"}:
            continue
        match = title_pattern.match(line)
        if match:
            return clean_inline(match.group(1))
    return filename.replace(".txt", "")


def infer_year(title: str, filename: str) -> Optional[int]:
    candidates = [title, filename]
    for candidate in candidates:
        match = re.search(r"\b(18|19|20)\d{2}\b", candidate or "")
        if match:
            return int(match.group(0))
    return None


def build_aliases(title: str, filename: str) -> List[str]:
    aliases: List[str] = []
    for candidate in [title, filename.replace(".txt", "")]:
        clean = clean_inline(candidate)
        if clean and clean not in aliases:
            aliases.append(clean)
        no_year = clean_inline(re.sub(r",?\s*\b(18|19|20)\d{2}\b", "", clean))
        if no_year and no_year not in aliases:
            aliases.append(no_year)
    return aliases


def should_skip_line(line: str) -> bool:
    if not line:
        return True
    if EDITORIAL_NOTE_RE.match(line):
        return True
    if line.upper() in {"ARRANGEMENT OF SECTIONS", "SECTIONS", "CONTENTS", "TABLE OF CONTENTS"}:
        return True
    return False


def preprocess_lines(raw_text: str) -> List[str]:
    lines: List[str] = []
    for raw_line in raw_text.splitlines():
        line = normalize_line(raw_line)
        if should_skip_line(line):
            continue
        lines.append(line)
    return lines


def find_body_start(lines: List[str]) -> int:
    enactment_idx = -1
    for idx, line in enumerate(lines):
        if ENACTMENT_RE.search(line):
            enactment_idx = idx
            break

    if enactment_idx >= 0:
        return min(enactment_idx + 1, len(lines))

    for idx, line in enumerate(lines):
        if re.match(r"^\s*ACT NO\.", line, re.IGNORECASE):
            return idx

    for idx, line in enumerate(lines):
        if CHAPTER_LINE_RE.match(line) or SECTION_LINE_RE.match(line):
            return idx

    return 0


def split_section_heading(text: str) -> Tuple[str, str]:
    text = clean_inline(text)
    patterns = [
        r"^(?P<title>.+?\.)\s*-\s*(?P<body>.+)$",
        r"^(?P<title>.+?\.)\s*-\((?P<body>.+)$",
        r"^(?P<title>.+?)\.-\s*(?P<body>.+)$",
        r"^(?P<title>.+?)\.-(?P<body>.+)$",
        r"^(?P<title>.+?)\.-\((?P<body>.+)$",
        r"^(?P<title>.+?)\.\s*-\s*(?P<body>.+)$",
        r"^(?P<title>.+?)\.-(?P<body>.+)$",
        r"^(?P<title>.+?)\.\s*:\s*(?P<body>.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, text)
        if match:
            title = clean_inline(match.group("title")).rstrip(".:- ")
            body = clean_inline(match.group("body"))
            if body.startswith("(") and not body.endswith(")"):
                body = body
            return title, body
    return text.rstrip(".:- "), ""


def looks_like_chapter_title(line: str) -> bool:
    if not line or SECTION_LINE_RE.match(line) or CHAPTER_LINE_RE.match(line):
        return False
    if len(line.split()) > 18:
        return False
    return line == line.upper() or line == line.title()


def collect_sections(lines: List[str]) -> List[Dict[str, Any]]:
    body_start = find_body_start(lines)
    body_lines = lines[body_start:]

    sections: List[Dict[str, Any]] = []
    current_section: Optional[Dict[str, Any]] = None
    current_chapter_number: Optional[str] = None
    current_chapter_title: Optional[str] = None

    idx = 0
    while idx < len(body_lines):
        line = body_lines[idx]
        if not line:
            idx += 1
            continue

        chapter_match = CHAPTER_LINE_RE.match(line)
        if chapter_match:
            current_chapter_number = clean_inline(chapter_match.group(1)).upper()
            inline_title = clean_inline(chapter_match.group(2))
            if not inline_title and idx + 1 < len(body_lines) and looks_like_chapter_title(body_lines[idx + 1]):
                inline_title = clean_inline(body_lines[idx + 1])
                idx += 1
            current_chapter_title = inline_title or None
            idx += 1
            continue

        section_match = SECTION_LINE_RE.match(line)
        if section_match and not AMENDMENT_NOTE_RE.match(line):
            if current_section:
                sections.append(current_section)
            section_number = clean_inline(section_match.group(1))
            heading_rest = section_match.group(2)
            section_title, first_body = split_section_heading(heading_rest)
            current_section = {
                "section_number": section_number,
                "section_title": section_title,
                "chapter_number": current_chapter_number,
                "chapter_title": current_chapter_title,
                "body_lines": [first_body] if first_body else [],
            }
            idx += 1
            continue

        if current_section and not AMENDMENT_NOTE_RE.match(line):
            current_section["body_lines"].append(line)
        idx += 1

    if current_section:
        sections.append(current_section)

    return sections


def is_roman(label: str) -> bool:
    raw = label.strip("()").lower()
    return bool(raw) and len(raw) <= 8 and re.fullmatch(r"[ivxlcdm]+", raw) is not None


def extract_amendments(text: str) -> List[str]:
    candidates: List[str] = []
    bracketed = re.findall(r"\[(.*?)\]", text)
    for item in bracketed:
        item_clean = clean_inline(item)
        if re.search(
            r"\b(act|w\.e\.f\.|inserted|substituted|omitted|amended|ins\.|subs\.)\b",
            item_clean,
            re.IGNORECASE,
        ):
            candidates.append(item_clean)

    inline = re.findall(
        r"\b(?:Ins\.|Subs\.|Inserted|Substituted|Omitted|Amended)\s+by\s+Act[^.;\n]*",
        text,
        flags=re.IGNORECASE,
    )
    candidates.extend(clean_inline(item) for item in inline)

    unique: List[str] = []
    seen = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def make_context_path(
    section_number: str,
    subsection: Optional[str],
    clause: Optional[str],
    subclause: Optional[str],
) -> str:
    parts = [f"Section {section_number}"]
    if subsection:
        parts.append(subsection)
    if clause:
        parts.append(clause)
    if subclause:
        parts.append(subclause)
    return " > ".join(parts)


def parent_from_context(
    section_number: str,
    subsection: Optional[str],
    clause: Optional[str],
    subclause: Optional[str],
    unit_type: str,
) -> Optional[str]:
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
    if subclause:
        return make_context_path(section_number, subsection, clause, subclause)
    if clause:
        return make_context_path(section_number, subsection, clause, None)
    if subsection:
        return make_context_path(section_number, subsection, None, None)
    return make_context_path(section_number, None, None, None)


def build_unit_identifier(document_id: str, section_number: str, unit_type: str, label: str) -> str:
    label_slug = slugify(label)
    doc_slug = slugify(document_id)
    return f"{doc_slug}_S{section_number}_{slugify(unit_type)}_{label_slug}_{stable_id(document_id, section_number, unit_type, label)}"


def parse_section_units(document_id: str, section: Dict[str, Any]) -> List[Dict[str, Any]]:
    section_number = section["section_number"]
    section_title = section["section_title"]
    lines = [normalize_line(line) for line in section["body_lines"]]

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
        text = clean_inline(" ".join(part for part in current["text_parts"] if part))
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
        label = current["label"]

        units.append(
            {
                "unit_id": build_unit_identifier(document_id, section_number, unit_type, label),
                "unit_type": unit_type,
                "label": label,
                "section_number": section_number,
                "section_title": section_title,
                "chapter_number": section.get("chapter_number"),
                "chapter_title": section.get("chapter_title"),
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
        if not line or AMENDMENT_NOTE_RE.match(line):
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

        m_alpha = re.match(r"^\(([A-Za-z]{1,4})\)\s*(.*)$", line)
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
    lines = preprocess_lines(raw_text)
    title = infer_title(lines, filename)
    document_id = filename.replace(".txt", "")
    year = infer_year(title, filename)
    aliases = build_aliases(title, filename)

    section_blocks = collect_sections(lines)
    sections: List[Dict[str, Any]] = []

    for block in section_blocks:
        units = parse_section_units(document_id, block)
        full_lines = [f"{block['section_number']}. {block['section_title']}"] + block["body_lines"]
        sections.append(
            {
                "section_number": block["section_number"],
                "section_title": block["section_title"],
                "chapter_number": block.get("chapter_number"),
                "chapter_title": block.get("chapter_title"),
                "full_section_text": normalize_block(full_lines),
                "units": units,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "document_id": document_id,
        "document_type": "act",
        "title": title,
        "aliases": aliases,
        "year": year,
        "jurisdiction": JURISDICTION,
        "source_file": filename,
        "sections": sections,
    }


def sentence_split(text: str) -> List[str]:
    pieces = re.split(r"(?<=[.!?;:])\s+", text)
    return [clean_inline(piece) for piece in pieces if clean_inline(piece)]


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

    for sentence in sentences:
        sentence_words = len(sentence.split())
        if sentence_words > max_words:
            tokens = sentence.split()
            for idx in range(0, len(tokens), max_words):
                part = " ".join(tokens[idx : idx + max_words]).strip()
                if part:
                    if current:
                        chunks.append(clean_inline(" ".join(current)))
                        current = []
                        current_words = 0
                    chunks.append(part)
            continue

        if current_words + sentence_words > max_words and current:
            chunks.append(clean_inline(" ".join(current)))
            current = [sentence]
            current_words = sentence_words
        else:
            current.append(sentence)
            current_words += sentence_words

    if current:
        chunks.append(clean_inline(" ".join(current)))

    return [chunk for chunk in chunks if chunk]


def context_text_lookup(sections: List[Dict[str, Any]]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for section in sections:
        section_context = f"Section {section['section_number']}"
        lookup[section_context] = section["full_section_text"]
        for unit in section["units"]:
            key = unit["context_path"]
            if key not in lookup and unit["unit_type"] in {"section", "subsection", "clause", "subclause"}:
                lookup[key] = unit["text"]
    return lookup


def build_retrieval_chunks(structure: Dict[str, Any]) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    section_lookup = {section["section_number"]: section for section in structure["sections"]}
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
                chunk_id = (
                    f"{slugify(structure['document_id'])}_S{section_number}_"
                    f"{slugify(unit['unit_type'])}_{slugify(unit['label'])}_P{part_idx}"
                )

                chunks.append(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "chunk_id": chunk_id,
                        "document_id": structure["document_id"],
                        "document_type": structure["document_type"],
                        "title": structure["title"],
                        "aliases": structure.get("aliases", []),
                        "year": structure.get("year"),
                        "jurisdiction": structure["jurisdiction"],
                        "source_file": structure["source_file"],
                        "chapter_number": section_lookup[section_number].get("chapter_number"),
                        "chapter_title": section_lookup[section_number].get("chapter_title"),
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


def process_file(input_dir: str, filename: str) -> Dict[str, Any]:
    raw_text = read_file(os.path.join(input_dir, filename))
    structure = build_structure(raw_text, filename)
    chunks = build_retrieval_chunks(structure)

    return {
        "schema_version": SCHEMA_VERSION,
        "document": {
            "document_id": structure["document_id"],
            "document_type": structure["document_type"],
            "title": structure["title"],
            "aliases": structure.get("aliases", []),
            "year": structure.get("year"),
            "jurisdiction": structure["jurisdiction"],
            "source_file": structure["source_file"],
            "sections_count": len(structure["sections"]),
            "chunks_count": len(chunks),
        },
        "sections": structure["sections"],
        "chunks": chunks,
    }


def process_all(input_dir: str, output_dir: str, limit: Optional[int] = None) -> None:
    os.makedirs(output_dir, exist_ok=True)
    files = sorted(
        filename
        for filename in os.listdir(input_dir)
        if filename.endswith(".txt") and not filename.startswith(".")
    )
    if limit is not None:
        files = files[:limit]

    print(f"Found {len(files)} acts in {input_dir}")
    for filename in files:
        print(f"\nProcessing: {filename}")
        output = process_file(input_dir, filename)
        out_path = os.path.join(output_dir, filename.replace(".txt", ".json"))
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(
            f"Saved: {out_path} | sections={output['document']['sections_count']} | chunks={output['document']['chunks_count']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert raw act TXT files into structured JSON chunks.")
    parser.add_argument("--input-dir", default=INPUT_FOLDER, help=f"Source TXT directory (default: {INPUT_FOLDER})")
    parser.add_argument("--output-dir", default=OUTPUT_FOLDER, help=f"Destination JSON directory (default: {OUTPUT_FOLDER})")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N files")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    process_all(args.input_dir, args.output_dir, args.limit)
