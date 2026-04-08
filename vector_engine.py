#!/usr/bin/env python3
"""
vector_engine.py — High-precision vector indexing and retrieval for legal JSON corpus.
Uses sentence-transformers (all-MiniLM-L6-v2) and FAISS.
"""

import os
import json
import logging
import argparse
import numpy as np
import faiss
from pathlib import Path
from typing import List, Dict, Any, Tuple
from sentence_transformers import SentenceTransformer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Constants
MODEL_NAME = "BAAI/bge-large-en-v1.5"
EMBEDDING_DIM = 1024
DEFAULT_CACHE_DIR = "embedding_acts/"

class VectorEngine:
    def __init__(self, model_name: str = MODEL_NAME):
        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.index = None
        self.metadata = []

    def load_json_corpus(self, folder_path: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        """
        Loads all JSON files and extracts chunk_text and metadata.
        Supports:
        1. Flat schema: { chunk_text, metadata... }
        2. Nested schema (v2): { sections: [ { units: [ { text_cleaned, ... } ] } ] }
        """
        texts = []
        metadatas = []
        
        path = Path(folder_path)
        if not path.exists():
            logger.warning(f"Input folder {folder_path} not found.")
            return texts, metadatas

        json_files = sorted(list(path.glob("*.json")))
        logger.info(f"Found {len(json_files)} JSON files in {folder_path}")

        for jf in json_files:
            if jf.name.startswith("._"): continue
            try:
                with open(jf, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # Case 1: Nested schema (JSON_acts)
                    if isinstance(data, dict) and "sections" in data:
                        doc = data.get("document", {})
                        doc_id = doc.get("document_id")
                        doc_title = doc.get("title")
                        
                        for section in data.get("sections", []):
                            sec_num = section.get("section_number")
                            sec_title = section.get("section_title")
                            
                            for unit in section.get("units", []):
                                text = (unit.get("text_cleaned") or unit.get("text_original") or "").strip()
                                if not text: continue
                                
                                meta = {
                                    "document_id": doc_id,
                                    "title": doc_title,
                                    "section_number": sec_num,
                                    "section_title": sec_title,
                                    "chunk_id": unit.get("unit_id"),
                                    "context_path": unit.get("context_path")
                                }
                                texts.append(text)
                                metadatas.append(meta)
                                
                    # Case 2: Flat schema or list of objects
                    else:
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            text = item.get("chunk_text", "").strip()
                            if not text: continue
                            metadata = {k: v for k, v in item.items() if k != "chunk_text"}
                            texts.append(text)
                            metadatas.append(metadata)
                            
            except Exception as e:
                logger.error(f"Error loading {jf}: {e}")
                
        return texts, metadatas

    def build_index(self, texts: List[str], metadatas: List[Dict[str, Any]]):
        """Generates embeddings and builds a FAISS index."""
        if not texts:
            logger.error("No texts provided for indexing.")
            return

        logger.info(f"Generating embeddings for {len(texts)} chunks...")
        # Inject chunk_text into metadata for retrieval
        for i, text in enumerate(texts):
            metadatas[i]["chunk_text"] = text
            
        embeddings = self.model.encode(texts, show_progress_bar=True, batch_size=32)
        embeddings = np.array(embeddings).astype('float32')

        self.index = faiss.IndexFlatIP(EMBEDDING_DIM)
        faiss.normalize_L2(embeddings)
        self.index.add(embeddings)
        self.metadata = metadatas
        
        logger.info(f"Successfully built FAISS index with {self.index.ntotal} vectors.")

    def save(self, output_dir: str):
        """Saves the FAISS index and metadata locally."""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        index_file = str(out_path / "index.faiss")
        meta_file = str(out_path / "metadata.json")
        
        faiss.write_index(self.index, index_file)
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, indent=2, ensure_ascii=False)
            
        logger.info(f"Index and metadata saved to {output_dir}")

    def load(self, input_dir: str):
        """Loads the FAISS index and metadata."""
        in_path = Path(input_dir)
        index_file = str(in_path / "index.faiss")
        meta_file = str(in_path / "metadata.json")
        
        if not os.path.exists(index_file) or not os.path.exists(meta_file):
            raise FileNotFoundError(f"Index or metadata not found in {input_dir}")
            
        self.index = faiss.read_index(index_file)
        with open(meta_file, 'r', encoding='utf-8') as f:
            self.metadata = json.load(f)
            
        logger.info(f"Index loaded with {self.index.ntotal} vectors.")

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Performs similarity search and returns results with metadata."""
        if self.index is None:
            raise RuntimeError("Index not loaded. Build or load an index first.")
            
        query_vec = self.model.encode([query])
        query_vec = np.array(query_vec).astype('float32')
        faiss.normalize_L2(query_vec)
        
        distances, indices = self.index.search(query_vec, top_k)
        
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx != -1 and idx < len(self.metadata):
                res = {
                    "score": float(dist),
                    "metadata": self.metadata[idx]
                }
                results.append(res)
                
        return results

def main():
    parser = argparse.ArgumentParser(description="Legal Vector Engine")
    parser.add_argument("--index", action="store_true", help="Build index from JSON corpus")
    parser.add_argument("--query", type=str, help="Search the index")
    parser.add_argument("--input_folder", type=str, default="embedding_acts", help="Folder with JSON chunks")
    parser.add_argument("--output_folder", type=str, default=DEFAULT_CACHE_DIR, help="Where to save/load index")
    parser.add_argument("--top_k", type=int, default=5, help="Number of results")
    
    args = parser.parse_args()
    engine = VectorEngine()

    if args.index:
        texts, metadatas = engine.load_json_corpus(args.input_folder)
        engine.build_index(texts, metadatas)
        engine.save(args.output_folder)
    
    if args.query:
        try:
            engine.load(args.output_folder)
            results = engine.search(args.query, top_k=args.top_k)
            print(f"\nResults for: '{args.query}'\n")
            for i, res in enumerate(results):
                m = res['metadata']
                print(f"[{i+1}] Score: {res['score']:.4f}")
                print(f"Act: {m.get('title', 'Unknown')} | Section: {m.get('section_number', m.get('chunk_id', 'N/A'))}")
                print(f"Text: {m.get('chunk_text', '')[:200]}...")
                print("-" * 40)
        except Exception as e:
            logger.error(f"Search failed: {e}")

if __name__ == "__main__":
    main()
