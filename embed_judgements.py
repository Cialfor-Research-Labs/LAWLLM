#!/usr/bin/env python3
"""
embed_judgements.py — Production-grade embedding, indexing & retrieval pipeline for Indian Legal Judgements.

Pipeline:
  1. Reads JSON judgements from a directory.
  2. Maps fields to the user-requested schema.
  3. Generates embeddings using BAAI/bge-base-en-v1.5 with metadata enrichment.
  4. Stores vectors in FAISS and metadata in SQLite (aligned by ID).

Usage:
  python3 embed_judgements.py --json_dir json_judgements --out_dir embedding_judgements
"""

import argparse
import json
import logging
import math
import os
import sqlite3
import torch
import numpy as np
from sentence_transformers import SentenceTransformer
import sys
import time
import faiss
from pathlib import Path
from typing import Dict, List, Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MODEL_NAME = "BAAI/bge-large-en-v1.5"
EMBEDDING_DIM = 1024
BATCH_SIZE = 16
DOC_PREFIX = "Represent this legal judgement for retrieval: "
QUERY_PREFIX = "Represent this legal query for retrieving relevant passages: "

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ===================================================================
# 1. load_data — Read and Map to Schema
# ===================================================================
def load_and_map_data(json_dir: str) -> List[Dict]:
    """
    Read JSON files and map them to the following schema:
    {
      "document_id": "string",
      "document_type": "judgement",
      "case_metadata": { ... },
      "legal_structure": { ... },
      "statutes_referred": [ ... ],
      "precedents_cited": [ ... ],
      "chunking": { ... },
      "embedding_metadata": { ... }
    }
    """
    json_path = Path(json_dir)
    if not json_path.is_dir():
        raise FileNotFoundError(f"JSON directory not found: {json_dir}")

    json_files = sorted(json_path.glob("*.json"))
    log.info("Found %d JSON files in %s", len(json_files), json_dir)

    all_schema_chunks: List[Dict] = []
    chunk_global_index = 0

    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                raw_chunks = json.load(f)
        except Exception as exc:
            log.warning("Skipping %s: %s", jf.name, exc)
            continue

        if not isinstance(raw_chunks, list):
            log.warning("Skipping %s: expected list of chunks", jf.name)
            continue

        for i, rc in enumerate(raw_chunks):
            # Extract Bench from entities.judges
            bench = rc.get("entities", {}).get("judges", [])
            if not isinstance(bench, list):
                bench = [bench] if bench else []

            # Extract Issues from legal_issues
            issues = rc.get("legal_issues", [])
            if not isinstance(issues, list):
                issues = [issues] if issues else []

            # Map to Schema
            schema_obj = {
                "document_id": rc.get("document_id", jf.stem),
                "document_type": "judgement",
                "case_metadata": {
                    "case_name": rc.get("title", "Unknown Case"),
                    "court": rc.get("court", "Unknown Court"),
                    "bench": bench,
                    "date_of_judgement": str(rc.get("year", "0000")) + "-01-01",
                    "citation": rc.get("citation", ""),
                    "jurisdiction": rc.get("jurisdiction", "India")
                },
                "legal_structure": {
                    "facts": "", # Placeholder or extract if possible
                    "issues": issues,
                    "arguments": {
                        "petitioner": "",
                        "respondent": ""
                    },
                    "analysis": "",
                    "ratio_decidendi": "",
                    "obiter_dicta": "",
                    "final_judgement": rc.get("holding", "") or ""
                },
                "statutes_referred": [
                    {"act_name": s, "section": ""} for s in rc.get("statutes", [])
                ],
                "precedents_cited": [
                    {"case_name": p, "citation": ""} for p in rc.get("precedents", [])
                ],
                "chunking": {
                    "chunk_id": rc.get("chunk_id", f"{jf.stem}_c{i}"),
                    "chunk_index": chunk_global_index,
                    "chunk_text": rc.get("chunk_text", ""),
                    "chunk_type": rc.get("section", "general")
                },
                "embedding_metadata": {
                    "domain": rc.get("domain", "Legal"),
                    "legal_topics": [],
                    "keywords": rc.get("entities", {}).get("acts", []) # Using acts as initial keywords
                }
            }

            if schema_obj["chunking"]["chunk_text"].strip():
                all_schema_chunks.append(schema_obj)
                chunk_global_index += 1

    log.info("Loaded and mapped %d chunks from %d files", len(all_schema_chunks), len(json_files))
    return all_schema_chunks

# ===================================================================
# 2. build_embeddings
# ===================================================================
def build_embeddings(chunks: List[Dict], model: SentenceTransformer) -> np.ndarray:
    log.info("Constructing enriched texts for %d chunks...", len(chunks))

    texts: List[str] = []
    for ch in chunks:
        meta = ch["case_metadata"]
        chunk = ch["chunking"]
        
        # Enrichment: Case Name + Court + Bench + Type + Text
        enriched = (
            f"Case: {meta['case_name']}\n"
            f"Court: {meta['court']} | Bench: {', '.join(meta['bench'][:3])}\n"
            f"Type: {chunk['chunk_type']}\n"
            f"{chunk['chunk_text']}"
        )
        texts.append(DOC_PREFIX + enriched)

    log.info("Encoding %d texts with BGE (batch_size=%d)...", len(texts), BATCH_SIZE)
    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        normalize_embeddings=True, # L2 Normalization
        convert_to_numpy=True,
    )
    return embeddings.astype(np.float32)

# ===================================================================
# 3. build_faiss
# ===================================================================
def build_faiss(embeddings: np.ndarray, output_path: str):
    n, d = embeddings.shape
    log.info("Building FAISS index with %d vectors...", n)
    
    # Use IVF for scalability if enough data
    if n >= 1000:
        nlist = int(math.sqrt(n))
        quantizer = faiss.IndexFlatIP(d)
        index = faiss.IndexIVFFlat(quantizer, d, nlist, faiss.METRIC_INNER_PRODUCT)
        index.train(embeddings)
        index.add(embeddings)
    else:
        index = faiss.IndexFlatIP(d)
        index.add(embeddings)

    faiss.write_index(index, output_path)
    log.info("FAISS index saved to %s", output_path)

# ===================================================================
# 4. build_sqlite
# ===================================================================
def build_sqlite(chunks: List[Dict], output_path: str):
    if os.path.exists(output_path):
        os.remove(output_path)

    conn = sqlite3.connect(output_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE judgements (
            id            INTEGER PRIMARY KEY,
            document_id   TEXT,
            case_name     TEXT,
            court         TEXT,
            bench         TEXT,
            date          TEXT,
            chunk_type    TEXT,
            chunk_text    TEXT,
            full_json     TEXT
        )
    """)

    # FTS5 for BM25 search
    cur.execute("""
        CREATE VIRTUAL TABLE judgements_fts USING fts5(
            case_name, court, chunk_text, chunk_type,
            content='judgements', content_rowid='id'
        )
    """)

    log.info("Inserting metadata into SQLite...")
    rows = []
    for idx, ch in enumerate(chunks):
        rows.append((
            idx,
            ch["document_id"],
            ch["case_metadata"]["case_name"],
            ch["case_metadata"]["court"],
            ", ".join(ch["case_metadata"]["bench"]),
            ch["case_metadata"]["date_of_judgement"],
            ch["chunking"]["chunk_type"],
            ch["chunking"]["chunk_text"],
            json.dumps(ch)
        ))

    cur.executemany("INSERT INTO judgements VALUES (?,?,?,?,?,?,?,?,?)", rows)
    cur.execute("INSERT INTO judgements_fts(rowid, case_name, court, chunk_text, chunk_type) SELECT id, case_name, court, chunk_text, chunk_type FROM judgements")
    
    conn.commit()
    conn.close()
    log.info("SQLite metadata saved to %s", output_path)

# ===================================================================
# Main
# ===================================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-dir", default="json_judgements", help="Source JSON directory")
    parser.add_argument("--output-dir", default="embedding_judgements", help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    log.info("Starting Judgement Embedding Pipeline...")
    chunks = load_and_map_data(args.json_dir)
    
    if not chunks:
        log.error("No chunks found. Exiting.")
        return

    log.info("Loading model %s...", MODEL_NAME)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(MODEL_NAME, device=device)

    embeddings = build_embeddings(chunks, model)
    
    faiss_path = os.path.join(args.output_dir, "index.faiss")
    build_faiss(embeddings, faiss_path)

    sqlite_path = os.path.join(args.output_dir, "metadata.db")
    build_sqlite(chunks, sqlite_path)

    log.info("Success! Judgements embedded and indexed.")

if __name__ == "__main__":
    main()
