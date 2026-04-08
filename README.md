# Legal RAG Assistant (Indian Law)

This project is a domain-aware legal assistant backend + frontend focused on Indian law use cases.
It is designed to improve legal reliability by adding routing, retrieval controls, structured reasoning,
and validation layers on top of LLM generation.

## Product Purpose

The assistant answers legal questions using local legal corpora (acts + judgments), and can:

- classify legal issue/domain before retrieval
- route queries with domain constraints to reduce context bleed
- retrieve and rank context with hybrid search (dense + BM25)
- decompose queries via sub-questions for better legal coverage
- extract facts (date, amount, party type, etc.) for procedural logic
- run response validators (structure, contamination, legal era consistency)
- return actionable guidance and citations from retrieved context

## Key Problem It Solves

Plain RAG systems often return semantically similar but legally irrelevant text.
This project adds legal workflow controls to reduce:

- wrong-domain citations
- old-era law leakage (IPC/CrPC/IEA vs BNS/BNSS/BSA)
- generic non-actionable responses
- unsupported legal conclusions

## End-to-End Pipeline

1. User query arrives at `POST /query`.
2. Legal issue/domain is classified.
3. Intent route is built with domain hints and exclude terms.
4. Retrieval runs over acts/judgments indexes (hybrid ranking).
5. Optional sub-question retrieval improves context coverage.
6. Optional LLM-as-judge filters weak chunks from top results.
7. LLM answer generation runs with curated context.
8. Validators check answer quality and legal consistency.
9. Procedural layers add limitation/jurisdiction checks where applicable.

## Technology Stack

- Backend: FastAPI + Python
- Retrieval: FAISS + BM25 + optional reranker
- LLM runtime: Ollama (default model `llama3.1:8b`)
- Frontend: React + Vite (inside `ui/`)

## API Endpoints

- `GET /health`:
  - basic service health/version response
- `POST /query`:
  - full legal retrieval + generation + validation flow
- `POST /extract_facts`:
  - structured entity extraction for procedural checks

## Project Structure (Top Level)

- `retrieval_api.py`: FastAPI entrypoint and query orchestration
- `context_builder.py`: retrieval orchestration and context pack assembly
- `hybrid_retrieval.py`: dense + BM25 retrieval logic
- `legal_router.py`: legal domain classification + intent routing
- `sub_question_engine.py`: query decomposition and merged retrieval
- `llm_judge.py`: lightweight context relevance judge stage
- `llama_legal_answer.py`: prompt construction + Ollama call
- `answer_validator.py`: structure/domain/era validation checks
- `fact_extractor.py`: LLM + heuristic fact extraction
- `statutory_checks.py`: limitation and statutory procedural checks
- `jurisdiction_validator.py`: claim-amount forum selection checks
- `safe_fallback.py`: safe fallback outputs when validations fail
- `run_eval.py`: evaluation runner against `eval_cases.json`
- `JSON_acts/`: source structured legal acts
- `embeddings_acts/` and `embeddings_judgements/`: local indexes
- `ui/`: frontend app (chat experience; includes `LegalChat.tsx`)

## Frontend Note

The `ui/` folder is already integrated as the frontend codebase.
`ui/src/components/LegalChat.tsx` is the active chat component for the product workflow.

## How To Use

1. Follow setup steps in `INSTALL.md`.
2. Start backend API (`retrieval_api.py` via Uvicorn).
3. Start frontend (`ui` with Vite).
4. Ask legal queries from frontend or API.
5. Run evaluations before significant changes.

## Quality and Reliability Principles

- prefer correct and relevant law over verbose output
- avoid blind citations
- ask for missing facts when legal computation depends on them
- reject context contamination and era mismatch
- log all architecture/code changes in `CHANGE_HISTORY.md`

## Documentation Files

- `INSTALL.md`: full installation and run instructions
- `CODE_DESCRIPTOR.md`: file-by-file module purpose
- `CHANGE_HISTORY.md`: plain-English change log (must update on each change)

## Important Disclaimer

This software is a legal information assistant and not a substitute for licensed legal advice.
Outputs should be reviewed by a qualified professional before filing or litigation decisions.
