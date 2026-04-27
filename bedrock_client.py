import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    PartialCredentialsError,
)


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
                # Runtime environment should win over .env so production/test servers
                # can inject credentials without changing application code.
                if key and key not in os.environ:
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


def _get_guardrail_config() -> Optional[Dict[str, str]]:
    identifier = os.getenv("BEDROCK_GUARDRAIL_IDENTIFIER", "").strip()
    version = os.getenv("BEDROCK_GUARDRAIL_VERSION", "").strip()
    if not identifier and not version:
        return None
    if not identifier or not version:
        raise ValueError(
            "Bedrock guardrail config is incomplete. Set both "
            "BEDROCK_GUARDRAIL_IDENTIFIER and BEDROCK_GUARDRAIL_VERSION."
        )
    return {
        "guardrailIdentifier": identifier,
        "guardrailVersion": version,
    }


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


def _current_region() -> Optional[str]:
    return os.getenv(
        "BEDROCK_REGION",
        os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION")),
    )


def _credential_hint(session: boto3.session.Session, assumed_role: bool = False) -> str:
    if assumed_role:
        return "assume-role"
    credentials = session.get_credentials()
    method = getattr(credentials, "method", None) if credentials is not None else None
    return str(method or "unknown")


def _build_bedrock_session(region_name: str) -> Tuple[boto3.session.Session, str]:
    session_kwargs: Dict[str, str] = {}
    if region_name:
        session_kwargs["region_name"] = region_name
    profile_name = (os.getenv("BEDROCK_AWS_PROFILE") or os.getenv("AWS_PROFILE") or "").strip()
    if profile_name:
        session_kwargs["profile_name"] = profile_name

    # Use AWS default credential provider chain (env vars, EC2 IAM role, ECS task
    # role, web identity, shared config, etc.). No static secrets in code.
    session = boto3.session.Session(**session_kwargs)
    assume_role_arn = (os.getenv("BEDROCK_ASSUME_ROLE_ARN") or "").strip()
    if not assume_role_arn:
        return session, _credential_hint(session)

    sts = session.client("sts", region_name=region_name or _current_region())
    assume_role_request: Dict[str, Any] = {
        "RoleArn": assume_role_arn,
        "RoleSessionName": os.getenv(
            "BEDROCK_ASSUME_ROLE_SESSION_NAME",
            "lawllm-bedrock-session",
        ),
    }
    external_id = (os.getenv("BEDROCK_ASSUME_ROLE_EXTERNAL_ID") or "").strip()
    if external_id:
        assume_role_request["ExternalId"] = external_id

    response = sts.assume_role(**assume_role_request)
    credentials = (response or {}).get("Credentials") or {}
    assumed_session = boto3.session.Session(
        aws_access_key_id=credentials.get("AccessKeyId"),
        aws_secret_access_key=credentials.get("SecretAccessKey"),
        aws_session_token=credentials.get("SessionToken"),
        region_name=region_name,
    )
    return assumed_session, _credential_hint(assumed_session, assumed_role=True)


@lru_cache(maxsize=6)
def _get_bedrock_runtime(region_name: str) -> Tuple[Any, str]:
    session, credential_source = _build_bedrock_session(region_name)

    read_timeout = int(os.getenv("BEDROCK_READ_TIMEOUT_SEC", "30"))
    connect_timeout = int(os.getenv("BEDROCK_CONNECT_TIMEOUT_SEC", "10"))
    retries = int(os.getenv("BEDROCK_MAX_RETRIES", "10"))

    cfg = Config(
        read_timeout=read_timeout,
        connect_timeout=connect_timeout,
        retries={"max_attempts": retries, "mode": "standard"},
    )
    return session.client("bedrock-runtime", config=cfg), credential_source


def _format_bedrock_credentials_error(region: Optional[str], model_id: Optional[str]) -> str:
    return (
        "[ERROR] AWS Bedrock credentials were not found. "
        f"region={region or 'unset'} model={model_id or 'unset'}. "
        "Use one of these setup paths without changing code: "
        "attach an IAM role to the server, set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY"
        " (and AWS_SESSION_TOKEN if needed), set AWS_PROFILE, or set "
        "BEDROCK_ASSUME_ROLE_ARN."
    )


def _format_bedrock_client_error(error: ClientError, region: Optional[str], model_id: Optional[str]) -> str:
    code = str(((error.response or {}).get("Error") or {}).get("Code") or "")
    message = str(((error.response or {}).get("Error") or {}).get("Message") or str(error))
    if code in {"AccessDeniedException", "UnrecognizedClientException", "InvalidSignatureException"}:
        return (
            "[ERROR] AWS Bedrock access was denied. "
            f"region={region or 'unset'} model={model_id or 'unset'} code={code}. "
            "Check IAM permissions, model access for this region, and whether the test "
            "server is using the intended AWS credentials or role. "
            f"Details: {message}"
        )
    return f"[ERROR] AWS Bedrock call failed: {message}"


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
    if not target_model:
        return (
            "[ERROR] No Bedrock model configured. Set LEGAL_MODEL_ID, BEDROCK_MODEL_ID, "
            "or BEDROCK_MODEL."
        )
    
    # Phase 26: Cross-Region Inference Support
    # US inference profiles (us.*) require calling us-east-1 or us-west-2.
    # We auto-switch to us-east-1 for us.* models unless user explicitly sets BEDROCK_REGION.
    region = _current_region() or DEFAULT_REGION
    if target_model.startswith("us.") and not os.getenv("BEDROCK_REGION"):
        region = "us-east-1"

    profile = os.getenv("AWS_PROFILE", "")
    credential_source = "unknown"

    normalized_messages = _normalize_messages(messages)
    # Global hard cap requested for output size. Claude 3.5 Sonnet needs more than 1000.
    effective_max_tokens = min(int(max_tokens), 4096)
    if not normalized_messages:
        return "[ERROR] No valid message content provided."
    try:
        client, credential_source = _get_bedrock_runtime(region or "")
        guardrail_config = _get_guardrail_config()
    except Exception as e:
        return f"[ERROR] Unable to initialize Bedrock client in {region}: {str(e)}"

    print(
        f"[BEDROCK] Attempting call to {target_model} in {region} "
        f"(profile={profile or 'default'}, auth={credential_source})..."
    )

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
        if guardrail_config:
            req["guardrailConfig"] = guardrail_config
        response = client.converse(**req)
        text = _extract_converse_text(response)
        return text or "[ERROR] Bedrock returned an empty response."
    except (NoCredentialsError, PartialCredentialsError):
        return _format_bedrock_credentials_error(region, target_model)
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
                    invoke_request: Dict[str, Any] = {
                        "modelId": target_model,
                        "contentType": "application/json",
                        "accept": "application/json",
                        "body": json.dumps(invoke_body).encode("utf-8"),
                    }
                    if guardrail_config:
                        invoke_request.update(guardrail_config)
                    response = client.invoke_model(**invoke_request)
                    body = response.get("body")
                    raw = body.read() if body is not None else b"{}"
                    payload = json.loads(raw.decode("utf-8"))
                    text = _extract_invoke_text(payload)
                    return text or "[ERROR] Bedrock returned an empty response."
                except (NoCredentialsError, PartialCredentialsError):
                    return _format_bedrock_credentials_error(region, target_model)
                except ClientError as ce:
                    code = str(((ce.response or {}).get("Error") or {}).get("Code") or "")
                    last_error = ce
                    if code != "ValidationException":
                        raise
                except BotoCoreError as be:
                    last_error = be
                except Exception as e:
                    last_error = e
            if isinstance(last_error, ClientError):
                return _format_bedrock_client_error(last_error, region, target_model)
            return f"[ERROR] AWS Bedrock call failed: {str(last_error)}"
        except Exception as e:
            if isinstance(e, ClientError):
                return _format_bedrock_client_error(e, region, target_model)
            return f"[ERROR] AWS Bedrock call failed: {str(e)}"
    except ClientError as e:
        return _format_bedrock_client_error(e, region, target_model)
    except Exception as e:
        return f"[ERROR] AWS Bedrock call failed: {str(e)}"
