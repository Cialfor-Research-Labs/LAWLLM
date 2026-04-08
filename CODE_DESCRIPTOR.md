# Code Descriptor

This file explains what each major file/module does in the project.

## Core API and Orchestration

- `retrieval_api.py`
  - Main FastAPI service.
  - Exposes `/health`, `/query`, `/extract_facts`.
  - Orchestrates routing, retrieval, answer generation, validation, and procedural checks.

- `legal_pipeline.py`
  - Optional/alternate pipeline wiring utilities.
  - Keeps end-to-end flow glue for experiments or reusable orchestration code.

## Retrieval Layer

- `hybrid_retrieval.py`
  - Runs hybrid retrieval using dense vectors + BM25.
  - Handles ranking fusion and top-k candidate selection.

- `context_builder.py`
  - Converts retrieval results into final context packs for LLM prompts.
  - Applies filters, chunk shaping, scoring balance, and citation mapping support.

- `sub_question_engine.py`
  - Splits user query into legal sub-questions (issue/rule/remedy style).
  - Runs retrieval per sub-question and merges results.

- `llm_judge.py`
  - LLM-based lightweight relevance judge over top retrieved chunks.
  - Helps reject semantically close but legally irrelevant blocks.

## Routing and Domain Control

- `legal_router.py`
  - Classifies legal domain (consumer/property/criminal/labour/contract/general).
  - Builds intent route with include/exclude clues to reduce domain contamination.

## Generation Layer

- `llama_legal_answer.py`
  - Builds the answer-generation prompt.
  - Calls Ollama model and returns generated legal response text.

## Validation and Safety

- `answer_validator.py`
  - Validates output structure.
  - Detects domain contamination and legal era mismatch.
  - Checks applicable-law quality constraints.

- `safe_fallback.py`
  - Returns safe fallback responses when validation fails or context is weak.
  - Reduces risk of overconfident wrong legal advice.

## Fact and Procedural Logic

- `fact_extractor.py`
  - Extracts structured facts from user query:
  - date, amount, incident type, party type, domain hints, etc.
  - Supports LLM extraction with heuristic fallback path.

- `statutory_checks.py`
  - Performs statutory/procedural checks such as limitation windows.
  - Adds legal-process constraints before final response.

- `jurisdiction_validator.py`
  - Computes likely filing forum from claim amount/domain rules.
  - Used for consumer forum guidance (district/state/national style outputs).

## Evaluation and Testing

- `run_eval.py`
  - Runs benchmark scenarios from `eval_cases.json`.
  - Produces report output in `eval_report.json`.

- `eval_cases.json`
  - Evaluation test cases/questions.

- `eval_report.json`
  - Most recent evaluation output report.

- `test_import.py`
  - Basic import/module smoke test utility.

- `validate_acts.py`
  - Consistency checks for acts data quality/format.

## Data and Indexes

- `JSON_acts/`
  - Canonical structured legal act JSON files.
  - Embedding rebuild input source for acts corpus.

- `txt_acts/`
  - Text representations of acts, used as source/support files.

- `embeddings_acts/`
  - Built retrieval assets for acts:
  - `index.faiss`, `bm25.db`, `metadata.json`.

- `embeddings_judgements/`
  - Built retrieval assets for judgments:
  - `index.faiss`, `bm25.db`, `metadata.json`.

## Frontend

- `ui/src/components/LegalChat.tsx`
  - Main chat component for current frontend experience.
  - This is the focus frontend component currently used for app interaction.

- `ui/`
  - Vite + React app with TypeScript.
  - Handles user input, API calls, and answer rendering.

## Dependency and Build Files

- `requirements.txt`
  - Python runtime dependencies.

- `ui/package.json`
  - Frontend scripts and JS dependencies.

## Documentation Files

- `README.md`
  - Product-level overview and architecture summary.

- `INSTALL.md`
  - Setup, run, and troubleshooting guide.

- `CHANGE_HISTORY.md`
  - Plain-English historical log of changes by date.

## How to Maintain This Descriptor

When new files/modules are added:

1. Add the file path in the correct section.
2. Add 1-3 bullets explaining purpose and role.
3. Mention inputs/outputs only if they materially affect architecture.
