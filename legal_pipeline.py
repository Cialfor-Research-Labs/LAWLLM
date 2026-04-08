import os
import json
import logging
import numpy as np
import faiss
from glob import glob
from typing import List, Dict, Tuple, Any
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def load_json_files(directory: str) -> List[str]:
    """
    Finds all JSON files in the specified directory.
    """
    pattern = os.path.join(directory, "*.json")
    files = glob(pattern)
    logger.info(f"Found {len(files)} JSON files in {directory}")
    return files

def extract_text_and_metadata(file_paths: List[str]) -> Tuple[List[str], List[Dict]]:
    """
    Extracts chunk_text and metadata from a list of JSON files.
    Supports both flat list (judgements) and nested sections (acts) structures.
    """
    all_texts = []
    all_metadata = []
    
    for file_path in tqdm(file_paths, desc="Extracting data"):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Handle Acts (nested structure)
            if isinstance(data, dict) and "sections" in data:
                doc_meta = data.get("document", {})
                sections = data.get("sections", [])
                for section in sections:
                    units = section.get("units", [])
                    for unit in units:
                        text = unit.get("text", "").strip()
                        if not text:
                            continue
                        
                        metadata = {
                            "document_id": doc_meta.get("document_id", "N/A"),
                            "title": doc_meta.get("title", "N/A"),
                            "section_number": unit.get("section_number", section.get("section_number", "N/A")),
                            "section_title": unit.get("section_title", section.get("section_title", "N/A")),
                            "context_path": unit.get("context_path", "N/A"),
                            "unit_type": unit.get("unit_type", "chunk"),
                            "chunk_id": unit.get("unit_id", str(len(all_texts))),
                            "chunk_text": text
                        }
                        all_texts.append(text)
                        all_metadata.append(metadata)
            
            # Handle Judgements (flat list or single dict)
            else:
                chunks = data if isinstance(data, list) else [data]
                for chunk in chunks:
                    text = chunk.get("chunk_text", "")
                    if not text:
                        continue
                    
                    metadata = {
                        "document_id": chunk.get("document_id", "N/A"),
                        "title": chunk.get("title", "N/A"),
                        "year": chunk.get("year", "N/A"),
                        "domain": chunk.get("domain", "N/A"),
                        "jurisdiction": chunk.get("jurisdiction", "N/A"),
                        "source_path": chunk.get("source_path", "N/A"),
                        "page_number": chunk.get("page_number", "N/A"),
                        "chunk_id": chunk.get("chunk_id", "N/A"),
                        "chunk_text": text
                    }
                    all_texts.append(text)
                    all_metadata.append(metadata)
                
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            
    logger.info(f"Extracted {len(all_texts)} total chunks.")
    return all_texts, all_metadata

def generate_embeddings(texts: List[str], model_name: str = "all-MiniLM-L6-v2", batch_size: int = 32) -> np.ndarray:
    """
    Generates normalized embeddings using sentence-transformers in batches.
    """
    logger.info(f"Initializing embedding model: {model_name}")
    model = SentenceTransformer(model_name)
    
    logger.info(f"Generating embeddings for {len(texts)} texts (batch_size={batch_size})...")
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True # Crucial for IndexFlatIP (cosine similarity)
    )
    
    return embeddings.astype('float32')

def build_faiss_index(embeddings: np.ndarray) -> faiss.IndexFlatIP:
    """
    Builds a FAISS IndexFlatIP for similarity search.
    """
    dimension = embeddings.shape[1]
    logger.info(f"Building FAISS IndexFlatIP with dimension {dimension}")
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)
    logger.info(f"Index built with {index.ntotal} vectors.")
    return index

def save_index(index: faiss.Index, metadata: List[Dict], output_dir: str = "."):
    """
    Saves the FAISS index and metadata list to disk.
    """
    os.makedirs(output_dir, exist_ok=True)
    index_file = os.path.join(output_dir, "index.faiss")
    metadata_file = os.path.join(output_dir, "metadata.json")
    
    logger.info(f"Saving index to {index_file}...")
    faiss.write_index(index, index_file)
    
    logger.info(f"Saving metadata to {metadata_file}...")
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    logger.info("Storage completed.")

def search_and_print(query: str, model_name: str, index: faiss.Index, metadata: List[Dict], top_k: int = 5):
    """
    Performs a retrieval test.
    """
    logger.info(f"\nRetrieval Test for query: '{query}'")
    model = SentenceTransformer(model_name)
    query_embedding = model.encode([query], normalize_embeddings=True).astype('float32')
    
    distances, indices = index.search(query_embedding, top_k)
    
    for i in range(len(indices[0])):
        idx = indices[0][i]
        if idx == -1: continue
        
        res = metadata[idx]
        score = distances[0][i]
        
        print(f"\n[Rank {i+1}] (Score: {score:.4f})")
        print(f"Title: {res.get('title', 'N/A')} | Year: {res.get('year', 'N/A')} | Chunk ID: {res.get('chunk_id', 'N/A')}")
        print(f"Text: {res.get('chunk_text', '')[:200]}...")
        print("-" * 40)

if __name__ == "__main__":
    # Integration Run - Use relative path or env var for Cloud/Linux portability
    DATA_DIR = os.getenv("DATA_DIR", "json_judgements")
    MODEL_NAME = "all-MiniLM-L6-v2"
    
    # 1. Load Files (Process all files for production)
    file_paths = load_json_files(DATA_DIR)
    
    # 2. Extract
    texts, metadata = extract_text_and_metadata(file_paths)
    
    if texts:
        # 3. Embed
        embeddings = generate_embeddings(texts, model_name=MODEL_NAME)
        
        # 4. Index
        index = build_faiss_index(embeddings)
        
        # 5. Save
        OUTPUT_DIR = os.getenv("OUTPUT_DIR", "embeddings_acts")
        save_index(index, metadata, output_dir=OUTPUT_DIR)

        # 6. Rebuild BM25
        logger.info("Triggering BM25 database build...")
        try:
            from hybrid_retrieval import CORPORA, build_bm25_index
            cfg = CORPORA.get("acts")
            if cfg:
                build_bm25_index(cfg, rebuild=True)
        except Exception as e:
            logger.error(f"Failed to rebuild BM25: {e}")
        
        # 6. Test
        search_and_print("Insolvency and Bankruptcy Code Section 238", MODEL_NAME, index, metadata)
    else:
        logger.error("No texts extracted. Check data directory.")
