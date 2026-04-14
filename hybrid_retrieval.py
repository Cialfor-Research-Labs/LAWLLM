import argparse
import json
import math
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sentence_transformers import CrossEncoder, SentenceTransformer


MODEL_NAME = "BAAI/bge-large-en-v1.5"
EMBEDDING_DIM = 1024
BGE_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-2-v2"


@dataclass
class CorpusConfig:
    name: str
    embeddings_dir: str
    model_name: str
    dim: int

    @property
    def faiss_path(self) -> str:
        return os.path.join(self.embeddings_dir, "index.faiss")

    @property
    def metadata_path(self) -> str:
        return os.path.join(self.embeddings_dir, "metadata.json")

    @property
    def bm25_db_path(self) -> str:
        return os.path.join(self.embeddings_dir, "bm25.db")


CORPORA: Dict[str, CorpusConfig] = {
    "acts": CorpusConfig(
        name="acts",
        embeddings_dir="embedding_acts",
        model_name="BAAI/bge-large-en-v1.5",
        dim=1024
    ),
    "judgements": CorpusConfig(
        name="judgements",
        embeddings_dir="embedding_judgements",
        model_name="BAAI/bge-large-en-v1.5",
        dim=1024
    ),
}


@lru_cache(maxsize=4)
def load_embedding_model(model_name: str, device: str = "cpu") -> SentenceTransformer:
    try:
        if device == "cuda":
            import torch
            if not torch.cuda.is_available():
                device = "cpu"
        
        return SentenceTransformer(model_name, device=device, local_files_only=True)
    except Exception:
        return SentenceTransformer(model_name, device=device)


@lru_cache(maxsize=2)
def load_reranker(model_name: str = BGE_RERANKER_MODEL) -> CrossEncoder:
    candidates = [
        model_name,
        "cross-encoder/ms-marco-MiniLM-L-2-v2",
        "BAAI/bge-reranker-base",
    ]
    last_exc = None
    for cand in candidates:
        try:
            return CrossEncoder(cand, device="cpu", max_length=512, local_files_only=True)
        except Exception as exc:
            last_exc = exc
    raise RuntimeError(f"Unable to load any reranker model from local cache: {last_exc}")


def ensure_exists(path: str, label: str) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing {label}: {path}")


def connect_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    return conn


def build_bm25_index(cfg: CorpusConfig, rebuild: bool = False) -> None:
    ensure_exists(cfg.metadata_path, "metadata")

    if rebuild and os.path.exists(cfg.bm25_db_path):
        os.remove(cfg.bm25_db_path)

    conn = connect_db(cfg.bm25_db_path)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS docs (
            id INTEGER PRIMARY KEY,
            source_json TEXT,
            document_id TEXT,
            title TEXT,
            section_number TEXT,
            section_title TEXT,
            context_path TEXT,
            unit_type TEXT,
            chunk_id TEXT,
            chunk_index INTEGER,
            chunk_text TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts
        USING fts5(chunk_text, content='docs', content_rowid='id', tokenize='unicode61')
        """
    )

    cur.execute("SELECT COUNT(1) FROM docs")
    existing_docs = cur.fetchone()[0]
    if existing_docs > 0 and not rebuild:
        conn.close()
        print(f"[{cfg.name}] bm25.db already built ({existing_docs} docs): {cfg.bm25_db_path}")
        return

    cur.execute("DELETE FROM docs_fts")
    cur.execute("DELETE FROM docs")
    conn.commit()

    with open(cfg.metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    print(f"[{cfg.name}] Building BM25 index from {len(metadata)} metadata records...")

    batch_size = 5000
    rows = []

    for idx, rec in enumerate(metadata, start=1):
        rows.append(
            (
                idx,
                rec.get("source_json"),
                rec.get("document_id"),
                rec.get("title"),
                str(rec.get("section_number", "")) if rec.get("section_number") is not None else None,
                rec.get("section_title"),
                rec.get("context_path"),
                rec.get("unit_type"),
                rec.get("chunk_id"),
                rec.get("chunk_index"),
                rec.get("chunk_text", ""),
            )
        )

        if len(rows) >= batch_size:
            cur.executemany(
                """
                INSERT INTO docs(
                    id, source_json, document_id, title, section_number, section_title,
                    context_path, unit_type, chunk_id, chunk_index, chunk_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            rows.clear()
            conn.commit()

    if rows:
        cur.executemany(
            """
            INSERT INTO docs(
                id, source_json, document_id, title, section_number, section_title,
                context_path, unit_type, chunk_id, chunk_index, chunk_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()

    cur.execute("INSERT INTO docs_fts(rowid, chunk_text) SELECT id, chunk_text FROM docs")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_chunk_id ON docs(chunk_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_doc_id ON docs(document_id)")
    conn.commit()

    cur.execute("SELECT COUNT(1) FROM docs")
    total = cur.fetchone()[0]
    conn.close()
    print(f"[{cfg.name}] BM25 index ready: {cfg.bm25_db_path} ({total} docs)")


def query_to_fts_match(query: str) -> str:
    terms = re.findall(r"[A-Za-z0-9_]+", query.lower())
    if not terms:
        safe = query.replace('"', "")
        return f'"{safe}"'

    # OR semantics improves recall for long legal queries; BM25 still ranks specificity.
    return " OR ".join([f'"{t}"*' for t in terms])


def _safe_norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _looks_like_precise_query(query: str) -> bool:
    q = _safe_norm_text(query)
    precise_patterns = [
        r"\bsection\s+\d+[a-z]?\b",
        r"\bs\.?\s*\d+[a-z]?\b",
        r"\b(?:ipc|crpc|iea|bns|bnss|bsa)\b",
    ]
    return any(re.search(pattern, q) for pattern in precise_patterns)


def _looks_like_explanatory_query(query: str) -> bool:
    q = _safe_norm_text(query)
    explanatory_markers = ["explain", "meaning", "difference", "how", "why", "what is", "procedure", "steps"]
    return any(marker in q for marker in explanatory_markers)


def _query_profile(query: str) -> str:
    if _looks_like_precise_query(query):
        return "precise"
    if _looks_like_explanatory_query(query):
        return "explanatory"
    return "general"


def _dynamic_weights(query: str, dense_weight: float, bm25_weight: float) -> Tuple[float, float, str]:
    profile = _query_profile(query)
    d = float(dense_weight)
    b = float(bm25_weight)

    if profile == "precise":
        d, b = 0.45, 0.55
    elif profile == "explanatory":
        d, b = 0.75, 0.25

    total = max(d + b, 1e-9)
    return d / total, b / total, profile


def _era_preference(query: str, explicit_era_filter: Optional[str] = None) -> Optional[str]:
    if explicit_era_filter:
        return _safe_norm_text(explicit_era_filter)

    q = _safe_norm_text(query)
    modern_markers = ["bns", "bnss", "bsa", "bhartiya nyaya", "bhartiya nagrik", "bhartiya sakshya"]
    legacy_markers = ["ipc", "crpc", "evidence act", "indian penal code", "code of criminal procedure"]
    if any(marker in q for marker in modern_markers):
        return "modern_criminal"
    if any(marker in q for marker in legacy_markers):
        return "legacy_criminal"
    return None


def _era_multiplier(item: Dict[str, Any], era_pref: Optional[str]) -> float:
    if not era_pref:
        return 1.0
    hay = _safe_norm_text(
        " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("document_id") or ""),
                str(item.get("source_json") or ""),
                str(item.get("chunk_text") or "")[:120],
            ]
        )
    )
    modern_markers = ["bns", "bnss", "bsa", "bhartiya nyaya", "bhartiya nagrik", "bhartiya sakshya"]
    legacy_markers = ["ipc", "crpc", "evidence act", "indian penal code", "code of criminal procedure"]

    if era_pref == "modern_criminal":
        if any(marker in hay for marker in modern_markers):
            return 1.2
        if any(marker in hay for marker in legacy_markers):
            return 0.82
    if era_pref == "legacy_criminal":
        if any(marker in hay for marker in legacy_markers):
            return 1.2
        if any(marker in hay for marker in modern_markers):
            return 0.82
    return 1.0


def _passes_structural_filters(
    item: Dict[str, Any],
    act_filter: Optional[str],
    section_filter: Optional[str],
) -> bool:
    if not act_filter and not section_filter:
        return True

    hay = _safe_norm_text(
        " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("document_id") or ""),
                str(item.get("source_json") or ""),
            ]
        )
    )

    if act_filter:
        target = _safe_norm_text(act_filter)
        if target and target not in hay:
            return False

    if section_filter:
        target_sec = _safe_norm_text(section_filter).replace("section ", "").replace("s.", "").strip()
        item_sec = _safe_norm_text(item.get("section_number"))
        item_sec = item_sec.replace("section ", "").replace("s.", "").strip()
        if target_sec and item_sec and target_sec != item_sec:
            return False
    return True


def normalize_scores(score_map: Dict[int, float]) -> Dict[int, float]:
    if not score_map:
        return {}
    values = list(score_map.values())
    lo = min(values)
    hi = max(values)
    if hi - lo < 1e-12:
        return {k: 1.0 for k in score_map}
    return {k: (v - lo) / (hi - lo) for k, v in score_map.items()}


def dense_search(index, model: SentenceTransformer, query: str, k: int) -> Dict[int, float]:
    q_emb = model.encode([query], normalize_embeddings=True, convert_to_numpy=True).astype("float32")
    distances, indices = index.search(q_emb, k)

    out = {}
    for score, idx in zip(distances[0], indices[0]):
        if idx < 0:
            continue
        # cosine in [-1, 1] -> [0, 1]
        out[int(idx) + 1] = float((score + 1.0) / 2.0)
    return out


def bm25_search(conn: sqlite3.Connection, query: str, k: int, corpus_name: str = "acts") -> Dict[int, float]:
    match_expr = query_to_fts_match(query)
    cur = conn.cursor()
    
    table_name = "docs_fts" if corpus_name == "acts" else "judgements_fts"
    
    cur.execute(
        f"""
        SELECT rowid, bm25({table_name}) AS rank
        FROM {table_name}
        WHERE {table_name} MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (match_expr, k),
    )
    rows = cur.fetchall()
    return {int(r[0]): float(-r[1]) for r in rows}


def fetch_docs(conn: sqlite3.Connection, ids: List[int], corpus_name: str = "acts") -> Dict[int, Dict]:
    if not ids:
        return {}

    placeholders = ",".join(["?"] * len(ids))
    cur = conn.cursor()
    
    if corpus_name == "acts":
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
                "source_json": None, # Missing in new schema, providing default
                "document_id": row[1],
                "title": row[2],
                "section_number": row[3],
                "section_title": row[4],
                "context_path": row[5],
                "unit_type": "section", # Providing default
                "chunk_id": row[6],
                "chunk_index": row[7],
                "chunk_text": row[8],
            }
    else: # judgements
        cur.execute(
            f"""
            SELECT id, document_id, case_name, court, bench, date, chunk_type, chunk_text
            FROM judgements
            WHERE id IN ({placeholders})
            """,
            ids,
        )
        results = {}
        for row in cur.fetchall():
            results[int(row[0])] = {
                "document_id": row[1],
                "title": row[2], # Map case_name to title for consistency
                "court": row[3],
                "bench": row[4],
                "date": row[5],
                "chunk_type": row[6],
                "chunk_text": row[7],
                "source_json": row[1] + ".json"
            }
    return results


def hybrid_search(
    cfg: CorpusConfig,
    query: str,
    top_k: int,
    dense_k: int,
    bm25_k: int,
    dense_weight: float,
    bm25_weight: float,
    domain_filter: Optional[str] = None,
    act_filter: Optional[str] = None,
    section_filter: Optional[str] = None,
    era_filter: Optional[str] = None,
) -> List[Dict]:
    # For judgements, use metadata.db directly from embedding_judgements/
    db_path = os.path.join(cfg.embeddings_dir, "metadata.db") if cfg.name == "judgements" else cfg.bm25_db_path
    
    ensure_exists(cfg.faiss_path, "FAISS index")
    ensure_exists(db_path, "BM25 db")

    t_total0 = time.time()
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = load_embedding_model(cfg.model_name, device=device)
    import faiss
    index = faiss.read_index(cfg.faiss_path)
    
    # Validation: Dimension match
    assert index.d == cfg.dim, f"Dimension mismatch for {cfg.name}: index.d={index.d} vs cfg.dim={cfg.dim}"
    
    conn = connect_db(db_path)

    t0 = time.time()
    dense_raw = dense_search(index, model, query, dense_k)
    dense_ms = (time.time() - t0) * 1000.0

    t0 = time.time()
    bm25_raw = bm25_search(conn, query, bm25_k, corpus_name=cfg.name)
    bm25_ms = (time.time() - t0) * 1000.0

    dense_norm = normalize_scores(dense_raw)
    bm25_norm = normalize_scores(bm25_raw)
    dynamic_dense_weight, dynamic_bm25_weight, q_profile = _dynamic_weights(query, dense_weight, bm25_weight)
    era_pref = _era_preference(query, era_filter)

    all_ids = sorted(set(dense_norm.keys()) | set(bm25_norm.keys()))
    docs = fetch_docs(conn, all_ids, corpus_name=cfg.name)
    conn.close()

    # Rule-Based Metadata Filtering
    if domain_filter == "criminal":
        criminal_acts = {
            "bns", "bnss", "ipc", "crpc", "bsa", "iea", "it act", "motor vehicles", "ndps", "pocso",
            "theft", "stole", "stolen", "robbery", "theft", "bhartiya", "nyay", "sanhita", "nagrik",
            "suraksha", "sakshya", "adhiniyam", "indian penal", "criminal procedure",
            "evidence act", "information technology", "state vs", "union of india", "v. state"
        }
        filtered_docs = {}
        for doc_id, item in docs.items():
            title = str(item.get("title", "")).lower()
            doc_did = str(item.get("document_id", "")).lower()
            combined = f"{title} {doc_did}".lower()
            if any(act in combined for act in criminal_acts):
                filtered_docs[doc_id] = item
        docs = filtered_docs

    t0 = time.time()
    ranked = []
    for doc_id in all_ids:
        item = docs.get(doc_id)
        if not item:
            continue

        if cfg.name == "acts" and not _passes_structural_filters(item, act_filter=act_filter, section_filter=section_filter):
            continue

        d = dense_norm.get(doc_id, 0.0)
        b = bm25_norm.get(doc_id, 0.0)
        score = dynamic_dense_weight * d + dynamic_bm25_weight * b
        score *= _era_multiplier(item, era_pref)

        item.update(
            {
                "id": doc_id,
                "hybrid_score": score,
                "dense_score": d,
                "bm25_score": b,
                "corpus": cfg.name,
                "query_profile": q_profile,
                "dense_weight_used": dynamic_dense_weight,
                "bm25_weight_used": dynamic_bm25_weight,
                "era_preference": era_pref,
                "retrieval_trace": {
                    "device": device,
                    "query_profile": q_profile,
                    "dense_ms": round(dense_ms, 2),
                    "bm25_ms": round(bm25_ms, 2),
                    "candidates_dense": len(dense_norm),
                    "candidates_bm25": len(bm25_norm),
                },
            }
        )
        ranked.append(item)

    fusion_ms = (time.time() - t0) * 1000.0
    total_ms = (time.time() - t_total0) * 1000.0
    for item in ranked:
        trace = item.get("retrieval_trace") or {}
        trace["fusion_ms"] = round(fusion_ms, 2)
        trace["total_ms"] = round(total_ms, 2)
        item["retrieval_trace"] = trace

    ranked.sort(key=lambda x: x["hybrid_score"], reverse=True)
    return ranked[:top_k]


def print_results(results: List[Dict]) -> None:
    for i, res in enumerate(results, start=1):
        primary = res.get("final_score", res["hybrid_score"])
        score_line = f"\n[{i}] score={primary:.4f} hybrid={res['hybrid_score']:.4f} dense={res['dense_score']:.4f} bm25={res['bm25_score']:.4f}"
        if "rerank_score" in res:
            score_line += f" rerank={res['rerank_score']:.4f}"
        print(score_line)
        print(f"Corpus: {res['corpus']} | File: {res.get('source_json')} | Chunk: {res.get('chunk_id')}")
        print(f"Doc: {res.get('title')} | Sec: {res.get('section_number')} | Context: {res.get('context_path')}")
        snippet = (res.get("chunk_text") or "").replace("\n", " ")
        if len(snippet) > 280:
            snippet = snippet[:280] + "..."
        print(f"Text: {snippet}")


def rerank_results(
    query: str,
    results: List[Dict],
    top_k: int,
    rerank_top_n: int,
    rerank_model: str,
    rerank_batch_size: int,
) -> List[Dict]:
    if not results:
        return results

    top_n = min(max(rerank_top_n, top_k), len(results))
    head = results[:top_n]
    tail = results[top_n:]

    try:
        model = load_reranker(rerank_model)
    except Exception as exc:
        print(f"[rerank] warning: unable to load reranker '{rerank_model}' ({exc}); using hybrid rank only.")
        return results[:top_k]

    pairs = []
    for item in head:
        enriched = "\n".join(
            [
                str(item.get("title") or ""),
                f"Section {item.get('section_number')}: {item.get('section_title')}",
                str(item.get("context_path") or ""),
                str(item.get("chunk_text") or ""),
            ]
        ).strip()
        pairs.append([query, enriched])
    scores = model.predict(pairs, batch_size=rerank_batch_size, show_progress_bar=False)

    for item, score in zip(head, scores):
        raw_score = float(score)
        normalized_score = 1.0 / (1.0 + math.exp(-raw_score))
        item["rerank_score"] = normalized_score
        item["rerank_raw_score"] = raw_score
        hybrid = float(item.get("hybrid_score", 0.0) or 0.0)
        # Keep reranker meaningful but avoid full overwrite of hybrid signal.
        item["final_score"] = (0.65 * hybrid) + (0.35 * normalized_score)

    head.sort(key=lambda x: x["final_score"], reverse=True)
    for item in tail:
        if "final_score" not in item:
            item["final_score"] = float(item.get("hybrid_score", 0.0) or 0.0)
    merged = head + tail
    merged.sort(key=lambda x: float(x.get("final_score", x.get("hybrid_score", 0.0)) or 0.0), reverse=True)
    return merged[:top_k]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BM25 + FAISS hybrid retrieval for legal corpora")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="Build BM25 index(es) from embedding metadata")
    p_build.add_argument("--corpus", choices=["acts", "judgements", "all"], default="all")
    p_build.add_argument("--rebuild", action="store_true", help="Rebuild BM25 DB from scratch")

    p_query = sub.add_parser("query", help="Run hybrid retrieval")
    p_query.add_argument("--corpus", choices=["acts", "judgements", "all"], default="acts")
    p_query.add_argument("--q", required=True, help="Query text")
    p_query.add_argument("--top-k", type=int, default=10)
    p_query.add_argument("--dense-k", type=int, default=80)
    p_query.add_argument("--bm25-k", type=int, default=80)
    p_query.add_argument("--dense-weight", type=float, default=0.6)
    p_query.add_argument("--bm25-weight", type=float, default=0.4)
    p_query.add_argument("--rerank", action="store_true", help="Apply BGE reranking on hybrid candidates")
    p_query.add_argument("--rerank-model", default=BGE_RERANKER_MODEL)
    p_query.add_argument("--rerank-top-n", type=int, default=50)
    p_query.add_argument("--rerank-batch-size", type=int, default=16)
    p_query.add_argument("--act-filter", default=None, help="Restrict acts retrieval to matching act title/id")
    p_query.add_argument("--section-filter", default=None, help="Restrict acts retrieval to matching section number")
    p_query.add_argument("--era-filter", default=None, help="Criminal law era preference: modern_criminal|legacy_criminal")

    return parser.parse_args()


def run_build(corpus: str, rebuild: bool) -> None:
    targets = [CORPORA[corpus]] if corpus in CORPORA else [CORPORA["acts"]]
    for cfg in targets:
        build_bm25_index(cfg, rebuild=rebuild)


def run_hybrid_retrieval(args: argparse.Namespace) -> List[Dict]:
    """
    Programmatic entry point for hybrid retrieval.
    Returns a list of result dictionaries.
    """
    candidate_k = max(args.top_k, getattr(args, "rerank_top_n", 50)) if getattr(args, "rerank", False) else args.top_k

    cfg = CORPORA[args.corpus]
    domain_filter = getattr(args, "domain_filter", None)
    
    results = hybrid_search(
        cfg,
        query=args.q,
        top_k=candidate_k,
        dense_k=args.dense_k,
        bm25_k=args.bm25_k,
        dense_weight=args.dense_weight,
        bm25_weight=args.bm25_weight,
        domain_filter=domain_filter,
        act_filter=getattr(args, "act_filter", None),
        section_filter=getattr(args, "section_filter", None),
        era_filter=getattr(args, "era_filter", None),
    )
    final = results
    if getattr(args, "rerank", False):
        final = rerank_results(
            query=args.q,
            results=results,
            top_k=args.top_k,
            rerank_top_n=getattr(args, "rerank_top_n", 50),
            rerank_model=getattr(args, "rerank_model", BGE_RERANKER_MODEL),
            rerank_batch_size=getattr(args, "rerank_batch_size", 16),
        )
    else:
        final = results[: args.top_k]
    return final


def main() -> None:
    args = parse_args()

    if args.cmd == "build":
        run_build(corpus=args.corpus, rebuild=args.rebuild)
    elif args.cmd == "query":
        results = run_hybrid_retrieval(args)
        print_results(results)


if __name__ == "__main__":
    main()
