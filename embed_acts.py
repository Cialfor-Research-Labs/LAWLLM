#!/usr/bin/env python3
"""
embed_acts.py — Production-grade embedding, indexing & retrieval pipeline for Indian Legal Acts.

Pipeline (build mode):
  1. Reads structured JSON acts from a directory
  2. Generates embeddings using BAAI/bge-base-en-v1.5
  3. Stores vectors in FAISS (IndexIVFFlat for scalability)
  4. Stores metadata in SQLite with multi-field FTS5 for BM25 retrieval
  5. Maintains PERFECT alignment: FAISS vector position == SQLite row id

Retrieval (search mode):
  6. Hybrid search (FAISS + BM25) with score fusion
  7. Cross-encoder reranking (BAAI/bge-reranker-base)
  8. Section-level context reconstruction
  9. Hard validation with accuracy metrics
"""

import argparse
import json
import logging
import math
import os
import re
import sqlite3
import sys
import time
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import faiss
import numpy as np
from sentence_transformers import CrossEncoder, SentenceTransformer

from query_expansion import build_query as expand_query_full

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MODEL_NAME = "BAAI/bge-large-en-v1.5"
RERANKER_MODEL = "BAAI/bge-reranker-large"
EMBEDDING_DIM = 1024
BATCH_SIZE = 16
DOC_PREFIX = "Represent this legal passage for retrieval: "
QUERY_PREFIX = "Represent this legal query for retrieving relevant passages: "

# RRF constant (higher k = smoother blending)
RRF_K = 60

# Rerank candidate pool size
RERANK_CANDIDATE_K = 50

# Section reconstruction: max chars before switching to window mode
SECTION_MERGE_THRESHOLD = 3000
ADJACENT_CHUNK_WINDOW = 1  # +/- N chunks around each matched chunk


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

if sys.version_info < (3, 8):
    raise RuntimeError(
        "embed_acts.py requires Python 3.8+. "
        "Use your venv/python3 interpreter."
    )


# ===================================================================
# Model loading (cached)
# ===================================================================
@lru_cache(maxsize=2)
def load_embedding_model(model_name: str = MODEL_NAME, device: str = "cpu") -> SentenceTransformer:
    """Load and cache the embedding model."""
    try:
        return SentenceTransformer(model_name, device=device, local_files_only=True)
    except Exception:
        return SentenceTransformer(model_name, device=device)


@lru_cache(maxsize=2)
def load_reranker(model_name: str = RERANKER_MODEL, device: str = "cpu") -> CrossEncoder:
    """Load and cache the cross-encoder reranker."""
    try:
        return CrossEncoder(model_name, device=device, max_length=512, local_files_only=True)
    except Exception:
        return CrossEncoder(model_name, device=device, max_length=512)


# ===================================================================
# 1. load_data — Read JSON acts, flatten into chunks
# ===================================================================
def load_data(json_dir: str) -> List[Dict]:
    """
    Read all .json files from *json_dir*, iterate through
    document → sections → units, and return a flat list of chunk dicts.

    Each chunk dict contains:
        document_id, title, section_number, section_title,
        context_path, chunk_id, chunk_index, chunk_text
    """
    json_path = Path(json_dir)
    if not json_path.is_dir():
        raise FileNotFoundError(f"JSON directory not found: {json_dir}")

    json_files = sorted(json_path.glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"No .json files found in: {json_dir}")

    log.info("Found %d JSON files in %s", len(json_files), json_dir)

    chunks: List[Dict] = []
    skipped = 0
    source_stats: Dict[str, int] = defaultdict(int)
    no_units_sections = 0
    chunk_index = 0

    def _extract_text(unit: Dict) -> Tuple[str, str]:
        """Extract text across schema variants, returning (text, source_field)."""
        candidates = [
            ("text", unit.get("text")),
            ("text_cleaned", unit.get("text_cleaned")),
            ("text_original", unit.get("text_original")),
            ("content", unit.get("content")),
            ("body", unit.get("body")),
            ("paragraph_text", unit.get("paragraph_text")),
        ]
        for source, raw in candidates:
            if isinstance(raw, str):
                value = raw.strip()
                if value:
                    return value, source
        return "", ""

    for jf in json_files:
        data = None
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                with open(jf, "r", encoding=enc) as f:
                    data = json.load(f)
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Skipping %s: %s", jf.name, exc)
                break
        if data is None:
            log.warning("Skipping %s: could not decode with any encoding", jf.name)
            continue

        doc = data.get("document", {})
        document_id = doc.get("document_id", jf.stem)
        title = doc.get("title", document_id)

        sections = data.get("sections", [])
        for section in sections:
            sec_number = str(section.get("section_number", ""))
            sec_title = section.get("section_title", "")
            units = section.get("units", [])

            if not units:
                no_units_sections += 1
                section_text = (
                    (section.get("full_section_text") or "").strip()
                    or (section.get("section_text") or "").strip()
                    or (section.get("text") or "").strip()
                )
                if section_text:
                    chunks.append(
                        {
                            "document_id": document_id,
                            "title": title,
                            "section_number": sec_number,
                            "section_title": sec_title,
                            "context_path": f"Section {sec_number}" if sec_number else "",
                            "chunk_id": f"{document_id}_S{sec_number}_FULL",
                            "chunk_index": chunk_index,
                            "chunk_text": " ".join(section_text.split()),
                        }
                    )
                    source_stats["section_fallback"] += 1
                    chunk_index += 1
                else:
                    skipped += 1
                continue

            for unit in units:
                text, source = _extract_text(unit)

                # --- Edge case: skip empty / whitespace-only chunks ---
                if not text:
                    skipped += 1
                    continue

                # Trim excessive internal whitespace
                text = " ".join(text.split())

                chunks.append(
                    {
                        "document_id": document_id,
                        "title": title,
                        "section_number": sec_number,
                        "section_title": sec_title,
                        "context_path": unit.get("context_path", ""),
                        "chunk_id": unit.get("unit_id", ""),
                        "chunk_index": chunk_index,
                        "chunk_text": text,
                    }
                )
                source_stats[source] += 1
                chunk_index += 1

    log.info(
        "Loaded %d chunks from %d files (%d empty units skipped; %d sections had no units)",
        len(chunks),
        len(json_files),
        skipped,
        no_units_sections,
    )
    if source_stats:
        breakdown = ", ".join(
            f"{k}={v}" for k, v in sorted(source_stats.items(), key=lambda kv: kv[1], reverse=True)
        )
        log.info("Text source breakdown: %s", breakdown)
    return chunks


# ===================================================================
# 2. build_embeddings — Generate BGE embeddings with enriched text
# ===================================================================
def build_embeddings(
    chunks: List[Dict],
    model: SentenceTransformer,
    batch_size: int = BATCH_SIZE,
) -> np.ndarray:
    """
    For each chunk, construct enriched embedding input (P5):
        {title}
        {context_path}
        Section {section_number}: {section_title}
        {chunk_text}

    Prepend instruction prefix, batch-encode, then L2-normalise.
    Returns an (N, 768) float32 numpy array of normalised embeddings.
    """
    log.info("Constructing enriched texts for %d chunks...", len(chunks))

    texts: List[str] = []
    for ch in chunks:
        # PRIORITY 5: Include context_path for richer embeddings
        enriched = (
            f"{ch['title']}\n"
            f"{ch['context_path']}\n"
            f"Section {ch['section_number']}: {ch['section_title']}\n"
            f"{ch['chunk_text']}"
        )
        doc_text = DOC_PREFIX + enriched
        texts.append(doc_text)

    log.info("Encoding %d texts (batch_size=%d)...", len(texts), batch_size)
    t0 = time.time()

    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=False,  # We normalise manually below
        convert_to_numpy=True,
    )

    elapsed = time.time() - t0
    log.info(
        "Encoding complete in %.1fs (%.1f chunks/s)",
        elapsed,
        len(texts) / max(elapsed, 0.001),
    )

    # --- Mandatory: L2 normalisation ---
    embeddings = embeddings.astype(np.float32)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)

    # Guard against zero-norm (NaN) vectors
    zero_mask = norms.flatten() < 1e-10
    if zero_mask.any():
        bad_count = int(zero_mask.sum())
        log.warning(
            "%d vectors have near-zero norm — replacing with unit random", bad_count
        )
        for idx in np.where(zero_mask)[0]:
            rng = np.random.default_rng(seed=int(idx))
            rand_vec = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
            embeddings[idx] = rand_vec / np.linalg.norm(rand_vec)
        # Recompute norms after fixup
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)

    embeddings = embeddings / norms

    # Sanity: check for NaN
    if np.isnan(embeddings).any():
        raise RuntimeError("NaN detected in embeddings after normalisation!")

    log.info("Embeddings shape: %s, dtype: %s", embeddings.shape, embeddings.dtype)
    return embeddings


# ===================================================================
# 3. build_faiss — Create and save FAISS IndexIVFFlat (P7: scalable)
# ===================================================================
def build_faiss(embeddings: np.ndarray, output_path: str) -> faiss.Index:
    """
    Build a FAISS index for inner product search (cosine for unit vectors).
    FAISS vector position i  ↔  SQLite row id = i.

    Uses IndexIVFFlat for scalability (100k+ chunks).
    Falls back to IndexFlatIP if N < 1000 (not enough to train IVF).
    """
    n, d = embeddings.shape
    if d != EMBEDDING_DIM:
        raise ValueError(f"Expected dim={EMBEDDING_DIM}, got {d}")

    # PRIORITY 7: Use IndexIVFFlat for scalability
    MIN_IVF_SIZE = 1000  # Need enough data to train clusters

    if n >= MIN_IVF_SIZE:
        nlist = max(4, int(math.sqrt(n)))
        log.info(
            "Building FAISS IndexIVFFlat(%d) with %d vectors, nlist=%d...",
            d, n, nlist,
        )
        quantizer = faiss.IndexFlatIP(d)
        index = faiss.IndexIVFFlat(quantizer, d, nlist, faiss.METRIC_INNER_PRODUCT)

        log.info("Training IVF index on %d vectors...", n)
        t0 = time.time()
        index.train(embeddings)
        log.info("Training complete in %.1fs", time.time() - t0)

        index.add(embeddings)

        # FIX 5: Dynamic nprobe — better recall than static 10
        nprobe = min(nlist, max(10, nlist // 10))
        index.nprobe = nprobe
        log.info("IVF nprobe set to %d (dynamic: min(%d, max(10, %d//10)))", nprobe, nlist, nlist)
    else:
        log.info(
            "N=%d < %d, using IndexFlatIP(%d) (brute-force)...", n, MIN_IVF_SIZE, d
        )
        index = faiss.IndexFlatIP(d)
        index.add(embeddings)

    faiss.write_index(index, output_path)
    log.info("FAISS index saved → %s  (ntotal=%d)", output_path, index.ntotal)
    return index


# ===================================================================
# 4. build_sqlite — Create SQLite DB with docs + multi-field FTS5 (P1)
# ===================================================================
def build_sqlite(chunks: List[Dict], output_path: str) -> None:
    """
    Create SQLite database with:
      - docs table     (metadata per chunk, id aligned with FAISS position)
      - docs_fts table (multi-field FTS5 for rich BM25 full-text search)

    id values start at 0 and match FAISS vector positions exactly.
    """
    # Remove existing DB to rebuild cleanly
    if os.path.exists(output_path):
        os.remove(output_path)

    conn = sqlite3.connect(output_path)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    cur = conn.cursor()

    # --- Create docs table ---
    cur.execute(
        """
        CREATE TABLE docs (
            id            INTEGER PRIMARY KEY,
            document_id   TEXT,
            title         TEXT,
            section_number TEXT,
            section_title TEXT,
            context_path  TEXT,
            chunk_id      TEXT,
            chunk_index   INTEGER,
            chunk_text    TEXT
        )
        """
    )

    # --- PRIORITY 1: Multi-field FTS5 for richer keyword matching ---
    cur.execute(
        """
        CREATE VIRTUAL TABLE docs_fts USING fts5(
            chunk_text,
            section_title,
            section_number,
            title,
            context_path,
            content='docs',
            content_rowid='id',
            tokenize='unicode61'
        )
        """
    )
    conn.commit()

    # --- Batch insert into docs ---
    log.info("Inserting %d chunks into SQLite...", len(chunks))
    batch_size = 5000
    rows = []

    for idx, ch in enumerate(chunks):
        rows.append(
            (
                idx,  # id == FAISS vector position
                ch["document_id"],
                ch["title"],
                ch["section_number"],
                ch["section_title"],
                ch["context_path"],
                ch["chunk_id"],
                ch["chunk_index"],
                ch["chunk_text"],
            )
        )
        if len(rows) >= batch_size:
            cur.executemany(
                """
                INSERT INTO docs(id, document_id, title, section_number,
                                 section_title, context_path, chunk_id,
                                 chunk_index, chunk_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            rows.clear()
            conn.commit()

    if rows:
        cur.executemany(
            """
            INSERT INTO docs(id, document_id, title, section_number,
                             section_title, context_path, chunk_id,
                             chunk_index, chunk_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()

    # --- PRIORITY 1: Populate multi-field FTS5 index ---
    cur.execute(
        """
        INSERT INTO docs_fts(rowid, chunk_text, section_title, section_number, title, context_path)
        SELECT id, chunk_text, section_title, section_number, title, context_path FROM docs
        """
    )

    # --- Indexes for fast lookups ---
    cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_chunk_id ON docs(chunk_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_doc_id ON docs(document_id)")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_docs_section ON docs(document_id, section_number)"
    )
    conn.commit()

    # --- Verify counts ---
    cur.execute("SELECT COUNT(1) FROM docs")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(1) FROM docs_fts")
    fts_total = cur.fetchone()[0]
    conn.close()

    log.info(
        "SQLite saved → %s  (docs=%d, fts=%d)", output_path, total, fts_total
    )
    if total != fts_total:
        log.error("ALIGNMENT ERROR: docs count (%d) != fts count (%d)", total, fts_total)


# ===================================================================
# Helper: encode query with BGE prefix + normalise (FIX 6: cached)
# ===================================================================
_query_embedding_cache: Dict[str, np.ndarray] = {}


def encode_query(query: str, model: SentenceTransformer) -> np.ndarray:
    """Encode and normalise a single query using BGE query prefix. Cached by normalised query text."""
    # FIX: deterministic cache key (hash() is not stable across runs and can collide)
    cache_key = query.strip().lower()
    if cache_key in _query_embedding_cache:
        log.debug("Query embedding cache HIT")
        return _query_embedding_cache[cache_key]

    query_text = QUERY_PREFIX + query
    t0 = time.time()
    q_emb = model.encode(
        [query_text], normalize_embeddings=False, convert_to_numpy=True
    )
    q_emb = q_emb.astype(np.float32)
    q_emb = q_emb / np.linalg.norm(q_emb, axis=1, keepdims=True)
    elapsed_ms = (time.time() - t0) * 1000
    log.debug("Query embedding: %.1fms", elapsed_ms)

    # Cache (bounded: evict oldest if > 1000)
    if len(_query_embedding_cache) >= 1000:
        oldest_key = next(iter(_query_embedding_cache))
        del _query_embedding_cache[oldest_key]
    _query_embedding_cache[cache_key] = q_emb
    return q_emb


# ===================================================================
# Helper: Reciprocal Rank Fusion (FIX 2: replaces min-max)
# ===================================================================
def rrf_scores(ranked_ids: List[int], k: int = RRF_K) -> Dict[int, float]:
    """
    Reciprocal Rank Fusion: score = 1 / (k + rank).

    FIX 2: Replaces min-max normalisation which is mathematically
    unstable when scores are clustered (everything → ~1.0).
    RRF is rank-based, so it's stable regardless of score distribution.
    """
    return {doc_id: 1.0 / (k + rank) for rank, doc_id in enumerate(ranked_ids, start=1)}


# ===================================================================
# Helper: fetch doc rows from SQLite by ids
# ===================================================================
def fetch_docs(conn: sqlite3.Connection, ids: List[int]) -> Dict[int, Dict]:
    """Fetch full doc rows for a set of ids."""
    if not ids:
        return {}
    placeholders = ",".join(["?"] * len(ids))
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT id, document_id, title, section_number, section_title,
               context_path, chunk_id, chunk_index, chunk_text
        FROM docs
        WHERE id IN ({placeholders})
        """,
        ids,
    )
    results = {}
    for row in cur.fetchall():
        results[int(row[0])] = {
            "id": int(row[0]),
            "document_id": row[1],
            "title": row[2],
            "section_number": row[3],
            "section_title": row[4],
            "context_path": row[5],
            "chunk_id": row[6],
            "chunk_index": row[7],
            "chunk_text": row[8],
        }
    return results


# ===================================================================
# PRIORITY 2: hybrid_search — FAISS + BM25 with RRF fusion
# ===================================================================
def hybrid_search(
    query: str,
    faiss_index: faiss.Index,
    sqlite_conn: sqlite3.Connection,
    model: SentenceTransformer,
    top_k: int = 10,
    dense_k: int = 20,
    bm25_k: int = 20,
) -> List[Dict]:
    """
    Hybrid search combining FAISS dense retrieval and BM25 keyword search.

    Uses Reciprocal Rank Fusion (RRF) for stable score combination.
    Handles edge cases: empty query, no BM25 results, FAISS -1 ids.
    """
    # --- empty query guard ---
    if not query or not query.strip():
        log.warning("Empty query — returning empty results")
        return []

    # --- Query expansion via query_expansion module ---
    eq = expand_query_full(query)
    log.info("  📝 query expansion:")
    log.info("       type:     %s", eq.query_type)
    log.info("       expanded: %s", eq.expanded_query)
    log.info("       bm25:     %s", eq.bm25_query)
    if eq.filters.get("section_number") or eq.filters.get("act"):
        log.info("       filters:  %s", eq.filters)
    if eq.expansions_added:
        log.info("       added:    %s (level: %s)", eq.expansions_added, len(eq.expansions_added))
        log.info("       added:    %s", eq.expansions_added)

    # ---- FAISS dense search (uses expanded semantic query) ----
    t0 = time.time()
    q_emb = encode_query(eq.expanded_query, model)
    embed_ms = (time.time() - t0) * 1000

    t0 = time.time()
    distances, indices = faiss_index.search(q_emb, dense_k)
    faiss_ms = (time.time() - t0) * 1000

    # Collect FAISS results in rank order (already sorted by score)
    dense_ranked: List[int] = []
    for score, idx in zip(distances[0], indices[0]):
        if idx < 0:  # guard against -1 ids
            continue
        dense_ranked.append(int(idx))

    # ---- BM25 keyword search (uses structured BM25 query) ----
    t0 = time.time()
    bm25_ranked: List[int] = []
    try:
        match_expr = eq.bm25_query
        cur = sqlite_conn.cursor()
        cur.execute(
            """
            SELECT rowid, bm25(docs_fts) AS rank
            FROM docs_fts
            WHERE docs_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (match_expr, bm25_k),
        )
        rows = cur.fetchall()
        # FTS5 bm25(): lower = better, already sorted
        bm25_ranked = [int(r[0]) for r in rows]
    except Exception as exc:
        log.warning("BM25 search failed (%s) — using dense results only", exc)
    bm25_ms = (time.time() - t0) * 1000

    # PRIORITY 8: log latencies
    log.info(
        "  ⏱ embed=%.1fms | faiss=%.1fms (%d hits) | bm25=%.1fms (%d hits)",
        embed_ms, faiss_ms, len(dense_ranked), bm25_ms, len(bm25_ranked),
    )

    # ---- FIX 2: RRF score fusion (replaces unstable min-max) ----
    dense_rrf = rrf_scores(dense_ranked)
    bm25_rrf = rrf_scores(bm25_ranked)

    all_ids = sorted(set(dense_rrf.keys()) | set(bm25_rrf.keys()))

    if not all_ids:
        log.warning("No results from FAISS or BM25 — returning empty")
        return []

    docs = fetch_docs(sqlite_conn, all_ids)
    req_act = eq.filters.get("act")

    ranked: List[Dict] = []
    for doc_id in all_ids:
        item = docs.get(doc_id)
        if not item:
            continue
            
        # UPGRADE 6: Flexible Post-Search Act Filtering
        if req_act:
            item_act = (item.get("title") or "").lower()
            item_id = (item.get("document_id") or "").lower()
            target = req_act.lower()
            
            # Match if target is in title/id OR title/id is in target
            match = (target in item_act or item_act in target or 
                     target in item_id or item_id in target)
            
            if not match:
                continue

        d = dense_rrf.get(doc_id, 0.0)
        b = bm25_rrf.get(doc_id, 0.0)
        final_score = d + b  # equal weight — tune later if needed

        item["hybrid_score"] = final_score
        item["dense_score"] = d
        item["bm25_score"] = b
        
        # Attach query metadata for reranking and logging
        item["query_type"] = eq.query_type
        
        ranked.append(item)

    ranked.sort(key=lambda x: x["hybrid_score"], reverse=True)
    return ranked[:top_k]


# ===================================================================
# PRIORITY 3: rerank — Cross-encoder reranking
# ===================================================================
def rerank(
    query: str,
    candidate_chunks: List[Dict],
    top_k: int = 5,
    reranker_model: Optional[CrossEncoder] = None,
    device: str = "cpu",
) -> List[Dict]:
    """
    Rerank candidate chunks using a cross-encoder (BAAI/bge-reranker-base).

    Input:  top 20–30 candidates from hybrid_search
    Output: top_k ranked by cross-encoder relevance score
    """
    if not candidate_chunks:
        return []

    if reranker_model is None:
        try:
            reranker_model = load_reranker(RERANKER_MODEL, device)
        except Exception as exc:
            log.warning("Reranker load failed (%s) — returning hybrid-ranked results", exc)
            return candidate_chunks[:top_k]

    # FIX 3: Enriched reranker input — include structured fields, not just chunk_text
    t0 = time.time()
    pairs = []
    for ch in candidate_chunks:
        enriched = (
            f"{ch.get('title', '')}\n"
            f"Section {ch.get('section_number', '')}: {ch.get('section_title', '')}\n"
            f"{ch.get('chunk_text', '')}"
        )
        pairs.append([query, enriched])
    scores = reranker_model.predict(pairs, batch_size=16, show_progress_bar=False)
    rerank_ms = (time.time() - t0) * 1000

    log.info("  ⏱ rerank=%.1fms (%d candidates)", rerank_ms, len(candidate_chunks))

    for item, score in zip(candidate_chunks, scores):
        final_score = float(score)
        q_type = item.get("query_type", "legal")
        
        # UPGRADE 5: Use query_type in reranking
        if q_type == "precise":
            # prioritize exact text match
            if query.lower() in str(item.get("chunk_text", "")).lower() or query.lower() in str(item.get("section_title", "")).lower():
                final_score += 5.0
        elif q_type == "layman":
            # prioritize semantic similarity
            final_score += item.get("dense_score", 0.0) * 100.0
        elif q_type == "explanatory":
            # prioritize coverage (longer chunks)
            chunk_len = len(str(item.get("chunk_text", "")))
            final_score += min(3.0, chunk_len / 400.0)
            
        item["rerank_score"] = final_score

    candidate_chunks.sort(key=lambda x: x["rerank_score"], reverse=True)
    return candidate_chunks[:top_k]


# ===================================================================
# PRIORITY 4: reconstruct_section — Section-level context merging
# ===================================================================
def reconstruct_section(
    results: List[Dict],
    sqlite_conn: sqlite3.Connection,
    merge_threshold: int = SECTION_MERGE_THRESHOLD,
    adjacent_window: int = ADJACENT_CHUNK_WINDOW,
) -> List[Dict]:
    """
    Group retrieval results by (document_id, section_number).

    FIX 4: Smart reconstruction —
      - Small sections (< threshold chars): merge ALL chunks (full context)
      - Large sections: include only matched chunks + adjacent window
        to avoid sending irrelevant text to LLM

    Returns a list of section-level dicts with merged text.
    """
    if not results:
        return []

    # Group by (document_id, section_number)
    groups: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
    for r in results:
        key = (r["document_id"], r["section_number"])
        groups[key].append(r)

    cur = sqlite_conn.cursor()
    sections: List[Dict] = []

    for (doc_id, sec_num), group_items in groups.items():
        # Fetch ALL chunks for this section
        cur.execute(
            """
            SELECT id, chunk_text, chunk_index, section_title, title, context_path
            FROM docs
            WHERE document_id = ? AND section_number = ?
            ORDER BY chunk_index ASC
            """,
            (doc_id, sec_num),
        )
        rows = cur.fetchall()

        if not rows:
            continue

        # Estimate full section length
        full_text = "\n".join(row[1] for row in rows)

        if len(full_text) <= merge_threshold:
            # Small section → include everything
            merged_text = full_text
            used_count = len(rows)
            mode = "full"
        else:
            # FIX 4: Large section → window around matched chunks only
            matched_indices = {r.get("chunk_index") for r in group_items if r.get("chunk_index") is not None}
            # Build chunk_index → row mapping
            idx_to_row = {row[2]: row for row in rows}
            all_indices = sorted(idx_to_row.keys())

            # Expand window around matched chunks
            keep_indices = set()
            for mi in matched_indices:
                for offset in range(-adjacent_window, adjacent_window + 1):
                    target = mi + offset
                    if target in idx_to_row:
                        keep_indices.add(target)

            # Merge kept chunks in order
            kept_rows = [idx_to_row[i] for i in sorted(keep_indices)]
            merged_text = "\n".join(row[1] for row in kept_rows)
            used_count = len(kept_rows)
            mode = f"window(±{adjacent_window})"

        # FIX: Average score across all matching chunks (combined evidence)
        # instead of just max — multiple matching chunks = stronger signal
        chunk_scores = [
            x.get("rerank_score", x.get("hybrid_score", 0.0))
            for x in group_items
        ]
        avg_score = sum(chunk_scores) / len(chunk_scores) if chunk_scores else 0.0

        sections.append(
            {
                "document_id": doc_id,
                "title": rows[0][4],
                "section_number": sec_num,
                "section_title": rows[0][3],
                "context_path": rows[0][5],
                "merged_text": merged_text,
                "chunk_count": used_count,
                "total_chunks": len(rows),
                "merge_mode": mode,
                "best_score": avg_score,
                "retrieval_chunks": [r["id"] for r in group_items],
            }
        )

    sections.sort(key=lambda x: x["best_score"], reverse=True)
    return sections


# ===================================================================
# PRIORITY 6: evaluate — Hard validation with accuracy + relevance (FIX 7)
# ===================================================================
def _keyword_overlap_score(query: str, chunk_text: str) -> float:
    """
    Compute keyword overlap between query and retrieved text.
    Uses token-level intersection (not substring) for accuracy.
    Returns |query_terms ∩ text_terms| / |query_terms|.
    """
    stopwords = {"the", "of", "in", "a", "an", "is", "for", "and", "or", "to",
                 "under", "what", "how", "india", "indian", "law"}
    query_terms = set(re.findall(r"[a-z0-9]+", query.lower())) - stopwords
    if not query_terms:
        return 1.0
    # FIX: Token-level matching instead of substring (avoids false positives)
    text_terms = set(re.findall(r"[a-z0-9]+", chunk_text.lower()))
    overlap = query_terms & text_terms
    return len(overlap) / len(query_terms)


def evaluate(
    faiss_index: faiss.Index,
    sqlite_conn: sqlite3.Connection,
    model: SentenceTransformer,
    device: str = "cpu",
) -> None:
    """
    Run hard validation test cases and report:
      - top-1 / top-5 structural accuracy (doc + section match)
      - keyword overlap relevance score per result (FIX 7)
    """
    log.info("=" * 60)
    log.info("EVALUATION — Hard Validation")
    log.info("=" * 60)

    test_cases = [
        # Bhartiya Nyay Sanhita (BNS)
        ("murder punishment", "Bhartiya Nyay Sanhita", "101"),
        ("dishonest misappropriation", "Bhartiya Nyay Sanhita", "314"),
        ("cheating and dishonestly", "Bhartiya Nyay Sanhita", "318"),
        
        # Bhartiya Nagrik Suraksha Sanhita (BNSS)
        ("rights of arrested person", "Bhartiya Nagrik Suraksha Sanhita", None),
        
        # Other Acts
        ("consumer protection refund", "Consumer Protection Act", None),
        ("builder delay possession", "Real Estate (Regulation And Development) Act", None),
        ("breach of contract compensation", "The Code of Civil Procedure", None), 
    ]

    top1_hits = 0
    top5_hits = 0
    total = len(test_cases)
    total_overlap = 0.0

    for query, expected_doc_substr, expected_sec in test_cases:
        log.info("-" * 50)
        log.info("QUERY: %s", query)
        log.info("EXPECTED: doc contains '%s', section=%s", expected_doc_substr, expected_sec)

        results = hybrid_search(
            query, faiss_index, sqlite_conn, model,
            top_k=10, dense_k=20, bm25_k=20,
        )

        if not results:
            log.warning("  ❌ NO RESULTS")
            continue

        # FIX 7: Keyword overlap for top-1
        top1 = results[0]
        overlap = _keyword_overlap_score(query, top1.get("chunk_text", ""))
        total_overlap += overlap

        # Check top-1
        top1_match = _check_match(top1, expected_doc_substr, expected_sec)
        if top1_match:
            top1_hits += 1
            log.info(
                "  ✅ TOP-1 HIT: %s § %s (keyword overlap=%.0f%%)",
                top1["title"], top1["section_number"], overlap * 100,
            )
        else:
            log.info(
                "  ❌ TOP-1 MISS: got %s § %s (keyword overlap=%.0f%%)",
                top1["title"], top1["section_number"], overlap * 100,
            )

        # Check top-5
        top5_match = any(
            _check_match(r, expected_doc_substr, expected_sec)
            for r in results[:5]
        )
        if top5_match:
            top5_hits += 1
            log.info("  ✅ TOP-5 HIT")
        else:
            log.info("  ❌ TOP-5 MISS")
            log.info("  Top-5 returned:")
            for i, r in enumerate(results[:5], 1):
                ov = _keyword_overlap_score(query, r.get("chunk_text", ""))
                log.info(
                    "    [%d] %s § %s: %s (score=%.4f, overlap=%.0f%%)",
                    i, r["title"], r["section_number"], r["section_title"],
                    r["hybrid_score"], ov * 100,
                )

    avg_overlap = total_overlap / max(total, 1)
    log.info("=" * 60)
    log.info(
        "ACCURACY: top-1 = %d/%d (%.0f%%) | top-5 = %d/%d (%.0f%%)",
        top1_hits, total, 100 * top1_hits / max(total, 1),
        top5_hits, total, 100 * top5_hits / max(total, 1),
    )
    log.info("AVG KEYWORD OVERLAP (top-1): %.0f%%", avg_overlap * 100)
    log.info("=" * 60)


def _check_match(result: Dict, expected_doc_substr: str, expected_sec: Optional[str]) -> bool:
    """Check if a result matches expected document (title/doc_id) and section."""
    # Check both title and document_id for robustness
    title_match = expected_doc_substr.lower() in result.get("title", "").lower()
    id_match = expected_doc_substr.lower() in result.get("document_id", "").lower()
    
    doc_match = title_match or id_match
    
    if expected_sec is not None:
        return doc_match and str(result.get("section_number")) == str(expected_sec)
    return doc_match


# ===================================================================
# 5. validate — Legacy validation (kept for backward compat)
# ===================================================================
def validate(
    faiss_path: str,
    db_path: str,
    model: SentenceTransformer,
    top_k: int = 5,
) -> None:
    """
    End-to-end validation:
      1. Verify FAISS ↔ SQLite alignment
      2. Run hybrid search on test queries
      3. Run hard evaluation with accuracy metrics
    """
    log.info("=" * 60)
    log.info("VALIDATION")
    log.info("=" * 60)

    # Load FAISS index
    index = faiss.read_index(faiss_path)
    faiss_count = index.ntotal

    # Set nprobe if IVF
    if hasattr(index, 'nprobe'):
        index.nprobe = 10

    # Load SQLite
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(1) FROM docs")
    db_count = cur.fetchone()[0]

    log.info("FAISS vectors: %d | SQLite rows: %d", faiss_count, db_count)

    if faiss_count != db_count:
        log.error(
            "❌ ALIGNMENT FAILURE: FAISS has %d vectors but SQLite has %d rows!",
            faiss_count,
            db_count,
        )
    else:
        log.info("✅ ALIGNMENT OK: FAISS vectors == SQLite rows == %d", faiss_count)

    # --- Quick hybrid search test ---
    test_queries = [
        "What is the punishment for murder under Indian law?",
        "section 420 IPC",
        "breach of contract compensation",
    ]

    for query in test_queries:
        log.info("-" * 50)
        log.info("TEST QUERY: %s", query)
        results = hybrid_search(query, index, conn, model, top_k=top_k)
        for rank, r in enumerate(results, 1):
            snippet = r["chunk_text"][:180].replace("\n", " ")
            log.info(
                "  [%d] score=%.4f (d=%.3f b=%.3f) | %s § %s: %s",
                rank,
                r["hybrid_score"],
                r["dense_score"],
                r["bm25_score"],
                r["title"],
                r["section_number"],
                r["section_title"],
            )
            log.info("       %s...", snippet)

    # --- Run hard evaluation ---
    evaluate(index, conn, model)

    conn.close()
    log.info("=" * 60)
    log.info("VALIDATION COMPLETE")
    log.info("=" * 60)


# ===================================================================
# main — Orchestrate the full pipeline
# ===================================================================
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Embedding & indexing pipeline for Indian Legal Acts"
    )
    sub = parser.add_subparsers(dest="cmd", help="Sub-commands")

    # --- BUILD subcommand ---
    p_build = sub.add_parser("build", help="Build embeddings, FAISS index, and SQLite DB")
    p_build.add_argument(
        "--json-dir", type=str, default="JSON_acts",
        help="Directory containing JSON act files (default: JSON_acts)",
    )
    p_build.add_argument(
        "--output-dir", type=str, default="embedding_acts",
        help="Output directory (default: embedding_acts)",
    )
    p_build.add_argument(
        "--batch-size", type=int, default=BATCH_SIZE,
        help=f"Batch size for embedding (default: {BATCH_SIZE})",
    )
    p_build.add_argument(
        "--device", type=str, default=None,
        help="Device for model (cpu/cuda/mps). Auto-detected if omitted.",
    )
    p_build.add_argument(
        "--skip-validate", action="store_true",
        help="Skip the validation step",
    )

    # --- SEARCH subcommand ---
    p_search = sub.add_parser("search", help="Run hybrid search with reranking")
    p_search.add_argument("--q", required=True, help="Query text")
    p_search.add_argument(
        "--index-dir", type=str, default="embedding_acts",
        help="Directory with index.faiss and bm25.db",
    )
    p_search.add_argument("--top-k", type=int, default=5)
    p_search.add_argument("--dense-k", type=int, default=20)
    p_search.add_argument("--bm25-k", type=int, default=20)
    p_search.add_argument("--rerank", action="store_true", help="Apply cross-encoder reranking")
    p_search.add_argument("--reconstruct", action="store_true", help="Reconstruct full sections")
    p_search.add_argument("--device", type=str, default=None)

    # --- EVAL subcommand ---
    p_eval = sub.add_parser("eval", help="Run hard validation evaluation")
    p_eval.add_argument(
        "--index-dir", type=str, default="embedding_acts",
        help="Directory with index.faiss and bm25.db",
    )
    p_eval.add_argument("--device", type=str, default=None)

    args = parser.parse_args()

    # Auto-detect device
    device = getattr(args, "device", None)
    if device is None:
        import torch
        if torch.cuda.is_available():
            device = "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"

    # Default to build if no subcommand
    cmd = args.cmd or "build"

    if cmd == "build":
        _run_build(args, device)
    elif cmd == "search":
        _run_search(args, device)
    elif cmd == "eval":
        _run_eval(args, device)
    else:
        parser.print_help()


def _run_build(args, device: str) -> None:
    """Execute the full build pipeline."""
    t_start = time.time()

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)
    faiss_path = os.path.join(output_dir, "index.faiss")
    db_path = os.path.join(output_dir, "bm25.db")

    # Step 1: Load data
    log.info("=" * 60)
    log.info("STEP 1/5: Loading data")
    log.info("=" * 60)
    chunks = load_data(args.json_dir)
    if not chunks:
        log.error("No chunks loaded. Aborting.")
        sys.exit(1)

    # Step 2: Load model
    log.info("=" * 60)
    log.info("STEP 2/5: Loading model %s", MODEL_NAME)
    log.info("=" * 60)
    log.info("Using device: %s", device)
    model = SentenceTransformer(MODEL_NAME, device=device)

    # Step 3: Build embeddings
    log.info("=" * 60)
    log.info("STEP 3/5: Building embeddings")
    log.info("=" * 60)
    embeddings = build_embeddings(chunks, model, batch_size=args.batch_size)

    # Verify alignment
    if len(chunks) != embeddings.shape[0]:
        log.error(
            "FATAL: chunk count (%d) != embedding count (%d)",
            len(chunks), embeddings.shape[0],
        )
        sys.exit(1)

    # Step 4: Build FAISS
    log.info("=" * 60)
    log.info("STEP 4/5: Building FAISS index")
    log.info("=" * 60)
    build_faiss(embeddings, faiss_path)

    # Step 5: Build SQLite
    log.info("=" * 60)
    log.info("STEP 5/5: Building SQLite database")
    log.info("=" * 60)
    build_sqlite(chunks, db_path)

    elapsed = time.time() - t_start
    log.info("Pipeline complete in %.1fs", elapsed)

    # Validate
    if not args.skip_validate:
        validate(faiss_path, db_path, model)

    log.info("All outputs saved to: %s", output_dir)
    log.info("  FAISS index: %s", faiss_path)
    log.info("  SQLite DB:   %s", db_path)


def _run_search(args, device: str) -> None:
    """Execute hybrid search + optional reranking + optional section reconstruction."""
    index_dir = args.index_dir
    faiss_path = os.path.join(index_dir, "index.faiss")
    db_path = os.path.join(index_dir, "bm25.db")

    if not os.path.exists(faiss_path):
        log.error("FAISS index not found: %s", faiss_path)
        sys.exit(1)
    if not os.path.exists(db_path):
        log.error("SQLite DB not found: %s", db_path)
        sys.exit(1)

    model = load_embedding_model(MODEL_NAME, device)
    index = faiss.read_index(faiss_path)
    if hasattr(index, 'nprobe'):
        index.nprobe = 10
    conn = sqlite3.connect(db_path)

    log.info("Query: %s", args.q)

    # UPGRADE 8: Failure Detection Loop
    candidate_k = RERANK_CANDIDATE_K if args.rerank else args.top_k
    query_text = args.q
    
    for attempt in range(2):
        results = hybrid_search(
            query_text, index, conn, model,
            top_k=candidate_k, dense_k=args.dense_k, bm25_k=args.bm25_k,
        )

        # Rerank
        if args.rerank and results:
            results = rerank(query_text, results, top_k=args.top_k, device=device)
            
            if attempt == 0:
                top_score = results[0].get("rerank_score", 0.0)
                # If top rerank score is below 0, it indicates poor keyword/semantic overlap
                if top_score < 0.0:
                    log.warning("Poor top score (%.2f). Applying failure detection: Expanding query proactively...", top_score)
                    # Forcing 'explanatory' expansion routing by injecting keywords
                    query_text += " procedure meaning rights"
                    continue
        break

    # UPGRADE 7: Query Logging
    os.makedirs("logs", exist_ok=True)
    q_type = results[0].get("query_type", "unknown") if results else "unknown"
    log_data = {
        "timestamp": time.time(),
        "query": args.q,
        "query_type": q_type,
        "expanded_query_used": query_text,
        "top_results": [
            {
                "id": r["id"],
                "title": r["title"],
                "section": r["section_number"],
                "score": round(r.get("rerank_score", r.get("hybrid_score", 0.0)), 4)
            }
            for r in results[:args.top_k]
        ]
    }
    with open("logs/query_logs.json", "a") as f:
        f.write(json.dumps(log_data) + "\n")

    # Print results
    log.info("=" * 60)
    for rank, r in enumerate(results[:args.top_k], 1):
        score_key = "rerank_score" if "rerank_score" in r else "hybrid_score"
        log.info(
            "[%d] %s=%.4f | %s § %s: %s",
            rank, score_key, r[score_key],
            r["title"], r["section_number"], r["section_title"],
        )
        snippet = r["chunk_text"][:250].replace("\n", " ")
        log.info("    %s...", snippet)

    # Reconstruct sections
    if args.reconstruct and results:
        log.info("=" * 60)
        log.info("SECTION RECONSTRUCTION")
        sections = reconstruct_section(results[:args.top_k], conn)
        for i, sec in enumerate(sections, 1):
            log.info(
                "[Section %d] %s § %s: %s (%d chunks merged, score=%.4f)",
                i, sec["title"], sec["section_number"], sec["section_title"],
                sec["chunk_count"], sec["best_score"],
            )
            preview = sec["merged_text"][:400].replace("\n", " ")
            log.info("    %s...", preview)

    conn.close()


def _run_eval(args, device: str) -> None:
    """Run hard validation evaluation."""
    index_dir = args.index_dir
    faiss_path = os.path.join(index_dir, "index.faiss")
    db_path = os.path.join(index_dir, "bm25.db")

    model = load_embedding_model(MODEL_NAME, device)
    index = faiss.read_index(faiss_path)
    if hasattr(index, 'nprobe'):
        index.nprobe = 10
    conn = sqlite3.connect(db_path)

    evaluate(index, conn, model, device=device)
    conn.close()


if __name__ == "__main__":
    main()
