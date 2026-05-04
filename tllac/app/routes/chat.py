"""
Chat Route — POST /chat
========================
Accepts a user query and returns an Indian-law-scoped response.

Request :  { "query": "What is adverse possession in India?" }
Response:  { "response": "..." }
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import json
import os
import logging
from typing import Optional

from ..services.validation_service import validate_query
from ..services.llm_service import generate_response

# ──────────────────────────────────────────────
# Logger
# ──────────────────────────────────────────────
logger = logging.getLogger("tllac.routes.chat")
logging.basicConfig(level=logging.INFO)

# ──────────────────────────────────────────────
# Router
# ──────────────────────────────────────────────
router = APIRouter(tags=["chat"])

# ──────────────────────────────────────────────
# Request / Response Models
# ──────────────────────────────────────────────
class ChatRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=2,
        max_length=1000,
        description="The user's legal query (must relate to Indian law).",
        examples=["What is adverse possession in India?"],
    )

class ChatResponse(BaseModel):
    response: str = Field(
        ...,
        description="Structured legal answer or fallback message.",
    )

# ──────────────────────────────────────────────
# Load trained data once at module level
# ──────────────────────────────────────────────
_DATA_PATH = os.path.join(
    os.path.dirname(__file__), os.pardir, "data", "trained_data.json"
)

try:
    with open(os.path.normpath(_DATA_PATH), "r", encoding="utf-8") as fh:
        TRAINED_DATA: dict = json.load(fh)
    logger.info("✅ Trained data loaded — %d topics available.", len(TRAINED_DATA))
except FileNotFoundError:
    logger.error("❌ trained_data.json not found at %s", _DATA_PATH)
    TRAINED_DATA = {}
except json.JSONDecodeError as exc:
    logger.error("❌ Malformed trained_data.json: %s", exc)
    TRAINED_DATA = {}


# ──────────────────────────────────────────────
# Endpoint
# ──────────────────────────────────────────────
@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Main chat endpoint.

    Pipeline:
      1. Validate that the query relates to Indian law.
      2. Attempt to match against trained data.
      3. Generate a structured response or return a fallback.
    """
    query = request.query.strip()
    logger.info("📩 Incoming query: %s", query[:80])

    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    # ── Validation pipeline ──────────────────
    is_valid, fallback_message, matched_data = validate_query(query, TRAINED_DATA)

    if not is_valid:
        logger.info("⚠️  Validation failed — returning fallback.")
        return ChatResponse(response=fallback_message)

    # ── Generate response ────────────────────
    response_text = generate_response(query, matched_data)
    logger.info("✅ Response generated (%d chars).", len(response_text))

    return ChatResponse(response=response_text)
