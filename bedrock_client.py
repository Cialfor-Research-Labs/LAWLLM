import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


def _load_local_env(env_path: str = ".env") -> None:
    """Minimal .env loader (no external dependency required)."""
    try:
        if not os.path.isfile(env_path):
            return
        with open(env_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                # Phase 27: Absolute Priority for .env file.
                # Overwrite existing environment variables to ensure .env is Source of Truth.
                if key:
                    os.environ[key] = value
    except Exception:
        # Do not crash startup because of malformed .env.
        return


_load_local_env()


DEFAULT_BEDROCK_MODEL_ID = os.getenv(
    "LEGAL_MODEL_ID",
    os.getenv(
        "BEDROCK_MODEL_ID",
        os.getenv(
            "BEDROCK_MODEL"
        ),
    ),
)
DEFAULT_REGION = os.getenv(
    "BEDROCK_REGION",
    os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION")),
)


def _as_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)
    return str(content)


def _normalize_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for msg in messages or []:
        role = str(msg.get("role", "user")).strip().lower()
        if role not in {"user", "assistant"}:
            role = "user"
        text = _as_text(msg.get("content", ""))
        if not text.strip():
            continue
        normalized.append({"role": role, "content": [{"text": text}]})
    return normalized


@lru_cache(maxsize=6)
def _get_bedrock_client(region_name: str) -> Any:
    session_kwargs: Dict[str, str] = {}
    if region_name:
        session_kwargs["region_name"] = region_name
    # Use AWS default credential provider chain (EC2 IAM role, ECS task role,
    # web identity, shared config, etc.). No static secrets in code.
    session = boto3.session.Session(**session_kwargs)

    read_timeout = int(os.getenv("BEDROCK_READ_TIMEOUT_SEC", "300"))
    connect_timeout = int(os.getenv("BEDROCK_CONNECT_TIMEOUT_SEC", "100"))
    retries = int(os.getenv("BEDROCK_MAX_RETRIES", "100"))
    cfg = Config(
        read_timeout=read_timeout,
        connect_timeout=connect_timeout,
        retries={"max_attempts": retries, "mode": "standard"},
    )
    return session.client("bedrock-runtime", config=cfg)


def _extract_converse_text(response: Dict[str, Any]) -> str:
    content = (((response or {}).get("output") or {}).get("message") or {}).get("content", [])
    parts: List[str] = []
    for item in content:
        if isinstance(item, dict) and "text" in item:
            parts.append(str(item["text"]))
    return "\n".join(p for p in parts if p).strip()


def _extract_invoke_text(payload: Dict[str, Any]) -> str:
    """Extract text from common Bedrock invoke_model response shapes."""
    content = payload.get("content")
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
        if parts:
            return "\n".join(parts).strip()

    outputs = payload.get("outputs")
    if isinstance(outputs, list) and len(outputs) > 0:
        return str(outputs[0].get("text", "")).strip()

    return str(payload.get("completion", "")).strip()


def _to_plain_prompt(messages: List[Dict[str, Any]], system_prompt: Optional[str]) -> str:
    parts: List[str] = []
    if system_prompt and system_prompt.strip():
        parts.append(f"System: {system_prompt.strip()}")
    for m in messages or []:
        text = _as_text(m.get("content", "")).strip()
        if not text:
            continue
        role = str(m.get("role", "user")).strip().lower()
        if role == "assistant":
            parts.append(f"Assistant: {text}")
        else:
            parts.append(f"User: {text}")
    # Keep the final assistant cue for generation.
    parts.append("Assistant:")
    return "\n\n".join(parts)


def _build_invoke_payloads(
    messages: List[Dict[str, Any]],
    system_prompt: Optional[str],
    temperature: float,
    top_p: float,
    max_tokens: int,
) -> List[Dict[str, Any]]:
    payloads: List[Dict[str, Any]] = [
        {
            "prompt": _to_plain_prompt(messages, system_prompt),
            "max_tokens": max_tokens,
            "temperature": float(temperature),
            "top_p": float(top_p),
        },
    ]
    return payloads


def call_bedrock_chat(
    messages: List[Dict[str, Any]],
    system_prompt: Optional[str] = None,
    model_id: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1000,
    top_p: float = 0.9,
) -> str:
    target_model = model_id or DEFAULT_BEDROCK_MODEL_ID
    
    # Phase 26: Cross-Region Inference Support
    # US inference profiles (us.*) require calling us-east-1 or us-west-2.
    # We auto-switch to us-east-1 for us.* models unless user explicitly sets BEDROCK_REGION.
    region = DEFAULT_REGION
    if target_model.startswith("us.") and not os.getenv("BEDROCK_REGION"):
        region = "us-east-1"

    profile = os.getenv("AWS_PROFILE", "")
    # Phase 27: Diagnostic Visibility
    print(f"[BEDROCK] Attempting call to {target_model} in {region} (profile={profile or 'default'})...")

    normalized_messages = _normalize_messages(messages)
    # Global hard cap requested for output size. Claude 3.5 Sonnet needs more than 1000.
    effective_max_tokens = min(int(max_tokens), 4096)
    if not normalized_messages:
        return "[ERROR] No valid message content provided."
    try:
        client = _get_bedrock_client(region)
    except Exception as e:
        return f"[ERROR] Unable to initialize Bedrock client in {region}: {str(e)}"

    try:
        req: Dict[str, Any] = {
            "modelId": target_model,
            "messages": normalized_messages,
            "inferenceConfig": {
                "temperature": float(temperature),
                "maxTokens": effective_max_tokens,
                "topP": float(top_p),
            },
        }
        if system_prompt and system_prompt.strip():
            req["system"] = [{"text": system_prompt.strip()}]
        response = client.converse(**req)
        text = _extract_converse_text(response)
        return text or "[ERROR] Bedrock returned an empty response."
    except (ClientError, BotoCoreError):
        try:
            payloads = _build_invoke_payloads(
                messages=messages,
                system_prompt=system_prompt,
                temperature=float(temperature),
                top_p=float(top_p),
                max_tokens=effective_max_tokens,
            )
            last_error: Optional[Exception] = None
            for invoke_body in payloads:
                try:
                    response = client.invoke_model(
                        modelId=target_model,
                        contentType="application/json",
                        accept="application/json",
                        body=json.dumps(invoke_body).encode("utf-8"),
                    )
                    body = response.get("body")
                    raw = body.read() if body is not None else b"{}"
                    payload = json.loads(raw.decode("utf-8"))
                    text = _extract_invoke_text(payload)
                    return text or "[ERROR] Bedrock returned an empty response."
                except ClientError as ce:
                    code = str(((ce.response or {}).get("Error") or {}).get("Code") or "")
                    last_error = ce
                    if code != "ValidationException":
                        raise
                except BotoCoreError as be:
                    last_error = be
                except Exception as e:
                    last_error = e
            return f"[ERROR] AWS Bedrock call failed: {str(last_error)}"
        except Exception as e:
            return f"[ERROR] AWS Bedrock call failed: {str(e)}"
    except Exception as e:
        return f"[ERROR] AWS Bedrock call failed: {str(e)}"
