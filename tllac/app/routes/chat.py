"""
Chat route for the new LLM-only TLLAC flow.

Request:
  { "query": "..." }

Response:
  { "response": "..." }
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import logging

from ..services.bedrock_llm_service import generate_response
from ..services.validation_service import validate_query

logger = logging.getLogger("tllac.routes.chat")
logging.basicConfig(level=logging.INFO)

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=2,
        max_length=4000,
        description="The user's legal query.",
    )


class ChatResponse(BaseModel):
    response: str = Field(..., description="LLM response or fallback message.")


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    LLM-only chat endpoint for the new UI.
    """
    query = request.query.strip()
    logger.info("Incoming query: %s", query[:120])

    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    is_valid, fallback_message = validate_query(query)
    if not is_valid:
        return ChatResponse(response=fallback_message)

    response_text = generate_response(query)
    if not response_text:
        response_text = "The legal language model did not return a response."

    logger.info("Generated LLM-only response (%d chars).", len(response_text))
    return ChatResponse(response=response_text)
