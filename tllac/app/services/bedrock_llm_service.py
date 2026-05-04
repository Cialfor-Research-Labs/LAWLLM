"""
Direct Bedrock-backed LLM service for the new TLLAC chat flow.

Flow:
user query -> system prompt -> Bedrock model -> plain response
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List

from ..utils.prompt_builder import get_system_prompt


def _ensure_repo_root_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


def _load_env_file(env_path: Path) -> None:
    if not env_path.is_file():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        return


_ensure_repo_root_on_path()
_REPO_ROOT = Path(__file__).resolve().parents[3]
_load_env_file(_REPO_ROOT / ".env")
_load_env_file(_REPO_ROOT / "tllac" / ".env")

from bedrock_client import call_bedrock_chat, DEFAULT_BEDROCK_MODEL_ID  # noqa: E402


def _resolve_model_id() -> str:
    return (
        os.getenv("TLLAC_MODEL_ID")
        or os.getenv("LEGAL_MODEL_ID")
        or os.getenv("BEDROCK_MODEL_ID")
        or os.getenv("BEDROCK_MODEL")
        or DEFAULT_BEDROCK_MODEL_ID
        or ""
    )


def _build_messages(query: str) -> List[Dict[str, str]]:
    return [{"role": "user", "content": query.strip()}]


def generate_response(query: str) -> str:
    """
    Generate a direct LLM response from system prompt + user query only.
    """
    model_id = _resolve_model_id()
    if not model_id:
        return (
            "[ERROR] No Bedrock model ID is configured for TLLAC. "
            "Set TLLAC_MODEL_ID or BEDROCK_MODEL_ID in the environment."
        )

    messages = _build_messages(query)
    response = call_bedrock_chat(
        messages=messages,
        system_prompt=get_system_prompt(),
        model_id=model_id,
        temperature=0.2,
        max_tokens=1400,
        top_p=0.9,
    )
    return (response or "").strip()
