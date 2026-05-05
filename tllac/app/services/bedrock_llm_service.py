"""
Direct Bedrock invoke_model service for the new TLLAC chat flow.

This intentionally follows the same pattern as the user's working
Mistral reference:
load env -> initialize boto3 client -> send prompt -> parse text response.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from ..utils.prompt_builder import get_system_prompt


_REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_REPO_ROOT / ".env")
load_dotenv(_REPO_ROOT / "tllac" / ".env")


def _resolve_model_id() -> str:
    return (
        os.getenv("MODEL_ID")
        or os.getenv("TLLAC_MODEL_ID")
        or os.getenv("LEGAL_MODEL_ID")
        or os.getenv("BEDROCK_MODEL_ID")
        or os.getenv("BEDROCK_MODEL")
        or "mistral.mistral-7b-instruct-v0:2"
    )


def _build_prompt(user_question: str) -> str:
    system_prompt = get_system_prompt().strip()
    user_question = user_question.strip()
    return f"<s>[INST] {system_prompt}\n\nUser Query: {user_question} [/INST]"


def _build_bedrock_client():
    region = os.getenv("AWS_REGION") or os.getenv("BEDROCK_REGION")
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    session_token = os.getenv("AWS_SESSION_TOKEN")
    profile = os.getenv("AWS_PROFILE")

    client_kwargs = {}
    if region:
        client_kwargs["region_name"] = region

    # Prefer the host system's default AWS credential chain whenever
    # explicit credentials are not provided in the process environment.
    if access_key and secret_key:
        client_kwargs["aws_access_key_id"] = access_key
        client_kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            client_kwargs["aws_session_token"] = session_token
        return boto3.client("bedrock-runtime", **client_kwargs)

    if profile:
        session = boto3.session.Session(profile_name=profile, region_name=region)
        return session.client("bedrock-runtime")

    return boto3.client("bedrock-runtime", **client_kwargs)


def _extract_text(response_body: dict) -> str:
    if "outputs" in response_body and response_body["outputs"]:
        return str(response_body["outputs"][0].get("text", "")).strip()
    if "generation" in response_body:
        return str(response_body["generation"]).strip()
    if "text" in response_body:
        return str(response_body["text"]).strip()
    if "completion" in response_body:
        return str(response_body["completion"]).strip()
    return ""


def generate_response(user_question: str) -> str:
    """
    Send the user question directly to the configured Bedrock model.
    """
    print("Initializing Bedrock client...")
    try:
        client = _build_bedrock_client()

        model_id = _resolve_model_id()
        print(f"Using model: {model_id}")
        request_body = json.dumps(
            {
                "prompt": _build_prompt(user_question),
                "max_tokens": int(os.getenv("MAX_TOKENS", "1000")),
                "temperature": float(os.getenv("TEMPERATURE", "0.7")),
                "top_p": float(os.getenv("TOP_P", "0.9")),
                "top_k": int(os.getenv("TOP_K", "50")),
            }
        )

        print("Sending request to Bedrock...")
        response = client.invoke_model(
            modelId=model_id,
            body=request_body,
        )
        print("Response received!")
        response_body = json.loads(response["body"].read())
        print(f"Response structure: {list(response_body.keys())}")
        text = _extract_text(response_body)
        return text or json.dumps(response_body, indent=2)
    except ClientError as exc:
        return f"AWS Client Error: {exc}"
    except Exception as exc:
        return f"Error: {exc}"
