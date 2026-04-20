import json
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import subprocess
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Tuple

import psycopg
from fastapi import FastAPI, HTTPException, Body, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from answer_validator import validate_grounding
from context_builder import build_context_pack, load_acts_chunk_lookup, run_retrieval
from llama_legal_answer import call_llm, build_llm_prompt, get_model_and_tokenizer, rewrite_query, llm_rerank
from query_expansion import build_query
from bedrock_client import DEFAULT_BEDROCK_MODEL_ID

# 🔥 Security & Retrieval Engines
from dynamic_intake_engine import handle_query as handle_dynamic_intake
from deterministic_retrieval import search_sections, reconstruct_section, call_qwen as call_qwen_act, load_data as load_act_data, FULL_ACT_NAMES, is_explanation_query
from legal_router import classify_legal_issue, build_intent_route
from security_engine import is_valid_query, is_legal_query, validate_output, sanitize_user_input
from legal_heuristics import match_heuristics, format_heuristics_for_prompt, format_heuristics_for_debug
from legal_confidence import (
    compute_confidence, confidence_label, extract_citations, format_citations_for_prompt,
    validate_answer, build_refinement_prompt, build_confidence_rewrite_prompt,
    apply_confidence_styling, has_actionable_next_steps,
)
from legal_notice_engine import (
    NOTICE_TYPES, get_available_notice_types, auto_detect_notice_type,
    build_notice_prompt, build_refinement_prompt as build_notice_refinement_prompt,
    build_authority_appendix,
)
from legal_interview import (
    detect_issues, extract_facts as extract_facts_heuristic, select_questions, 
    generate_legal_output,
    compute_signal_strength, decide_next_step
)
from fact_extractor import extract_facts as extract_facts_llm
from case_model import CaseModel
from extractor_pipeline import run_case_extractor_pipeline
from legal_primitives import BehavioralPrimitive, LegalInterpretation, LegalBrain
from law_engine import ApplicableLaw, LawEngine
from bedrock_client import call_bedrock_chat
from phase65_engine import (
    analyze_interaction_logs,
    append_interaction_log,
    build_log_entry,
    choose_confirmation_question,
    contradiction_penalty as phase65_contradiction_penalty,
    derive_confirmed_tags,
    detect_contradictions,
    extract_signal_updates,
    merge_signal_state,
    normalize_user_confidence,
    rank_signal_questions,
    summarize_signal_state,
)


app = FastAPI(title="Legal AI API", version="2.5")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🧠 Session Storage
SESSIONS: Dict[str, List[Dict[str, str]]] = {}
LOG_PATH = os.path.join("logs", "query_logs.json")
DISABLE_EMBEDDING_RETRIEVAL = os.getenv("DISABLE_EMBEDDING_RETRIEVAL", "true").strip().lower() == "true"
USE_JUDGEMENT_EMBEDDINGS = os.getenv("USE_JUDGEMENT_EMBEDDINGS", "true").strip().lower() == "true"
# PHASE 1: Score thresholds disabled — no chunk is rejected due to score.
MIN_RETRIEVAL_SCORE = 0.0
MIN_ACCEPTABLE_RETRIEVAL_SCORE = 0.0
MAX_RETRIEVAL_QUERIES = int(os.getenv("MAX_RETRIEVAL_QUERIES", "5"))
DEFAULT_ALLOWED_DOCS = {"acts", "judgements"}
LAWYER_SESSIONS: Dict[str, Dict[str, Any]] = {}
INTERVIEW_SESSIONS: Dict[str, Dict[str, Any]] = {}
INTERACTION_LOG_PATH = os.path.join("test", "interaction_logs.jsonl")
MAX_INTERVIEW_TURNS = int(os.getenv("MAX_INTERVIEW_TURNS", "6"))
MAX_STAGNANT_TURNS = int(os.getenv("MAX_STAGNANT_TURNS", "2"))
MAX_PENDING_CONFIRMATION_RETRIES = int(os.getenv("MAX_PENDING_CONFIRMATION_RETRIES", "2"))

# Auth / Access control settings
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "24"))
PASSWORD_SETUP_TOKEN_TTL_HOURS = int(os.getenv("PASSWORD_SETUP_TOKEN_TTL_HOURS", "48"))
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")
PASSWORD_HASH_ITERATIONS = 120_000
MAILER_NODE_BIN = os.getenv("MAILER_NODE_BIN", "node")
MAILER_SCRIPT_PATH = os.getenv("MAILER_SCRIPT_PATH", os.path.join("ui", "scripts", "send_setup_email.cjs"))
CHAT_HISTORY_PROMPT_LIMIT = int(os.getenv("CHAT_HISTORY_PROMPT_LIMIT", "24"))
CHAT_HISTORY_DETAIL_LIMIT = int(os.getenv("CHAT_HISTORY_DETAIL_LIMIT", "200"))
CHAT_HISTORY_LIST_LIMIT = int(os.getenv("CHAT_HISTORY_LIST_LIMIT", "50"))
ADMIN_MONITORING_DEFAULT_DAYS = int(os.getenv("ADMIN_MONITORING_DEFAULT_DAYS", "7"))
ADMIN_MONITORING_DEFAULT_LIMIT = int(os.getenv("ADMIN_MONITORING_DEFAULT_LIMIT", "25"))
ADMIN_MONITORING_MAX_LIMIT = int(os.getenv("ADMIN_MONITORING_MAX_LIMIT", "200"))
ADMIN_MONITORING_TOP_IP_LIMIT = int(os.getenv("ADMIN_MONITORING_TOP_IP_LIMIT", "10"))
_DOTENV_CACHE: Optional[Dict[str, str]] = None


def _load_dotenv_cache() -> Dict[str, str]:
    global _DOTENV_CACHE
    if _DOTENV_CACHE is not None:
        return _DOTENV_CACHE

    parsed: Dict[str, str] = {}
    env_path = ".env"
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    parsed[key.strip()] = val.strip()
        except Exception:
            parsed = {}
    _DOTENV_CACHE = parsed
    return parsed


def _get_env_with_dotenv_fallback(key: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(key)
    if value is not None:
        return value
    return _load_dotenv_cache().get(key, default)


def _send_setup_link_email(recipient_email: str, recipient_name: str, setup_url: str) -> None:
    smtp_host = (_get_env_with_dotenv_fallback("SMTP_HOST", "") or "").strip()
    smtp_port = (_get_env_with_dotenv_fallback("SMTP_PORT", "587") or "587").strip()
    smtp_user = (_get_env_with_dotenv_fallback("SMTP_USER", "") or "").strip()
    smtp_pass = (_get_env_with_dotenv_fallback("SMTP_PASS", "") or "").strip()
    smtp_from = (_get_env_with_dotenv_fallback("SMTP_FROM", smtp_user) or "").strip()
    smtp_secure = (_get_env_with_dotenv_fallback("SMTP_SECURE", "false") or "false").strip().lower()

    missing = []
    if not smtp_host:
        missing.append("SMTP_HOST")
    if not smtp_user:
        missing.append("SMTP_USER")
    if not smtp_pass:
        missing.append("SMTP_PASS")
    if not smtp_from:
        missing.append("SMTP_FROM")
    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"Email configuration missing: {', '.join(missing)}",
        )

    script_abs = os.path.abspath(MAILER_SCRIPT_PATH)
    script_dir = os.path.dirname(script_abs)
    script_file = os.path.basename(script_abs)
    if not os.path.exists(script_abs):
        raise HTTPException(status_code=500, detail=f"Mailer script not found: {script_abs}")

    env = os.environ.copy()
    env.update(
        {
            "SMTP_HOST": smtp_host,
            "SMTP_PORT": smtp_port,
            "SMTP_USER": smtp_user,
            "SMTP_PASS": smtp_pass,
            "SMTP_FROM": smtp_from,
            "SMTP_SECURE": smtp_secure,
        }
    )

    proc = subprocess.run(
        [MAILER_NODE_BIN, script_file, recipient_email, recipient_name or "User", setup_url],
        cwd=script_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "").strip()
        raise HTTPException(status_code=500, detail=f"Failed to send setup email: {stderr or 'unknown error'}")

DOMAIN_FORBIDDEN_QUESTION_TERMS: Dict[str, List[str]] = {
    "labour": ["landlord", "rent", "property"],
}

DOMAIN_ALLOWED_VOCABULARY: Dict[str, List[str]] = {
    "labour": ["employee", "employer", "salary", "wages", "termination", "contract", "labour court"],
}

INDIAN_STATE_TERMS = [
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh", "goa",
    "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka", "kerala",
    "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram", "nagaland",
    "odisha", "orissa", "punjab", "rajasthan", "sikkim", "tamil nadu", "telangana",
    "tripura", "uttar pradesh", "uttarakhand", "west bengal", "delhi", "new delhi",
    "jammu and kashmir", "ladakh", "puducherry", "pondicherry", "chandigarh",
    "andaman and nicobar", "dadra and nagar haveli", "daman and diu", "lakshadweep",
]

GENERIC_STATE_RENT_HINTS = [
    "delhi rent act",
    "maharashtra rent control act",
    "tamil nadu regulation of rights and responsibilities of landlords and tenants act",
    "karnataka rent act",
    "west bengal premises tenancy act",
    "state rent act",
    "rent control act",
]

# =========================
# REQUEST / RESPONSE MODELS
# =========================

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=2)
    mode: str = "lawyer_case"  # "lawyer_case" (default) or "query_act"; "understand_case" kept as alias
    llm_model: str = DEFAULT_BEDROCK_MODEL_ID
    llm_timeout_sec: int = 300
    session_id: Optional[str] = None
    reset_session: bool = False
    debug: bool = False

class QueryResponse(BaseModel):
    ok: bool
    query: str
    answer: str
    reasoning: List[str] = [] 
    citations: List[Dict[str, Any]]
    context_blocks: List[Dict[str, Any]]
    applicable_laws: List[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    confidence_label: Optional[str] = None
    meta: Dict[str, Any]


class UserModeResponse(BaseModel):
    ok: bool
    query: str
    summary: str
    what_you_can_do: List[str]
    legal_options: List[str]
    notes: str
    meta: Dict[str, Any] = {}


class LawyerInitRequest(BaseModel):
    query: str = Field(..., min_length=2)
    llm_model: str = DEFAULT_BEDROCK_MODEL_ID
    llm_timeout_sec: int = 300
    session_id: Optional[str] = None
    reset_session: bool = False
    debug: bool = False


class LawyerRefineRequest(BaseModel):
    session_id: str = Field(..., min_length=3)
    answers: Dict[str, str] = Field(default_factory=dict)
    llm_model: str = DEFAULT_BEDROCK_MODEL_ID
    llm_timeout_sec: int = 300
    debug: bool = False


class LawyerModeResponse(BaseModel):
    ok: bool
    session_id: str
    facts: str
    issues: List[str]
    legal_pathways: List[Dict[str, Any]]
    questions: List[Dict[str, Any]]
    final_analysis: Optional[Dict[str, Any]] = None
    meta: Dict[str, Any] = {}


class RequestAccessRequest(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    email: str = Field(..., min_length=5)
    organization: str = Field(..., min_length=1)
    use_case: str = Field(..., min_length=5)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5)
    password: str = Field("", min_length=0)


class SetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=8)
    new_password: str = Field(..., min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


class UpdateProfileRequest(BaseModel):
    name: str = Field(..., min_length=2)
    organization: str = Field("", min_length=0)
    use_case: str = Field("", min_length=0)
    advocate_address: str = Field(..., min_length=5)
    advocate_mobile: str = Field(..., min_length=8)


class AccessUpdateRequest(BaseModel):
    status: Literal["pending", "granted", "denied"]
    access_granted: bool
    review_notes: str = ""


class AuthUserView(BaseModel):
    id: int
    name: str
    email: str
    organization: str = ""
    use_case: str = ""
    advocate_address: str = ""
    advocate_mobile: str = ""
    role: str
    status: str
    access_granted: bool
    created_at: str
    updated_at: str


class RequestAccessResponse(BaseModel):
    ok: bool
    message: str


class LoginResponse(BaseModel):
    ok: bool
    state: str
    message: str
    token: Optional[str] = None
    user: Optional[AuthUserView] = None


class MeResponse(BaseModel):
    ok: bool
    user: AuthUserView


class AuthUserUpdateResponse(BaseModel):
    ok: bool
    message: str
    user: AuthUserView


class LogoutResponse(BaseModel):
    ok: bool
    message: str


class AdminAccessListResponse(BaseModel):
    ok: bool
    users: List[Dict[str, Any]]
    requests: List[Dict[str, Any]]


class AdminAccessUpdateResponse(BaseModel):
    ok: bool
    message: str
    user: Dict[str, Any]


class PasswordSetupLinkResponse(BaseModel):
    ok: bool
    setup_url: str
    expires_at: str


class AccessEventView(BaseModel):
    id: int
    occurred_at: str
    ip_address: str
    forwarded_for: str = ""
    real_ip: str = ""
    method: str
    path: str
    status_code: int
    outcome: Literal["success", "client_error", "server_error"]
    user_agent: str = ""
    referer: str = ""
    origin: str = ""
    query_string_present: bool = False
    user_id: Optional[int] = None
    user_email: str = ""
    user_role: str = ""
    session_id: Optional[int] = None
    is_authenticated: bool = False


class AccessEventSummary(BaseModel):
    total: int = 0
    unique_ips: int = 0
    authenticated: int = 0
    anonymous: int = 0
    failed: int = 0


class TopIpView(BaseModel):
    ip_address: str
    hit_count: int
    last_seen_at: str


class AdminAccessMonitoringResponse(BaseModel):
    ok: bool
    events: List[AccessEventView]
    summary: AccessEventSummary
    top_ips: List[TopIpView]
    limit: int
    offset: int
    has_more: bool


class ChatSessionSummary(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str
    last_message_at: str
    message_count: int
    preview: str = ""


class ChatMessageView(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: str


class ChatSessionListResponse(BaseModel):
    ok: bool
    sessions: List[ChatSessionSummary]


class ChatSessionDetailResponse(BaseModel):
    ok: bool
    session: ChatSessionSummary
    messages: List[ChatMessageView]


class ChatSessionRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


class ChatSessionMutationResponse(BaseModel):
    ok: bool
    message: str


# =====================================================
# PHASE 2/3 INTERVIEW MODELS
# =====================================================

class InterviewChatRequest(BaseModel):
    session_id: Optional[str] = None
    query: str = Field(..., min_length=2)
    llm_model: str = DEFAULT_BEDROCK_MODEL_ID
    # Optional field for when the user confirms/edits the extracted case model
    case_model_update: Optional[CaseModel] = None

class LegalOutput(BaseModel):
    analysis: str
    summary: str
    severity: str = "medium"
    applicable_laws: List[str]
    legal_options: List[str]
    next_steps: List[str]
    confidence: float
    notice_draft: Optional[str] = None
    case_strategy: List[str] = []
    evidence_checklist: List[str] = []
    
    model_config = {"extra": "ignore"}

class InterviewChatResponse(BaseModel):
    ok: bool = True
    session_id: str
    issue: str
    secondary_issues: List[str] = []
    confidence: float
    status: str = "interviewing" # "interviewing", "clarification_required", "complete", "review_required"
    is_complete: bool
    questions: List[str]
    legal_output: Optional[LegalOutput] = None
    case_model: Optional[CaseModel] = None
    behavioral_primitives: List[BehavioralPrimitive] = []
    interpretations: List[LegalInterpretation] = []
    applicable_laws: List[ApplicableLaw] = []
    state_debug: Dict[str, Any]


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _utc_iso_after_hours(hours: int) -> str:
    return (datetime.utcnow() + timedelta(hours=hours)).replace(microsecond=0).isoformat() + "Z"


def _utc_iso_days_ago(days: int) -> str:
    return (datetime.utcnow() - timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"


AuthRow = Mapping[str, Any]


def _translate_auth_sql(query: str) -> str:
    return query.replace("?", "%s")


class _AuthCursor:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount or 0)

    def fetchone(self) -> Optional[AuthRow]:
        return self._cursor.fetchone()

    def fetchall(self) -> List[AuthRow]:
        return list(self._cursor.fetchall())


class _AuthCursorResult:
    def __init__(self, rowcount: int = 0) -> None:
        self.rowcount = rowcount

    def fetchone(self) -> Optional[AuthRow]:
        return None

    def fetchall(self) -> List[AuthRow]:
        return []


class _AuthConnection:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def __enter__(self) -> "_AuthConnection":
        self._conn.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return bool(self._conn.__exit__(exc_type, exc, tb))

    def execute(self, query: str, params: Sequence[Any] = ()) -> _AuthCursor:
        return _AuthCursor(self._conn.execute(_translate_auth_sql(query), params))

    def executemany(self, query: str, params_seq: Sequence[Sequence[Any]]) -> _AuthCursor:
        translated = _translate_auth_sql(query)
        with self._conn.cursor() as cur:
            cur.executemany(translated, params_seq)
            rowcount = int(cur.rowcount or 0)
        return _AuthCursor(_AuthCursorResult(rowcount))

    def commit(self) -> None:
        self._conn.commit()


def _db_conn() -> _AuthConnection:
    dsn = (_get_env_with_dotenv_fallback("AUTH_DB_DSN", "") or "").strip()
    if dsn:
        return _AuthConnection(psycopg.connect(dsn, row_factory=dict_row))

    host = (_get_env_with_dotenv_fallback("AUTH_DB_HOST", "") or "").strip()
    port = (_get_env_with_dotenv_fallback("AUTH_DB_PORT", "5432") or "5432").strip()
    dbname = (_get_env_with_dotenv_fallback("AUTH_DB_NAME", "") or "").strip()
    user = (_get_env_with_dotenv_fallback("AUTH_DB_USER", "") or "").strip()
    password = _get_env_with_dotenv_fallback("AUTH_DB_PASSWORD", "")
    sslmode = (_get_env_with_dotenv_fallback("AUTH_DB_SSLMODE", "prefer") or "prefer").strip()

    missing = [
        key
        for key, value in (
            ("AUTH_DB_HOST", host),
            ("AUTH_DB_NAME", dbname),
            ("AUTH_DB_USER", user),
            ("AUTH_DB_PASSWORD", password),
        )
        if not str(value or "").strip()
    ]
    if missing:
        raise RuntimeError(
            "Missing PostgreSQL auth DB config. Set AUTH_DB_DSN or "
            + ", ".join(missing)
            + "."
        )

    return _AuthConnection(
        psycopg.connect(
            host=host,
            port=int(port),
            dbname=dbname,
            user=user,
            password=password,
            sslmode=sslmode,
            row_factory=dict_row,
        )
    )


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS)
    return (
        f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}$"
        f"{salt.hex()}${digest.hex()}"
    )


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iter_str, salt_hex, digest_hex = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _row_to_user_view(row: AuthRow) -> Dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "email": row["email"],
        "organization": row["organization"] or "",
        "use_case": row["use_case"] or "",
        "advocate_address": row["advocate_address"] or "",
        "advocate_mobile": row["advocate_mobile"] or "",
        "role": row["role"],
        "status": row["status"],
        "access_granted": bool(row["access_granted"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _ensure_auth_schema() -> None:
    with _db_conn() as conn:
        for statement in (
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                organization TEXT NOT NULL DEFAULT '',
                use_case TEXT NOT NULL DEFAULT '',
                advocate_address TEXT NOT NULL DEFAULT '',
                advocate_mobile TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
                status TEXT NOT NULL CHECK (status IN ('pending', 'granted', 'denied')),
                access_granted BOOLEAN NOT NULL DEFAULT FALSE,
                password_hash TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_single_admin_role
            ON users(role) WHERE role = 'admin'
            """,
            """
            CREATE TABLE IF NOT EXISTS access_requests (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                organization TEXT NOT NULL DEFAULT '',
                use_case TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK (status IN ('pending', 'granted', 'denied')),
                reviewed_by INTEGER,
                review_notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(reviewed_by) REFERENCES users(id) ON DELETE SET NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS password_setup_tokens (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                used BOOLEAN NOT NULL DEFAULT FALSE,
                created_by_admin_id INTEGER,
                created_at TEXT NOT NULL,
                used_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(created_by_admin_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                revoked BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_message_at TEXT NOT NULL,
                archived BOOLEAN NOT NULL DEFAULT FALSE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_last
            ON chat_sessions(user_id, last_message_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id
            ON chat_messages(session_id, id)
            """,
            """
            CREATE TABLE IF NOT EXISTS access_events (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                occurred_at TEXT NOT NULL,
                ip_address TEXT NOT NULL DEFAULT '',
                forwarded_for TEXT NOT NULL DEFAULT '',
                real_ip TEXT NOT NULL DEFAULT '',
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                outcome TEXT NOT NULL CHECK (outcome IN ('success', 'client_error', 'server_error')),
                user_agent TEXT NOT NULL DEFAULT '',
                referer TEXT NOT NULL DEFAULT '',
                origin TEXT NOT NULL DEFAULT '',
                query_string_present BOOLEAN NOT NULL DEFAULT FALSE,
                user_id INTEGER,
                user_email TEXT NOT NULL DEFAULT '',
                user_role TEXT NOT NULL DEFAULT '',
                session_id INTEGER,
                is_authenticated BOOLEAN NOT NULL DEFAULT FALSE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_access_events_occurred_at_desc
            ON access_events(occurred_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_access_events_ip_address
            ON access_events(ip_address)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_access_events_user_id
            ON access_events(user_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_access_events_path
            ON access_events(path)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_access_events_status_occurred
            ON access_events(status_code, occurred_at DESC)
            """,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS advocate_address TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS advocate_mobile TEXT NOT NULL DEFAULT ''",
        ):
            conn.execute(statement)
        conn.commit()


def _bootstrap_single_admin() -> None:
    admin_email = (_get_env_with_dotenv_fallback("ADMIN_EMAIL", "") or "").strip().lower()
    admin_name = (_get_env_with_dotenv_fallback("ADMIN_NAME", "System Admin") or "System Admin").strip() or "System Admin"
    admin_password = _get_env_with_dotenv_fallback("ADMIN_PASSWORD")
    admin_setup_token = (_get_env_with_dotenv_fallback("ADMIN_SETUP_TOKEN", "") or "").strip()

    if not admin_email:
        raise RuntimeError("Missing ADMIN_EMAIL. Cannot start without seeded single admin.")
    if not admin_password and not admin_setup_token:
        raise RuntimeError(
            "Missing admin credentials. Set ADMIN_PASSWORD or ADMIN_SETUP_TOKEN to seed the single admin."
        )

    with _db_conn() as conn:
        admins = conn.execute("SELECT * FROM users WHERE role = 'admin'").fetchall()
        if len(admins) > 1:
            raise RuntimeError("Single-admin invariant violated: more than one admin exists in database.")

        now = _utc_now_iso()
        if not admins:
            password_hash = _hash_password(admin_password) if admin_password else None
            cur = conn.execute(
                """
                INSERT INTO users
                (name, email, organization, use_case, role, status, access_granted, password_hash, created_at, updated_at)
                VALUES (?, ?, '', 'Seeded admin account', 'admin', 'granted', TRUE, ?, ?, ?)
                RETURNING id
                """,
                (admin_name, admin_email, password_hash, now, now),
            )
            admin_row = cur.fetchone()
            if not admin_row:
                raise RuntimeError("Failed to create seeded admin account.")
            admin_id = int(admin_row["id"])
            if admin_setup_token and not admin_password:
                conn.execute(
                    """
                    INSERT INTO password_setup_tokens
                    (user_id, token_hash, expires_at, used, created_by_admin_id, created_at)
                    VALUES (?, ?, ?, FALSE, NULL, ?)
                    """,
                    (
                        admin_id,
                        _hash_token(admin_setup_token),
                        _utc_iso_after_hours(PASSWORD_SETUP_TOKEN_TTL_HOURS),
                        now,
                    ),
                )
            conn.commit()
            return

        admin_row = admins[0]
        existing_email = str(admin_row["email"]).strip().lower()
        if existing_email != admin_email:
            raise RuntimeError(
                f"Seeded admin mismatch. DB admin={existing_email}, env ADMIN_EMAIL={admin_email}."
            )

        if admin_row["status"] != "granted" or int(admin_row["access_granted"]) != 1:
            raise RuntimeError("Admin account is corrupt. Admin must always be status='granted' and access_granted=1.")

        if not admin_row["password_hash"]:
            if admin_password:
                conn.execute(
                    "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                    (_hash_password(admin_password), now, int(admin_row["id"])),
                )
                conn.commit()
            elif admin_setup_token:
                token_hash = _hash_token(admin_setup_token)
                existing = conn.execute(
                    """
                    SELECT id FROM password_setup_tokens
                    WHERE user_id = ? AND token_hash = ? AND used = FALSE AND expires_at > ?
                    """,
                    (int(admin_row["id"]), token_hash, now),
                ).fetchone()
                if not existing:
                    conn.execute(
                        """
                        INSERT INTO password_setup_tokens
                        (user_id, token_hash, expires_at, used, created_by_admin_id, created_at)
                        VALUES (?, ?, ?, FALSE, NULL, ?)
                        """,
                        (
                            int(admin_row["id"]),
                            token_hash,
                            _utc_iso_after_hours(PASSWORD_SETUP_TOKEN_TTL_HOURS),
                            now,
                        ),
                    )
                    conn.commit()
            else:
                raise RuntimeError("Admin password is missing. Set ADMIN_PASSWORD or ADMIN_SETUP_TOKEN.")


def _initialize_auth_system() -> None:
    _ensure_auth_schema()
    _bootstrap_single_admin()


def _extract_bearer_token(authorization: Optional[str]) -> str:
    raw = (authorization or "").strip()
    if not raw.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid bearer token.")
    token = raw[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    return token


def _extract_bearer_token_optional(authorization: Optional[str]) -> Optional[str]:
    raw = (authorization or "").strip()
    if not raw.lower().startswith("bearer "):
        return None
    token = raw[7:].strip()
    return token or None


def _get_valid_session_user_row(raw_token: str) -> Optional[AuthRow]:
    token_hash = _hash_token(raw_token)
    now = _utc_now_iso()
    with _db_conn() as conn:
        session_row = conn.execute(
            """
            SELECT
                s.id AS session_id,
                s.user_id AS session_user_id,
                s.revoked,
                s.expires_at,
                u.id,
                u.name,
                u.email,
                u.organization,
                u.use_case,
                u.advocate_address,
                u.advocate_mobile,
                u.role,
                u.status,
                u.access_granted,
                u.password_hash,
                u.created_at,
                u.updated_at
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        if not session_row or bool(session_row["revoked"]) or str(session_row["expires_at"]) <= now:
            return None
        return session_row


def _get_user_by_valid_session_token(raw_token: str) -> AuthRow:
    user_row = _get_valid_session_user_row(raw_token)
    if not user_row:
        raise HTTPException(status_code=401, detail="Session expired or invalid.")
    return user_row


def _get_request_auth_context(authorization: Optional[str]) -> Dict[str, Any]:
    raw_token = _extract_bearer_token_optional(authorization)
    if not raw_token:
        return {
            "user_id": None,
            "user_email": "",
            "user_role": "",
            "session_id": None,
            "is_authenticated": False,
        }

    user_row = _get_valid_session_user_row(raw_token)
    if not user_row:
        return {
            "user_id": None,
            "user_email": "",
            "user_role": "",
            "session_id": None,
            "is_authenticated": False,
        }

    return {
        "user_id": int(user_row["id"]),
        "user_email": str(user_row["email"] or ""),
        "user_role": str(user_row["role"] or ""),
        "session_id": int(user_row["session_id"]) if "session_id" in user_row and user_row["session_id"] is not None else None,
        "is_authenticated": True,
    }


def _require_authenticated_user(authorization: Optional[str]) -> AuthRow:
    token = _extract_bearer_token(authorization)
    return _get_user_by_valid_session_token(token)


def _require_admin_user(authorization: Optional[str]) -> AuthRow:
    user = _require_authenticated_user(authorization)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


def _require_product_access_user(authorization: Optional[str]) -> AuthRow:
    user = _require_authenticated_user(authorization)
    if user["role"] == "admin":
        return user
    if user["status"] != "granted" or int(user["access_granted"]) != 1:
        raise HTTPException(status_code=403, detail="Product access not granted.")
    return user


def _create_session_for_user(user_id: int) -> str:
    raw_token = secrets.token_urlsafe(48)
    now = _utc_now_iso()
    expires_at = _utc_iso_after_hours(SESSION_TTL_HOURS)
    with _db_conn() as conn:
        conn.execute(
            """
            INSERT INTO sessions (user_id, token_hash, expires_at, revoked, created_at)
            VALUES (?, ?, ?, FALSE, ?)
            """,
            (user_id, _hash_token(raw_token), expires_at, now),
        )
        conn.commit()
    return raw_token


CHAT_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")


def _sanitize_chat_session_id(session_id: Optional[str]) -> str:
    raw = str(session_id or "").strip()
    if not raw:
        return str(uuid.uuid4())
    if not CHAT_SESSION_ID_RE.fullmatch(raw):
        raise HTTPException(status_code=400, detail="Invalid session_id format.")
    return raw


def _derive_chat_title(seed_text: str) -> str:
    cleaned = " ".join(str(seed_text or "").split()).strip()
    if not cleaned:
        return "New Conversation"
    if len(cleaned) <= 80:
        return cleaned
    return cleaned[:77].rstrip() + "..."


def _get_chat_session_row(user_id: int, session_id: str) -> Optional[AuthRow]:
    with _db_conn() as conn:
        return conn.execute(
            """
            SELECT session_id, title, created_at, updated_at, last_message_at
            FROM chat_sessions
            WHERE user_id = ? AND session_id = ? AND archived = FALSE
            """,
            (user_id, session_id),
        ).fetchone()


def _ensure_chat_session(user_id: int, session_id: str, seed_text: str = "") -> None:
    now = _utc_now_iso()
    title = _derive_chat_title(seed_text)
    with _db_conn() as conn:
        row = conn.execute(
            "SELECT session_id, title, archived FROM chat_sessions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        ).fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO chat_sessions (session_id, user_id, title, created_at, updated_at, last_message_at, archived)
                VALUES (?, ?, ?, ?, ?, ?, FALSE)
                """,
                (session_id, user_id, title, now, now, now),
            )
        elif bool(row["archived"]):
            conn.execute(
                """
                UPDATE chat_sessions
                SET archived = FALSE, updated_at = ?, last_message_at = ?
                WHERE user_id = ? AND session_id = ?
                """,
                (now, now, user_id, session_id),
            )
        conn.commit()


def _save_chat_turn(user_id: int, session_id: str, user_text: str, assistant_text: str) -> None:
    now = _utc_now_iso()
    title_candidate = _derive_chat_title(user_text)
    with _db_conn() as conn:
        row = conn.execute(
            "SELECT title FROM chat_sessions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        ).fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO chat_sessions (session_id, user_id, title, created_at, updated_at, last_message_at, archived)
                VALUES (?, ?, ?, ?, ?, ?, FALSE)
                """,
                (session_id, user_id, title_candidate, now, now, now),
            )
            current_title = title_candidate
        else:
            current_title = str(row["title"] or "").strip()

        conn.executemany(
            """
            INSERT INTO chat_messages (session_id, user_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (session_id, user_id, "user", str(user_text or ""), now),
                (session_id, user_id, "assistant", str(assistant_text or ""), now),
            ],
        )

        final_title = current_title
        if not current_title or current_title.lower() in {"new conversation", "new chat", "untitled"}:
            final_title = title_candidate

        conn.execute(
            """
            UPDATE chat_sessions
            SET title = ?, updated_at = ?, last_message_at = ?, archived = FALSE
            WHERE user_id = ? AND session_id = ?
            """,
            (final_title, now, now, user_id, session_id),
        )
        conn.commit()


def _record_chat_turn(user_id: int, session_id: str, user_text: str, assistant_text: str) -> None:
    SESSIONS.setdefault(session_id, [])
    SESSIONS[session_id].append({"role": "user", "content": str(user_text or "")})
    SESSIONS[session_id].append({"role": "assistant", "content": str(assistant_text or "")})
    _save_chat_turn(user_id, session_id, user_text, assistant_text)


def _load_chat_history_for_prompt(user_id: int, session_id: str, limit: int = CHAT_HISTORY_PROMPT_LIMIT) -> List[Dict[str, str]]:
    safe_limit = max(2, min(int(limit or CHAT_HISTORY_PROMPT_LIMIT), 200))
    with _db_conn() as conn:
        rows = conn.execute(
            """
            SELECT role, content
            FROM chat_messages
            WHERE user_id = ? AND session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, session_id, safe_limit),
        ).fetchall()
    history = [{"role": str(row["role"]), "content": str(row["content"])} for row in reversed(rows)]
    return history


def _clear_chat_history(user_id: int, session_id: str) -> None:
    now = _utc_now_iso()
    with _db_conn() as conn:
        conn.execute(
            "DELETE FROM chat_messages WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )
        conn.execute(
            """
            UPDATE chat_sessions
            SET title = 'New Conversation', updated_at = ?, last_message_at = ?
            WHERE user_id = ? AND session_id = ?
            """,
            (now, now, user_id, session_id),
        )
        conn.commit()
    SESSIONS[session_id] = []


def _load_chat_session_detail(user_id: int, session_id: str, limit: int = CHAT_HISTORY_DETAIL_LIMIT) -> Optional[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit or CHAT_HISTORY_DETAIL_LIMIT), 500))
    with _db_conn() as conn:
        session_row = conn.execute(
            """
            SELECT
                c.session_id,
                c.title,
                c.created_at,
                c.updated_at,
                c.last_message_at,
                (
                    SELECT COUNT(*)
                    FROM chat_messages m
                    WHERE m.session_id = c.session_id AND m.user_id = c.user_id
                ) AS message_count,
                COALESCE((
                    SELECT substr(m2.content, 1, 220)
                    FROM chat_messages m2
                    WHERE m2.session_id = c.session_id AND m2.user_id = c.user_id
                    ORDER BY m2.id DESC
                    LIMIT 1
                ), '') AS preview
            FROM chat_sessions c
            WHERE c.user_id = ? AND c.session_id = ? AND c.archived = FALSE
            """,
            (user_id, session_id),
        ).fetchone()
        if not session_row:
            return None

        messages_rows = conn.execute(
            """
            SELECT role, content, created_at
            FROM chat_messages
            WHERE user_id = ? AND session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, session_id, safe_limit),
        ).fetchall()

    messages = [
        {"role": str(row["role"]), "content": str(row["content"]), "created_at": str(row["created_at"])}
        for row in reversed(messages_rows)
    ]
    summary = {
        "session_id": str(session_row["session_id"]),
        "title": str(session_row["title"] or "New Conversation"),
        "created_at": str(session_row["created_at"]),
        "updated_at": str(session_row["updated_at"]),
        "last_message_at": str(session_row["last_message_at"]),
        "message_count": int(session_row["message_count"] or 0),
        "preview": str(session_row["preview"] or ""),
    }
    return {"session": summary, "messages": messages}


def _list_chat_sessions(user_id: int, limit: int = CHAT_HISTORY_LIST_LIMIT) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit or CHAT_HISTORY_LIST_LIMIT), 100))
    with _db_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                c.session_id,
                c.title,
                c.created_at,
                c.updated_at,
                c.last_message_at,
                (
                    SELECT COUNT(*)
                    FROM chat_messages m
                    WHERE m.session_id = c.session_id AND m.user_id = c.user_id
                ) AS message_count,
                COALESCE((
                    SELECT substr(m2.content, 1, 220)
                    FROM chat_messages m2
                    WHERE m2.session_id = c.session_id AND m2.user_id = c.user_id
                    ORDER BY m2.id DESC
                    LIMIT 1
                ), '') AS preview
            FROM chat_sessions c
            WHERE c.user_id = ? AND c.archived = FALSE
            ORDER BY c.last_message_at DESC
            LIMIT ?
            """,
            (user_id, safe_limit),
        ).fetchall()

    return [
        {
            "session_id": str(row["session_id"]),
            "title": str(row["title"] or "New Conversation"),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "last_message_at": str(row["last_message_at"]),
            "message_count": int(row["message_count"] or 0),
            "preview": str(row["preview"] or ""),
        }
        for row in rows
    ]


def _rename_chat_session(user_id: int, session_id: str, title: str) -> bool:
    cleaned = " ".join(str(title or "").split()).strip()
    if not cleaned:
        return False
    now = _utc_now_iso()
    with _db_conn() as conn:
        cur = conn.execute(
            """
            UPDATE chat_sessions
            SET title = ?, updated_at = ?
            WHERE user_id = ? AND session_id = ? AND archived = FALSE
            """,
            (cleaned[:120], now, user_id, session_id),
        )
        conn.commit()
        return cur.rowcount > 0


def _delete_chat_session(user_id: int, session_id: str) -> bool:
    with _db_conn() as conn:
        cur = conn.execute(
            "DELETE FROM chat_sessions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )
        conn.commit()
    if cur.rowcount > 0:
        SESSIONS.pop(session_id, None)
        return True
    return False


_initialize_auth_system()


def _clip_text(value: Optional[str], max_length: int = 1024) -> str:
    text = str(value or "").strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def _derive_access_outcome(status_code: int) -> Literal["success", "client_error", "server_error"]:
    if status_code >= 500:
        return "server_error"
    if status_code >= 400:
        return "client_error"
    return "success"


def _extract_request_ip_details(request: Request) -> Tuple[str, str, str]:
    forwarded_for = _clip_text(request.headers.get("x-forwarded-for"), max_length=512)
    real_ip = _clip_text(request.headers.get("x-real-ip"), max_length=255)
    ip_candidates = [part.strip() for part in forwarded_for.split(",") if part.strip()]
    client_ip = ip_candidates[0] if ip_candidates else real_ip
    if not client_ip:
        client_ip = _clip_text(getattr(request.client, "host", ""), max_length=255)
    return client_ip, forwarded_for, real_ip


def _record_access_event(
    request: Request,
    *,
    occurred_at: str,
    status_code: int,
    auth_context: Dict[str, Any],
) -> None:
    ip_address, forwarded_for, real_ip = _extract_request_ip_details(request)
    with _db_conn() as conn:
        conn.execute(
            """
            INSERT INTO access_events (
                occurred_at,
                ip_address,
                forwarded_for,
                real_ip,
                method,
                path,
                status_code,
                outcome,
                user_agent,
                referer,
                origin,
                query_string_present,
                user_id,
                user_email,
                user_role,
                session_id,
                is_authenticated
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                occurred_at,
                _clip_text(ip_address, max_length=255),
                forwarded_for,
                real_ip,
                _clip_text(request.method.upper(), max_length=16),
                _clip_text(request.url.path or "/", max_length=255),
                int(status_code),
                _derive_access_outcome(status_code),
                _clip_text(request.headers.get("user-agent"), max_length=1024),
                _clip_text(request.headers.get("referer"), max_length=1024),
                _clip_text(request.headers.get("origin"), max_length=512),
                bool(request.scope.get("query_string")),
                auth_context.get("user_id"),
                _clip_text(auth_context.get("user_email"), max_length=320),
                _clip_text(auth_context.get("user_role"), max_length=32),
                auth_context.get("session_id"),
                bool(auth_context.get("is_authenticated")),
            ),
        )
        conn.commit()


def _normalize_monitoring_timestamp(value: Optional[str], field_name: str) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            parsed = datetime.fromisoformat(f"{raw}T00:00:00+00:00")
        else:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)
        return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name} timestamp.") from exc


def _build_access_event_filters(
    *,
    from_at: Optional[str],
    to_at: Optional[str],
    ip: Optional[str],
    user_id: Optional[int],
    email: Optional[str],
    path_contains: Optional[str],
    status_code: Optional[int],
    outcome: Optional[str],
    authenticated_only: Optional[bool],
) -> Tuple[str, List[Any]]:
    where_parts: List[str] = []
    params: List[Any] = []

    normalized_from = _normalize_monitoring_timestamp(from_at, "from")
    normalized_to = _normalize_monitoring_timestamp(to_at, "to")
    if not normalized_from and not normalized_to:
        normalized_from = _utc_iso_days_ago(ADMIN_MONITORING_DEFAULT_DAYS)
        normalized_to = _utc_now_iso()
    if normalized_from and normalized_to and normalized_from > normalized_to:
        raise HTTPException(status_code=400, detail="'from' must be earlier than or equal to 'to'.")

    if normalized_from:
        where_parts.append("occurred_at >= ?")
        params.append(normalized_from)
    if normalized_to:
        where_parts.append("occurred_at <= ?")
        params.append(normalized_to)

    clean_ip = str(ip or "").strip()
    if clean_ip:
        where_parts.append("ip_address = ?")
        params.append(clean_ip)

    if user_id is not None:
        where_parts.append("user_id = ?")
        params.append(int(user_id))

    clean_email = str(email or "").strip().lower()
    if clean_email:
        where_parts.append("LOWER(user_email) LIKE ?")
        params.append(f"%{clean_email}%")

    clean_path = str(path_contains or "").strip()
    if clean_path:
        where_parts.append("path ILIKE ?")
        params.append(f"%{clean_path}%")

    if status_code is not None:
        where_parts.append("status_code = ?")
        params.append(int(status_code))

    clean_outcome = str(outcome or "").strip().lower()
    if clean_outcome:
        if clean_outcome not in {"success", "client_error", "server_error"}:
            raise HTTPException(status_code=400, detail="Invalid outcome filter.")
        where_parts.append("outcome = ?")
        params.append(clean_outcome)

    if authenticated_only is not None:
        where_parts.append("is_authenticated = ?")
        params.append(bool(authenticated_only))

    if not where_parts:
        return "", params
    return "WHERE " + " AND ".join(where_parts), params


def _serialize_access_event(row: AuthRow) -> Dict[str, Any]:
    item = dict(row)
    item["id"] = int(item["id"])
    item["status_code"] = int(item["status_code"])
    item["query_string_present"] = bool(item.get("query_string_present"))
    item["is_authenticated"] = bool(item.get("is_authenticated"))
    item["user_id"] = int(item["user_id"]) if item.get("user_id") is not None else None
    item["session_id"] = int(item["session_id"]) if item.get("session_id") is not None else None
    return item


@app.middleware("http")
async def access_event_logging_middleware(request: Request, call_next: Any) -> Any:
    if request.method.upper() == "OPTIONS":
        return await call_next(request)

    occurred_at = _utc_now_iso()
    auth_context = _get_request_auth_context(request.headers.get("authorization"))
    status_code = 500
    try:
        response = await call_next(request)
        status_code = int(response.status_code)
        return response
    except Exception:
        status_code = 500
        raise
    finally:
        try:
            _record_access_event(
                request,
                occurred_at=occurred_at,
                status_code=status_code,
                auth_context=auth_context,
            )
        except Exception:
            pass


def _domain_forbidden_terms(domain: str) -> List[str]:
    return DOMAIN_FORBIDDEN_QUESTION_TERMS.get(str(domain or "").lower(), [])


def _domain_allowed_terms(domain: str) -> List[str]:
    return DOMAIN_ALLOWED_VOCABULARY.get(str(domain or "").lower(), [])


def _top_law_name(laws: List[ApplicableLaw]) -> Optional[str]:
    if not laws:
        return None
    top = laws[0]
    return f"{top.law}:{top.section}"


def _update_session_facts_from_case_model(case_obj: CaseModel, session_facts: Dict[str, Any]) -> Dict[str, Any]:
    facts = dict(session_facts or {})
    for f in case_obj.financials:
        facts["amount"] = f.amount
        context = (f.context or "").lower()
        if "salary" in context:
            facts["months_unpaid"] = facts.get("months_unpaid", True)
        if "deposit" in context:
            facts["issue_type"] = facts.get("issue_type") or "security_deposit"
    for d in case_obj.documents:
        low_type = (d.type or "").lower()
        if "agreement" in low_type or "contract" in low_type or "lease" in low_type:
            facts["agreement"] = True
        if low_type in {"screenshot", "email", "receipt", "salary_slip", "bank_statement"}:
            facts["proof"] = True
    for evt in case_obj.events:
        desc = (evt.description or "").lower()
        if any(token in desc for token in ["terminated", "fired", "resigned", "left the job"]):
            facts["status"] = True
        if "notice" in desc:
            facts["notice"] = True
        if "salary" in desc:
            facts["months_unpaid"] = facts.get("months_unpaid", True)
    return facts


def _fresh_interview_session_state() -> Dict[str, Any]:
    return {
        "issue": "unknown",
        "active_issues": [],
        "facts": {},
        "asked_questions": [],
        "case_model": None,
        "signals": {},
        "pending_confirmation": None,
        "contradictions": [],
        "last_top_law": None,
        "interview_turns": 0,
        "stagnant_turns": 0,
        "pending_confirmation_retries": 0,
        "asked_contradiction_codes": [],
    }


def _should_auto_reset_interview_session(session: Dict[str, Any], query: str) -> bool:
    """Reset stale interview state when a clearly new case narrative is submitted on an existing session."""
    if not session:
        return False
    prior_turns = int(session.get("interview_turns", 0))
    if prior_turns < 2:
        return False

    q = str(query or "")
    low = q.lower()
    words = re.findall(r"[a-z0-9]+", low)
    if len(words) < 40:
        return False

    new_matter_markers = [
        "my client", "purchased", "bought", "hospital", "medical", "seller", "manufacturer",
        "injury", "burn", "accident", "seeking legal advice", "despite multiple complaints",
    ]
    looks_like_new_narrative = (q.count(".") >= 3 or "\n" in q) and any(tok in low for tok in new_matter_markers)
    if not looks_like_new_narrative:
        return False

    hinted = str((detect_issues(q) or {}).get("primary") or "unknown")
    current = str(session.get("issue") or "unknown")
    issue_shift = hinted not in {"unknown", ""} and current not in {"unknown", ""} and hinted != current

    return issue_shift or bool(session.get("signals")) or len(session.get("asked_questions", [])) >= 3

# =========================
# HELPERS
# =========================

def build_context_text(context_blocks: List[Dict]) -> str:
    lines = []
    for c in context_blocks:
        ref = c.get("citation_id") or "CTX"
        corpus = (c.get("corpus") or "unknown").upper()
        title = c.get("title") or "Legal Document"
        section_number = c.get("section_number")
        section_title = c.get("section_title")
        context_path = c.get("context_path")
        texts = c.get("texts", {}) or {}

        header = f"[{ref}] Source: {corpus} | Title: {title}"
        if section_number:
            header += f" | Section: {section_number}"
        if section_title:
            header += f" | Section Title: {section_title}"
        if context_path:
            header += f" | Context: {context_path}"
        lines.append(header)
        lines.append(f"Content: {texts.get('chunk_text', '')}")

        if texts.get("parent_text"):
            lines.append(f"Parent Context: {texts.get('parent_text')}")
        if texts.get("section_text"):
            lines.append(f"Section Text: {texts.get('section_text')}")
        if texts.get("court") or texts.get("date"):
            lines.append(f"Court: {texts.get('court')} | Date: {texts.get('date')}")
        if texts.get("bench"):
            lines.append(f"Bench: {texts.get('bench')}")
        lines.append("")

    return "\n".join(lines).strip()


def build_direct_legal_prompt(user_query: str, legal_priors: str = "", citation_text: str = "") -> str:
    priors_block = f"\n\n{legal_priors}\n" if legal_priors else ""
    citations_block = f"\n\n{citation_text}\n" if citation_text else ""
    return (
        "You are a senior Indian legal expert.\n"
        "Answer strictly in Indian legal context only.\n"
        "Use Indian statutes, Indian courts, and Indian legal terminology.\n"
        "If the question appears to be about another country, still provide an India-focused answer and state that assumption.\n"
        "Provide a clear general legal-information answer using your own knowledge.\n"
        "Do not refuse with generic text like 'I can't give legal advice'.\n"
        "If specific legal advice is requested, provide general legal information, legal options, and procedural next steps.\n"
        "Do not claim to quote any specific statute unless you are reasonably confident.\n"
        "If jurisdiction or facts are unclear, state assumptions explicitly.\n"
        "Be confident and direct — do NOT hedge.\n"
        "Cite relevant laws and sections where possible.\n"
        "If citations are available below, refer to them explicitly.\n\n"
        f"User question:\n{user_query}\n"
        f"{priors_block}"
        f"{citations_block}\n"
        "Return in strict FIRAC structure:\n"
        "Part 1 - Facts:\n"
        "Part 2 - Issue:\n"
        "Part 3 - Rule:\n"
        "Part 4 - Application:\n"
        "Part 5 - Conclusion:\n"
        "Disclaimer:\n"
    )


def _detect_low_confidence(results: List[Dict[str, Any]]) -> bool:
    """PHASE 2: Detect when retrieval confidence is too low to rely on."""
    if not results:
        return True
    scores = [float(r.get('final_score', r.get('hybrid_score', 0)) or 0) for r in results]
    avg_score = sum(scores) / len(scores)
    return avg_score < 0.3


def _build_fallback_prompt(user_query: str, legal_priors: str, citation_text: str = "") -> str:
    """PHASE 2+3: Fallback prompt — used when retrieval is weak.
    Gives the LLM permission to reason from legal knowledge + heuristic priors.
    Phase 3: Also injects citations and enforces FIRAC."""
    priors_section = f"{legal_priors}\n\n" if legal_priors else ""
    citations_section = f"{citation_text}\n\n" if citation_text else ""
    return (
        "You are an expert Indian lawyer with deep knowledge of Indian statutes and case law.\n\n"
        "The legal database retrieval did not return strong results for this query.\n"
        "However, use your legal knowledge combined with the known legal signals below to:\n\n"
        "1. Identify the legal issue\n"
        "2. Name the applicable Indian laws and specific sections\n"
        "3. Suggest concrete legal remedies\n"
        "4. Explain the exact next steps the person should take\n\n"
        "Do not refuse with generic text like 'I can't give legal advice'.\n"
        "Provide general legal information and procedural guidance.\n"
        "Be confident and direct — do NOT hedge.\n"
        "If citations are available below, refer to them explicitly.\n"
        "If jurisdiction or facts are unclear, state assumptions explicitly.\n\n"
        f"User Facts:\n{user_query}\n\n"
        f"{priors_section}"
        f"{citations_section}"
        "Structure your answer in strict FIRAC format:\n"
        "Part 1 - Facts:\n"
        "- Restate only the material facts\n\n"
        "Part 2 - Issue:\n"
        "- Frame the core legal issue(s) as questions\n\n"
        "Part 3 - Rule:\n"
        "- List every applicable Act, section, and judgement\n\n"
        "Part 4 - Application:\n"
        "- Apply each rule to the facts step-by-step\n"
        "- Include procedural next steps and forum/authority\n\n"
        "Part 5 - Conclusion:\n"
        "- Give a clear legal conclusion and immediate action plan\n\n"
        "Disclaimer:\n"
        "For information only. Consult a professional.\n"
    )


def _build_augmented_context(base_context: str, legal_priors: str) -> str:
    """PHASE 2: Merge retrieved context with heuristic priors."""
    if not legal_priors:
        return base_context
    return f"{base_context}\n\n---\n{legal_priors}\n" if base_context else legal_priors


def _is_legal_advice_refusal(answer: str) -> bool:
    text = (answer or "").strip().lower()
    patterns = [
        "i can't give legal advice",
        "i cant give legal advice",
        "cannot give legal advice",
        "can't provide legal advice",
        "cannot provide legal advice",
        "not able to provide legal advice",
        "i am not a lawyer so i cannot",
    ]
    return any(p in text for p in patterns)


def _retry_prompt_for_general_info(user_query: str) -> str:
    return (
        "You are an Indian legal information assistant.\n"
        "Do not refuse with 'I can't give legal advice'.\n"
        "Instead provide:\n"
        "Part 1 - Facts,\n"
        "Part 2 - Issue,\n"
        "Part 3 - Rule,\n"
        "Part 4 - Application,\n"
        "Part 5 - Conclusion,\n"
        "Disclaimer.\n"
        "Give general legal information and practical procedural guidance. Do not assist wrongdoing.\n\n"
        f"User question:\n{user_query}\n"
    )


def extract_structured_query(user_query: str, model_name: str) -> Dict[str, Any]:
    prompt = (
        "Convert the user's legal query into JSON.\n"
        "Return ONLY valid JSON with this schema:\n"
        "{\n"
        '  "domain": "consumer|criminal|contract|property|labour|general",\n'
        '  "intent": "legal_notice|legal_query",\n'
        '  "facts": ["fact 1", "fact 2"]\n'
        "}\n"
        "Rules:\n"
        "- Extract atomic facts.\n"
        "- Do not rely on punctuation splitting alone.\n"
        "- Use 'legal_notice' only if the user is clearly asking to draft a notice.\n\n"
        f"User query:\n{user_query}"
    )

    raw = call_llm(model_name=model_name, prompt=prompt, timeout_sec=20)
    if raw.startswith("[ERROR]"):
        raw = ""

    try:
        start = raw.find("{")
        end = raw.rfind("}")
        payload = json.loads(raw[start : end + 1]) if start >= 0 and end > start else {}
    except Exception:
        payload = {}

    route = classify_legal_issue(user_query)
    facts = payload.get("facts")
    if not isinstance(facts, list) or not facts:
        facts = [
            frag.strip(" .")
            for frag in re.split(r"\b(?:and|but|because|after|when|while)\b|[.;!?]", user_query, flags=re.IGNORECASE)
            if frag.strip()
        ]
    facts = [str(f).strip() for f in facts if str(f).strip()][:5]

    domain = str(payload.get("domain") or route.domain or "general").strip().lower()
    if domain not in {"consumer", "criminal", "contract", "property", "labour", "general"}:
        domain = route.domain or "general"

    intent = str(payload.get("intent") or "legal_query").strip().lower()
    if intent not in {"legal_notice", "legal_query"}:
        intent = "legal_query"

    return {
        "domain": domain,
        "intent": intent,
        "facts": facts,
    }


def merge_retrieval_results(result_sets: List[List[Dict[str, Any]]], top_k: int) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for results in result_sets:
        for item in results:
            key = "|".join(
                [
                    str(item.get("corpus") or ""),
                    str(item.get("chunk_id") or ""),
                    str(item.get("title") or ""),
                    str(item.get("section_number") or ""),
                    str(item.get("context_path") or ""),
                ]
            )
            existing = merged.get(key)
            current_score = float(item.get("final_score", item.get("hybrid_score", 0.0)) or 0.0)
            if not existing or current_score > float(existing.get("final_score", existing.get("hybrid_score", 0.0)) or 0.0):
                merged[key] = dict(item)

    ranked = list(merged.values())
    ranked.sort(key=lambda x: float(x.get("final_score", x.get("hybrid_score", 0.0)) or 0.0), reverse=True)
    if top_k <= 0:
        return []

    top = ranked[:top_k]
    if not top:
        return top

    # Preserve corpus diversity: keep at least one act, and include judgement only if usable.
    available_corpora = {str(item.get("corpus") or "").lower() for item in ranked}
    top_corpora = {str(item.get("corpus") or "").lower() for item in top}

    def _inject_corpus(corpus_name: str, predicate: Optional[Any] = None) -> None:
        if top_k < 2:
            return
        if corpus_name not in available_corpora or corpus_name in top_corpora:
            return
        candidate = next(
            (
                item
                for item in ranked
                if str(item.get("corpus") or "").lower() == corpus_name
                and (predicate(item) if predicate else True)
            ),
            None,
        )
        if not candidate:
            return
        # Replace the last item from another corpus to preserve list size.
        replace_idx = next(
            (idx for idx in range(len(top) - 1, -1, -1) if str(top[idx].get("corpus") or "").lower() != corpus_name),
            len(top) - 1,
        )
        top[replace_idx] = candidate
        top_corpora.add(corpus_name)

    _inject_corpus("acts")
    _inject_corpus("judgements", predicate=lambda item: _is_usable_judgement_result(item, min_score=0.2))

    # Dedupe while preserving order, then refill from ranked if needed.
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in top:
        key = (
            str(item.get("corpus") or ""),
            str(item.get("chunk_id") or ""),
            str(item.get("title") or ""),
            str(item.get("section_number") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    if len(deduped) < top_k:
        for item in ranked:
            key = (
                str(item.get("corpus") or ""),
                str(item.get("chunk_id") or ""),
                str(item.get("title") or ""),
                str(item.get("section_number") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
            if len(deduped) >= top_k:
                break

    return deduped[:top_k]


def _extract_json_object(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if not text or text.startswith("[ERROR]"):
        return {}
    try:
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _coerce_string_list(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    return [str(v).strip() for v in values if str(v).strip()]


def _parse_answer_sections(answer: str) -> Dict[str, str]:
    normalized = (answer or "").replace("\r\n", "\n").strip()
    sections: Dict[str, str] = {}
    def _extract_any(headings: List[str]) -> str:
        for heading in headings:
            pattern = rf"(?is)(?:\*\*)?{re.escape(heading)}(?:\*\*)?\s*\n(.*?)(?=\n(?:\*\*)?Part\s*\d+\s*-\s*[A-Za-z][^\n]*(?:\*\*)?\s*\n|\Z)"
            match = re.search(pattern, normalized)
            if match:
                return match.group(1).strip()
        return ""

    sections["facts"] = _extract_any(["Part 1 - Facts", "Part 1 - Facts and Legal Issue"])
    sections["issue"] = _extract_any(["Part 2 - Issue"])
    sections["rule"] = _extract_any(["Part 3 - Rule", "Part 2 - Applicable Law", "Part 1 - Acts, Sections and Judgements"])
    sections["application"] = _extract_any(["Part 4 - Application", "Part 3 - Analysis", "Part 2 - Exact Steps to Follow"])
    sections["conclusion"] = _extract_any(["Part 5 - Conclusion", "Part 5 - Limits", "Part 3 - Limits"])
    sections["disclaimer"] = _extract_any(["Part 6 - Disclaimer", "Part 4 - Disclaimer", "Disclaimer"])

    # Backward-compatible aliases used by older response shaping logic.
    sections["part1"] = sections["rule"]
    sections["part2"] = sections["application"]
    sections["part3"] = sections["conclusion"]
    sections["part4"] = sections["disclaimer"]
    return sections


def _extract_numbered_items(text: str) -> List[str]:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    items: List[str] = []
    for line in lines:
        cleaned = re.sub(r"^\d+\.\s*", "", line)
        cleaned = re.sub(r"^[-*•]\s*", "", cleaned)
        if cleaned:
            items.append(cleaned)
    return items


def _filter_lawyer_questions(
    questions: List[Dict[str, Any]],
    domain: str,
    legal_pathways: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    forbidden_terms = _domain_forbidden_terms(domain)
    allowed_terms = _domain_allowed_terms(domain)
    pathway_laws = {str(p.get("law", "")).strip() for p in legal_pathways if str(p.get("law", "")).strip()}

    filtered: List[Dict[str, Any]] = []
    seen = set()
    for index, item in enumerate(questions, start=1):
        question = str(item.get("question") or item.get("text") or "").strip()
        affects = _coerce_string_list(item.get("affects"))
        lowered = question.lower()
        if not question:
            continue
        if any(term in lowered for term in forbidden_terms):
            continue
        if affects:
            affects = [law for law in affects if law in pathway_laws]
        if not affects:
            continue
        if allowed_terms and not any(term in lowered for term in allowed_terms):
            pathway_text = " ".join(affects).lower()
            if not any(term in pathway_text for term in allowed_terms):
                continue
        key = (question.lower(), tuple(sorted(affects)))
        if key in seen:
            continue
        seen.add(key)
        filtered.append({"id": f"q{index}", "text": question, "affects": affects})
    return filtered[:5]


def retrieve_for_facts(facts: List[str], base_args: SimpleNamespace) -> List[Dict[str, Any]]:
    result_sets: List[List[Dict[str, Any]]] = []
    for fact in facts[:5]:
        args = SimpleNamespace(**vars(base_args))
        args.q = fact
        result_sets.append(run_retrieval(args))
    return merge_retrieval_results(result_sets, top_k=base_args.top_k)


def _extract_json_array(raw: str) -> List[str]:
    text = (raw or "").strip()
    if not text or text.startswith("[ERROR]"):
        return []
    try:
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            payload = json.loads(text[start : end + 1])
            if isinstance(payload, list):
                return [str(item).strip() for item in payload if str(item).strip()]
    except Exception:
        pass
    return []


def _clean_law_name(value: str) -> str:
    text = re.sub(r"\([^)]*\)", "", str(value or ""))
    text = re.sub(r",\s*\d{4}\b", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -,:;")
    return text


def _canonical_law_key(value: str) -> str:
    return re.sub(r"[^a-z]+", " ", _clean_law_name(value).lower()).strip()


def _display_law_name(value: str) -> str:
    cleaned = _clean_law_name(value)
    if not cleaned:
        return ""
    if cleaned == cleaned.lower():
        acronym_tokens = {"ipc", "crpc", "cpc", "it", "bns", "bnss", "bsa", "gst"}
        words = [token.upper() if token in acronym_tokens else token.capitalize() for token in cleaned.split()]
        return " ".join(words)
    return cleaned


def _is_placeholder_judgement_title(value: str) -> bool:
    title = re.sub(r"\s+", " ", str(value or "").strip().lower())
    if not title:
        return True
    if "title unavailable" in title:
        return True
    if title in {"judgement", "judgment", "case", "legal document", "untitled"}:
        return True
    if title.startswith("judgement") and len(title) <= 22:
        return True
    if title.startswith("judgment") and len(title) <= 22:
        return True
    return False


def _is_usable_judgement_result(item: Dict[str, Any], min_score: float = 0.0) -> bool:
    if str(item.get("corpus") or "").strip().lower() != "judgements":
        return False
    title = _display_law_name(str(item.get("title") or "")).strip()
    if _is_placeholder_judgement_title(title):
        return False
    score = float(item.get("final_score", item.get("hybrid_score", 0.0)) or 0.0)
    if score < float(min_score):
        return False
    text = str(item.get("chunk_text") or "")
    if len(text.strip()) < 80:
        return False
    return True


def _law_focus_candidates(law_focus: Dict[str, List[str]], limit: int = 6) -> List[str]:
    ordered: List[str] = []
    seen = set()
    for key in ("preferred_laws", "relevant_laws"):
        for raw in law_focus.get(key, []) or []:
            display = _display_law_name(raw)
            canonical = _canonical_law_key(display)
            if not display or not canonical or canonical in seen:
                continue
            seen.add(canonical)
            ordered.append(display)
            if len(ordered) >= limit:
                return ordered
    return ordered


def _extract_applicable_law_lines(
    context_blocks: List[Dict[str, Any]],
    fallback_laws: Optional[List[str]] = None,
    limit: int = 8,
) -> List[str]:
    law_sections: Dict[str, set[str]] = {}
    for block in context_blocks:
        corpus = str(block.get("corpus") or "").strip().lower()
        if corpus == "judgements":
            continue
        title = _display_law_name(str(block.get("title") or ""))
        section = str(block.get("section_number") or "").strip()
        if not title:
            continue
        law_sections.setdefault(title, set())
        if section:
            law_sections[title].add(section)

    lines: List[str] = []
    for title, sections in law_sections.items():
        if sections:
            section_list = ", ".join(sorted(sections, key=lambda x: (len(x), x)))
            lines.append(f"{title} - Section {section_list}")
        else:
            lines.append(title)
        if len(lines) >= limit:
            return lines[:limit]

    if lines:
        return lines[:limit]

    fallback = fallback_laws or []
    for law in fallback:
        display = _display_law_name(law)
        if display:
            lines.append(display)
        if len(lines) >= limit:
            break
    return lines[:limit]


def _is_security_deposit_tenancy_query(user_query: str, structured_query: Dict[str, Any]) -> bool:
    q = (user_query or "").lower()
    if structured_query.get("domain") != "property":
        return False
    required_groups = [
        any(term in q for term in ["landlord", "tenant", "lease", "rent", "vacated", "vacate"]),
        any(term in q for term in ["security deposit", "deposit"]),
    ]
    return all(required_groups)


def _is_cyber_it_act_query(user_query: str, structured_query: Dict[str, Any]) -> bool:
    q = (user_query or "").lower()
    cyber_terms = [
        "cyber", "online fraud", "otp", "phishing", "hacking", "hacked",
        "data breach", "identity theft", "fake profile", "ransomware",
        "upi fraud", "bank otp", "sim swap", "whatsapp fraud",
    ]
    it_markers = ["it act", "information technology act", "ita 2000", "section 66", "section 67", "section 43"]
    return any(term in q for term in cyber_terms) or any(marker in q for marker in it_markers)


def _deterministic_retrieval_queries(user_query: str, structured_query: Dict[str, Any]) -> List[str]:
    q = " ".join((user_query or "").split())
    if _is_security_deposit_tenancy_query(user_query, structured_query):
        return [
            "tenant security deposit refund transfer of property act india",
            "landlord refusing return of security deposit tenant remedy india",
            "lease security deposit refund breach of contract india",
            "tenant legal notice for security deposit recovery india",
            q,
        ][:MAX_RETRIEVAL_QUERIES]
    if _is_cyber_it_act_query(user_query, structured_query):
        return [
            "Information Technology Act cyber offence india",
            "IT Act phishing otp fraud online cheating india",
            "cyber crime unauthorized access data breach Information Technology Act",
            "identity theft fake profile online fraud IT Act india",
            q,
        ][:MAX_RETRIEVAL_QUERIES]
    return []


def _infer_era_filter(user_query: str, structured_query: Optional[Dict[str, Any]] = None) -> Optional[str]:
    q = (user_query or "").lower()
    structured_query = structured_query or {}

    explicit = str(structured_query.get("era") or "").strip().lower()
    if explicit in {"modern_criminal", "legacy_criminal"}:
        return explicit

    modern_markers = ["bns", "bnss", "bsa", "bhartiya nyaya", "bhartiya nagrik", "bhartiya sakshya"]
    legacy_markers = ["ipc", "crpc", "evidence act", "indian penal code", "code of criminal procedure"]

    if any(marker in q for marker in modern_markers):
        return "modern_criminal"
    if any(marker in q for marker in legacy_markers):
        return "legacy_criminal"
    return None


def generate_retrieval_queries(
    user_query: str,
    structured_query: Dict[str, Any],
    dense_query: str,
    rewritten_query: str,
    model_name: str,
    timeout_sec: int = 20,
) -> List[str]:
    deterministic = _deterministic_retrieval_queries(user_query, structured_query)
    if deterministic:
        return deterministic

    facts = structured_query.get("facts") or []
    prompt = (
        "Generate at most 5 highly relevant Indian legal search queries.\n"
        "Avoid unrelated laws, unrelated jurisdictions, and noisy expansion.\n"
        "Focus only on the core legal issue.\n"
        "Do not invent statute names, section numbers, penalties, multipliers, or remedies not present in the user query.\n"
        "Return ONLY a valid JSON array of strings.\n\n"
        f"User query: {user_query}\n"
        f"Detected domain: {structured_query.get('domain', 'general')}\n"
        f"Detected intent: {structured_query.get('intent', 'legal_query')}\n"
        f"Core facts: {json.dumps(facts[:5], ensure_ascii=False)}\n"
        f"Dense query seed: {dense_query}\n"
        f"Rewritten query seed: {rewritten_query}\n"
    )
    raw = call_llm(model_name=model_name, prompt=prompt, timeout_sec=timeout_sec)
    queries = _extract_json_array(raw)

    fallback = [rewritten_query, dense_query, user_query] + facts[:2]
    cleaned: List[str] = []
    seen = set()
    for candidate in queries + fallback:
        candidate = " ".join(str(candidate or "").replace("\n", " ").split()).strip()
        if not candidate:
            continue
        bad_markers = [
            "triple the security deposit",
            "rental agreement act",
            "section 11 of the transfer of property act",
        ]
        lowered_candidate = candidate.lower()
        if any(marker in lowered_candidate for marker in bad_markers):
            continue
        lowered = lowered_candidate
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(candidate)
        if len(cleaned) >= MAX_RETRIEVAL_QUERIES:
            break
    return cleaned[:MAX_RETRIEVAL_QUERIES]


def generate_relevant_laws(
    user_query: str,
    structured_query: Dict[str, Any],
    model_name: str,
    timeout_sec: int = 20,
) -> Dict[str, List[str]]:
    prompt = (
        "Given this Indian legal issue, list the most relevant laws for retrieval.\n"
        "Return ONLY valid JSON with this schema:\n"
        "{\n"
        '  "relevant_laws": ["law 1", "law 2"],\n'
        '  "preferred_laws": ["law 1"],\n'
        '  "disallowed_law_hints": ["irrelevant law hint"]\n'
        "}\n"
        "Rules:\n"
        "- Keep lists short and precise.\n"
        "- Focus on Indian laws only.\n"
        "- If state is not mentioned, prefer central laws and avoid state-specific rent laws.\n\n"
        f"User query: {user_query}\n"
        f"Detected domain: {structured_query.get('domain', 'general')}\n"
        f"Detected intent: {structured_query.get('intent', 'legal_query')}\n"
    )
    raw = call_llm(model_name=model_name, prompt=prompt, timeout_sec=timeout_sec)
    parsed: Dict[str, Any] = {}
    if raw and not raw.startswith("[ERROR]"):
        try:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(raw[start : end + 1])
        except Exception:
            parsed = {}

    relevant_laws = [str(x).strip() for x in parsed.get("relevant_laws", []) if str(x).strip()]
    preferred_laws = [str(x).strip() for x in parsed.get("preferred_laws", []) if str(x).strip()]
    disallowed_law_hints = [str(x).strip() for x in parsed.get("disallowed_law_hints", []) if str(x).strip()]
    relevant_laws = [_clean_law_name(x) for x in relevant_laws if _clean_law_name(x)]
    preferred_laws = [_clean_law_name(x) for x in preferred_laws if _clean_law_name(x)]
    disallowed_law_hints = [_clean_law_name(x) for x in disallowed_law_hints if _clean_law_name(x)]

    q = (user_query or "").lower()
    if structured_query.get("domain") == "property" and any(
        term in q for term in ["landlord", "tenant", "lease", "rent", "deposit", "security deposit", "vacated"]
    ):
        relevant_keys = [_canonical_law_key(x) for x in relevant_laws]
        preferred_keys = [_canonical_law_key(x) for x in preferred_laws]
        for law in ["transfer of property act", "indian contract act", "specific relief act"]:
            if law not in relevant_keys:
                relevant_laws.append(law)
                relevant_keys.append(law)
        for law in ["transfer of property act", "indian contract act", "specific relief act"]:
            if law not in preferred_keys:
                preferred_laws.append(law)
                preferred_keys.append(law)
        preferred_laws = [x for x in preferred_laws if "consumer protection act" not in _canonical_law_key(x)]
        if not _query_mentions_specific_state(user_query):
            for hint in GENERIC_STATE_RENT_HINTS:
                if hint not in [x.lower() for x in disallowed_law_hints]:
                    disallowed_law_hints.append(hint)

    if _is_cyber_it_act_query(user_query, structured_query):
        relevant_keys = [_canonical_law_key(x) for x in relevant_laws]
        preferred_keys = [_canonical_law_key(x) for x in preferred_laws]

        cyber_laws = [
            "information technology act",
            "bharatiya nyaya sanhita",
            "bharatiya nagrik suraksha sanhita",
        ]
        for law in cyber_laws:
            if law not in relevant_keys:
                relevant_laws.append(law)
                relevant_keys.append(law)
        if "information technology act" not in preferred_keys:
            preferred_laws.insert(0, "information technology act")
            preferred_keys.insert(0, "information technology act")

        # Cyber queries should not drift into unrelated civil statutes.
        for hint in ["transfer of property act", "specific relief act", "consumer protection act"]:
            if hint not in [x.lower() for x in disallowed_law_hints]:
                disallowed_law_hints.append(hint)

    return {
        "relevant_laws": relevant_laws[:8],
        "preferred_laws": preferred_laws[:5],
        "disallowed_law_hints": disallowed_law_hints[:8],
    }


def _result_score(item: Dict[str, Any]) -> float:
    return float(item.get("final_score", item.get("hybrid_score", 0.0)) or 0.0)


def _result_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    trace = item.get("retrieval_trace") or {}
    return {
        "corpus": item.get("corpus"),
        "title": item.get("title"),
        "document_id": item.get("document_id"),
        "section_number": item.get("section_number"),
        "context_path": item.get("context_path"),
        "chunk_id": item.get("chunk_id"),
        "score": round(_result_score(item), 4),
        "dense_score": round(float(item.get("dense_score", 0.0) or 0.0), 4),
        "bm25_score": round(float(item.get("bm25_score", 0.0) or 0.0), 4),
        "dense_weight_used": round(float(item.get("dense_weight_used", 0.0) or 0.0), 4),
        "bm25_weight_used": round(float(item.get("bm25_weight_used", 0.0) or 0.0), 4),
        "query_profile": item.get("query_profile"),
        "rerank_score": item.get("rerank_score"),
        "rerank_raw_score": item.get("rerank_raw_score"),
        "retrieval_ms": {
            "dense_ms": trace.get("dense_ms"),
            "bm25_ms": trace.get("bm25_ms"),
            "fusion_ms": trace.get("fusion_ms"),
            "total_ms": trace.get("total_ms"),
        },
        "text_preview": str(item.get("chunk_text") or "")[:200],
    }


def _apply_result_quality_controls(
    results: List[Dict[str, Any]],
    allowed_docs: set[str],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Apply lightweight quality controls while preserving hybrid/rerank signals."""
    kept: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for item in results:
        adjusted = dict(item)
        log_notes: List[str] = []
        corpus = str(adjusted.get("corpus") or "").strip().lower()

        # Corpus type mismatch remains the only hard rejection.
        if corpus not in allowed_docs:
            log_notes.append(f"rejected_doc_type:{corpus or 'unknown'}")
            rejected.append({**_result_summary(adjusted), "reasons": log_notes})
            continue

        base_score = float(adjusted.get("final_score", adjusted.get("hybrid_score", 0.0)) or 0.0)
        dense_score = float(adjusted.get("dense_score", 0.0) or 0.0)
        bm25_score = float(adjusted.get("bm25_score", 0.0) or 0.0)
        rerank_score = adjusted.get("rerank_score")
        query_profile = str(adjusted.get("query_profile") or "").strip().lower()

        # Diagnostic notes only.
        if bm25_score == 0.0:
            log_notes.append("bm25_zero")
        if dense_score < 0.15:
            log_notes.append("weak_dense")

        if rerank_score is not None:
            rr = float(rerank_score or 0.0)
            if query_profile == "precise":
                quality_score = (0.55 * base_score) + (0.45 * rr)
            elif query_profile == "explanatory":
                quality_score = (0.75 * base_score) + (0.25 * rr)
            else:
                quality_score = (0.65 * base_score) + (0.35 * rr)
        else:
            quality_score = base_score

        adjusted["quality_score"] = quality_score
        adjusted["final_score"] = quality_score
        adjusted["hybrid_score"] = max(float(adjusted.get("hybrid_score", 0.0) or 0.0), quality_score)
        if log_notes:
            adjusted["quality_notes"] = log_notes
        kept.append(adjusted)

    kept.sort(key=_result_score, reverse=True)
    return kept, rejected


def retrieve_for_queries(
    queries: List[str],
    base_args: SimpleNamespace,
    allowed_docs: set[str],
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    result_sets: List[List[Dict[str, Any]]] = []
    debug_runs: List[Dict[str, Any]] = []

    for query in queries[:MAX_RETRIEVAL_QUERIES]:
        args = SimpleNamespace(**vars(base_args))
        args.q = query
        raw_results = run_retrieval(args)
        filtered_results, rejected_results = _apply_result_quality_controls(raw_results, allowed_docs)
        result_sets.append(filtered_results)
        debug_runs.append(
            {
                "query": query,
                "retrieved_chunks": [_result_summary(item) for item in raw_results],
                "filtered_chunks": [_result_summary(item) for item in filtered_results],
                "rejected_chunks": rejected_results,
                "stage_metrics": (raw_results[0].get("retrieval_trace") if raw_results else {}),
            }
        )

    merged = merge_retrieval_results(result_sets, top_k=base_args.top_k)
    merged_scores = [float(item.get("final_score", item.get("hybrid_score", 0.0)) or 0.0) for item in merged]
    summary = {
        "expanded_queries": queries[:MAX_RETRIEVAL_QUERIES],
        "runs": debug_runs,
        "summary": {
            "queries_executed": len(debug_runs),
            "merged_count": len(merged),
            "max_score": max(merged_scores) if merged_scores else 0.0,
            "avg_score": (sum(merged_scores) / len(merged_scores)) if merged_scores else 0.0,
        },
    }
    return merged, summary


def retrieve_with_keyword_fallback(
    user_query: str,
    base_args: SimpleNamespace,
    allowed_docs: set[str],
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    q = (user_query or "").lower()
    keyword_queries: List[str] = []

    if any(term in q for term in ["deposit", "security deposit"]):
        keyword_queries.append("deposit tenant refund")
    if any(term in q for term in ["landlord", "tenant"]):
        keyword_queries.append("landlord tenant refund")
    if any(term in q for term in ["lease", "vacated", "vacate"]):
        keyword_queries.append("lease vacated deposit refund")

    if not keyword_queries:
        tokens = [tok for tok in re.findall(r"[a-z0-9]{4,}", q) if tok not in {"what", "india", "legal", "remedy"}]
        keyword_queries.append(" ".join(tokens[:3]) or q)

    keyword_queries = keyword_queries[:3]
    fallback_args = SimpleNamespace(**vars(base_args))
    fallback_args.rerank = False
    fallback_args.top_k = max(getattr(base_args, "top_k", 5), 5)
    fallback_args.section_filter = None
    results, debug = retrieve_for_queries(keyword_queries, fallback_args, allowed_docs)
    debug["fallback"] = True
    return results, debug


def _build_user_mode_response(base: QueryResponse) -> UserModeResponse:
    if not base.answer or "Insufficient legal context found" in base.answer:
        return UserModeResponse(
            ok=base.ok,
            query=base.query,
            summary=base.answer or "I could not find enough legal material to answer reliably.",
            what_you_can_do=[],
            legal_options=[],
            notes="Share more facts, agreement terms, dates, amounts, and location for a stronger answer.",
            meta=base.meta,
        )

    sections = _parse_answer_sections(base.answer)
    legal_options = _extract_numbered_items(sections.get("rule", ""))
    if not legal_options:
        legal_options = [line for line in sections.get("rule", "").splitlines() if line.strip()]
    steps = _extract_numbered_items(sections.get("application", ""))
    summary_parts = []
    if legal_options:
        summary_parts.append("Possible legal basis: " + "; ".join(legal_options[:3]))
    if steps:
        summary_parts.append("Best next move: " + steps[0])
    summary = " ".join(summary_parts).strip() or sections.get("application") or base.answer
    return UserModeResponse(
        ok=base.ok,
        query=base.query,
        summary=summary,
        what_you_can_do=steps[:5],
        legal_options=legal_options[:5],
        notes=sections.get("conclusion") or sections.get("disclaimer") or "",
        meta=base.meta,
    )


def _generate_lawyer_init_payload(
    user_query: str,
    structured_query: Dict[str, Any],
    law_focus: Dict[str, List[str]],
    model_name: str,
    timeout_sec: int,
) -> Dict[str, Any]:
    domain = str(structured_query.get("domain", "general")).lower()
    prompt = (
        "You are assisting a lawyer in issue-spotting under Indian law.\n"
        "Return ONLY valid JSON with this schema:\n"
        "{\n"
        '  "facts": "short fact summary",\n'
        '  "issues": ["issue 1", "issue 2"],\n'
        '  "legal_pathways": [\n'
        "    {\n"
        '      "law": "Real Indian law only",\n'
        '      "applicability": "high|medium|low",\n'
        '      "reason": "why it may apply",\n'
        '      "conditions_needed": ["fact 1", "fact 2"]\n'
        "    }\n"
        "  ],\n"
        '  "questions": [\n'
        "    {\n"
        '      "question": "question text",\n'
        '      "affects": ["law name from legal_pathways"]\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- Only use real Indian laws.\n"
        "- Do not invent law names.\n"
        "- Give top 3 to 5 legal pathways.\n"
        "- Given the following case facts and legal pathways, generate 3 to 5 clarification questions.\n"
        "- Questions MUST relate ONLY to these pathways.\n"
        "- Each question must help confirm or eliminate a pathway.\n"
        f"- Domain lock: {domain}.\n"
        f"- Forbidden question terms for this domain: {json.dumps(_domain_forbidden_terms(domain), ensure_ascii=False)}.\n"
        f"- Allowed domain vocabulary for this domain: {json.dumps(_domain_allowed_terms(domain), ensure_ascii=False)}.\n"
        "- Do not introduce unrelated domains.\n"
        "- Do not give final advice yet.\n\n"
        f"User query: {user_query}\n"
        f"Structured query: {json.dumps(structured_query, ensure_ascii=False)}\n"
        f"Relevant laws: {json.dumps(law_focus, ensure_ascii=False)}\n"
    )
    parsed = _extract_json_object(call_llm(model_name=model_name, prompt=prompt, timeout_sec=timeout_sec))
    issues = _coerce_string_list(parsed.get("issues"))
    questions_raw = parsed.get("questions") if isinstance(parsed.get("questions"), list) else []
    legal_pathways = parsed.get("legal_pathways") if isinstance(parsed.get("legal_pathways"), list) else []
    cleaned_pathways: List[Dict[str, Any]] = []
    for pathway in legal_pathways[:5]:
        if not isinstance(pathway, dict):
            continue
        law = _clean_law_name(pathway.get("law", ""))
        if not law:
            continue
        cleaned_pathways.append(
            {
                "law": law,
                "applicability": str(pathway.get("applicability", "medium")).strip().lower() or "medium",
                "reason": str(pathway.get("reason", "")).strip(),
                "conditions_needed": _coerce_string_list(pathway.get("conditions_needed")),
            }
        )
    if not cleaned_pathways:
        cleaned_pathways = [
            {
                "law": law,
                "applicability": "medium",
                "reason": "Preliminary pathway based on the reported facts.",
                "conditions_needed": ["Further agreement and payment facts"],
            }
            for law in law_focus.get("preferred_laws", [])[:3]
        ]
    questions = _filter_lawyer_questions(questions_raw, domain=domain, legal_pathways=cleaned_pathways)
    if not questions:
        fallback_questions = [
            {
                "question": "Was there a written agreement or contract supporting the claim?",
                "affects": [cleaned_pathways[0]["law"]] if cleaned_pathways else [],
            },
            {
                "question": "Do you have documentary proof supporting payment, salary, wages, or the disputed amount?",
                "affects": [cleaned_pathways[0]["law"]] if cleaned_pathways else [],
            },
            {
                "question": "Has the other side stated any damage, deduction, misconduct, or breach justification?",
                "affects": [cleaned_pathways[0]["law"]] if cleaned_pathways else [],
            },
        ]
        questions = _filter_lawyer_questions(fallback_questions, domain=domain, legal_pathways=cleaned_pathways)
    if not questions:
        questions = [
            {
                "id": "q1",
                "text": "Please share the agreement, documentary proof, and the stated reason for refusal, deduction, or termination.",
                "affects": [cleaned_pathways[0]["law"]] if cleaned_pathways else [],
            }
        ]
    return {
        "facts": str(parsed.get("facts") or "; ".join(structured_query.get("facts", [])[:3]) or user_query).strip(),
        "issues": issues[:5] or [structured_query.get("domain", "general")],
        "legal_pathways": cleaned_pathways[:5],
        "questions": questions[:5],
    }


def _build_lawyer_retrieval_inputs(session: Dict[str, Any], answers: Dict[str, str]) -> tuple[List[str], Dict[str, List[str]], Dict[str, Any]]:
    user_query = session.get("query", "")
    structured_query = session.get("structured_query", {})
    law_focus = session.get("law_focus", {})
    answer_lines = [f"{qid}: {value}" for qid, value in answers.items() if str(value).strip()]
    combined_text = user_query + ("\n" + "\n".join(answer_lines) if answer_lines else "")
    refined_structured = dict(structured_query)
    refined_structured["facts"] = list(structured_query.get("facts", [])) + answer_lines
    retrieval_queries = generate_retrieval_queries(
        user_query=combined_text,
        structured_query=refined_structured,
        dense_query=build_query(combined_text).expanded_query,
        rewritten_query=combined_text,
        model_name=session.get("llm_model", DEFAULT_BEDROCK_MODEL_ID),
        timeout_sec=min(int(session.get("llm_timeout_sec", 300)), 20),
    )
    return retrieval_queries, law_focus, refined_structured


def _generate_lawyer_final_analysis(
    session: Dict[str, Any],
    answers: Dict[str, str],
    context_blocks: List[Dict[str, Any]],
    model_name: str,
    timeout_sec: int,
) -> Dict[str, Any]:
    q_lookup = {q["id"]: q["text"] for q in session.get("questions", []) if isinstance(q, dict)}
    answer_lines = [f"{q_lookup.get(qid, qid)}: {value}" for qid, value in answers.items() if str(value).strip()]
    prompt = (
        "You are preparing a lawyer-mode preliminary applicability analysis under Indian law.\n"
        "Return ONLY valid JSON with this schema:\n"
        "{\n"
        '  "applicable_laws": [{"law": "...", "reason": "...", "confidence": "high|medium|low"}],\n'
        '  "rejected_laws": [{"law": "...", "reason": "..."}],\n'
        '  "question_impact": [{"question_id": "q1", "law": "...", "effect": "increase|decrease|neutral", "reason": "..."}],\n'
        '  "reasoning": ["point 1", "point 2"],\n'
        '  "next_steps": ["step 1", "step 2"],\n'
        '  "summary": "short analysis"\n'
        "}\n"
        "Rules:\n"
        "- Only use real Indian laws.\n"
        "- Distinguish clearly between applicable and not-yet-applicable laws.\n"
        "- If facts are incomplete, say so in reasoning.\n"
        "- Use only the provided legal context when citing authorities.\n\n"
        f"Original query: {session.get('query', '')}\n"
        f"Questions and answers: {json.dumps(answer_lines, ensure_ascii=False)}\n"
        f"Initial pathways: {json.dumps(session.get('legal_pathways', []), ensure_ascii=False)}\n"
        f"Retrieved legal context:\n{build_context_text(context_blocks)}\n"
    )
    parsed = _extract_json_object(call_llm(model_name=model_name, prompt=prompt, timeout_sec=timeout_sec))
    applicable = parsed.get("applicable_laws") if isinstance(parsed.get("applicable_laws"), list) else []
    rejected = parsed.get("rejected_laws") if isinstance(parsed.get("rejected_laws"), list) else []
    question_impact = parsed.get("question_impact") if isinstance(parsed.get("question_impact"), list) else []
    return {
        "summary": str(parsed.get("summary", "")).strip(),
        "applicable_laws": applicable[:6],
        "rejected_laws": rejected[:6],
        "question_impact": [item for item in question_impact[:20] if isinstance(item, dict)],
        "reasoning": _coerce_string_list(parsed.get("reasoning"))[:8],
        "next_steps": _coerce_string_list(parsed.get("next_steps"))[:5],
        "citations": [
            {
                "title": block.get("title"),
                "section_number": block.get("section_number"),
                "corpus": block.get("corpus"),
            }
            for block in context_blocks[:6]
        ],
    }


def append_query_log(entry: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    records: List[Dict[str, Any]] = []
    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                records = loaded[-199:]
        except Exception:
            records = []
    records.append(entry)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records[-200:], f, ensure_ascii=False, indent=2)


def build_authority_summary(context_blocks: List[Dict[str, Any]]) -> str:
    authorities: Dict[str, set[str]] = {}
    for block in context_blocks:
        title = str(block.get("title") or "").strip()
        section = str(block.get("section_number") or "").strip()
        if not title:
            continue
        authorities.setdefault(title, set())
        if section:
            authorities[title].add(section)

    if not authorities:
        return ""

    lines = ["Retrieved Authorities:"]
    for title, sections in authorities.items():
        if sections:
            section_list = ", ".join(sorted(sections, key=lambda x: (len(x), x)))
            lines.append(f"- {title}, Section {section_list}")
        else:
            lines.append(f"- {title}")
    return "\n".join(lines)


def _allowed_section_numbers(context_blocks: List[Dict[str, Any]]) -> List[str]:
    sections = []
    for block in context_blocks:
        sec = str(block.get("section_number") or "").strip()
        if sec and sec not in sections:
            sections.append(sec)
    return sections


def _build_grounding_repair_prompt(original_prompt: str, invalid_sections: List[str], allowed_sections: List[str]) -> str:
    allowed = ", ".join(allowed_sections) if allowed_sections else "none"
    invalid = ", ".join(invalid_sections) if invalid_sections else "none"
    return (
        f"{original_prompt}\n\n"
        "IMPORTANT GROUNDING FIX:\n"
        f"- You used disallowed section references: {invalid}\n"
        f"- You may use ONLY these section numbers: {allowed}\n"
        "- If exact section support is insufficient, keep the answer general and do not add new section numbers.\n"
        "- Rewrite the full answer in the required format.\n"
    )


def _build_context_grounded_fallback(user_query: str, context_blocks: List[Dict[str, Any]]) -> str:
    act_authorities = []
    judgement_authorities = []
    seen = set()
    for block in context_blocks:
        title = _display_law_name(str(block.get("title") or "")).strip()
        sec = str(block.get("section_number") or "").strip()
        corpus = str(block.get("corpus") or "").strip().lower()
        if not title:
            continue
        key = (corpus, title, sec)
        if key in seen:
            continue
        seen.add(key)
        if corpus == "judgements":
            if _is_placeholder_judgement_title(title):
                continue
            judgement_authorities.append(f"- **{title}**")
        else:
            act_authorities.append(f"- **{title}**, Section {sec}" if sec else f"- **{title}**")

    snippets = []
    for block in context_blocks[:3]:
        txt = str(((block.get("texts") or {}).get("chunk_text") or "")).strip()
        if txt:
            snippets.append(txt[:280].strip())

    rule_lines = []
    if act_authorities:
        rule_lines.append("Relevant Acts and Sections:")
        rule_lines.extend(act_authorities)
    if judgement_authorities:
        if rule_lines:
            rule_lines.append("")
        rule_lines.append("Relevant Judgements:")
        rule_lines.extend(judgement_authorities)
    if not rule_lines:
        rule_lines.append("No specific statute or judgement was identified with high confidence from the retrieved context.")

    if snippets:
        rule_lines.append("")
        rule_lines.append("Context Notes:")
        rule_lines.extend(f"- {s}" for s in snippets)

    application = (
        "1. File a written complaint with the local Cyber Crime Police Station or portal with all digital evidence.\n"
        "2. Preserve logs, emails, screenshots, and account access history to support investigation.\n"
        "3. Consult an Indian legal professional for case-specific drafting and forum strategy."
    )
    conclusion = (
        "Based on the available context, there appears to be a legally actionable grievance under the cited authorities. "
        "Immediate preservation of evidence and filing before the correct forum are critical to protect limitation periods."
    )
    return (
        "**Part 1 - Facts**\n"
        f"- User query summary: {user_query.strip()}\n\n"
        "**Part 2 - Issue**\n"
        "- Which Indian legal rights/remedies are triggered on these facts?\n\n"
        "**Part 3 - Rule**\n"
        f"{chr(10).join(rule_lines)}\n\n"
        "**Part 4 - Application**\n"
        f"{application}\n\n"
        "**Part 5 - Conclusion**\n"
        f"{conclusion}\n\n"
        "**Disclaimer**\n"
        "For information only. Consult a professional."
    )

def get_static_greeting(text: str) -> Optional[str]:
    clean = text.lower().strip("?!. ")
    greetings = {"hi", "hello", "hey", "hi there", "hello there", "namaste"}
    acknowledgements = {
        "ok",
        "okay",
        "ok thanks",
        "okay thanks",
        "thanks",
        "thank you",
        "thx",
        "got it",
        "understood",
        "noted",
        "fine",
        "alright",
        "all right",
        "sure",
    }
    if clean in greetings:
        return f"{text.strip()}! I am your Legal AI assistant. How can I help you today?"
    if clean in acknowledgements:
        return "Understood. If you want, I can explain the last answer, help with a new legal question, or draft the next step."
    if any(h in clean for h in ["good morning", "good afternoon", "good evening"]):
        return f"{text.strip()}! How can I assist you with your legal research today?"
    return None


def _bold_authorities(answer: str, context_blocks: List[Dict[str, Any]]) -> str:
    act_titles = []
    for block in context_blocks:
        if block.get("corpus") != "acts":
            continue
        title = (block.get("title") or "").strip()
        if title and title not in act_titles:
            act_titles.append(title)

    for title in sorted(act_titles, key=len, reverse=True):
        pattern = rf"(?<!\*)\b{re.escape(title)}\b(?!\*)"
        answer = re.sub(pattern, f"**{title}**", answer)
    return answer


def _strip_context_markers(answer: str) -> str:
    answer = re.sub(r"\s*\[C\d+\]", "", answer, flags=re.IGNORECASE)
    answer = re.sub(r"\(\s*\)", "", answer)
    answer = re.sub(r",\s*(?=\n|$)", "", answer)
    answer = re.sub(r"[ \t]{2,}", " ", answer)
    return answer


def _sanitize_section_artifacts(answer: str) -> str:
    # Fix malformed section references generated by the model.
    answer = re.sub(r"\bSection\s+s\s+(\d+[A-Z]?)", r"Sections \1", answer, flags=re.IGNORECASE)
    answer = re.sub(r"\bSections?\s+(\d+[A-Z]?)\*\*", r"Section \1", answer, flags=re.IGNORECASE)
    answer = re.sub(r"\bSection\s*\.\s*$", "", answer, flags=re.IGNORECASE | re.MULTILINE)
    answer = re.sub(r"(?m)^([^\n-][^\n]*?)\s*-\s*$", r"\1", answer)
    answer = re.sub(r"\*\*(?=[\s.,;:])", "", answer)
    return answer


def _normalize_heading_breaks(answer: str) -> str:
    headings = [
        "Facts",
        "Issue",
        "Rule",
        "Application",
        "Conclusion",
        "Disclaimer",
        "Part 1 - Facts",
        "Part 2 - Issue",
        "Part 3 - Rule",
        "Part 4 - Application",
        "Part 5 - Conclusion",
        "Part 6 - Disclaimer",
    ]
    for heading in headings:
        answer = re.sub(
            rf"(?<!\n)(\*\*{re.escape(heading)}\*\*)",
            r"\n\n\1",
            answer,
        )
        answer = re.sub(
            rf"(?<!\n)({re.escape(heading)})(?=\n|:| )",
            r"\n\n\1",
            answer,
        )
    answer = re.sub(r"\n{3,}", "\n\n", answer)
    return answer.strip()


def _remove_existing_disclaimer_sections(answer: str) -> str:
    patterns = [
        r"(?ms)\n*\*\*Part 6 - Disclaimer\*\*\s*\n.*$",
        r"(?ms)\n*\*\*Disclaimer\*\*\s*\n.*$",
        r"(?ms)\n*Part 6 - Disclaimer\s*:?\s*\n.*$",
        r"(?ms)\n*Disclaimer\s*:?\s*\n.*$",
        r"(?ms)\n*---\s*\n\*\*Part 6 - Disclaimer\*\*\s*\n.*$",
        r"(?ms)\n*---\s*\n\*\*Disclaimer\*\*\s*\n.*$",
    ]
    trimmed = answer
    for pattern in patterns:
        trimmed = re.sub(pattern, "", trimmed)
    return trimmed.strip()


def _bold_headings(answer: str) -> str:
    heading_map = {
        "Facts": "Part 1 - Facts",
        "Issue": "Part 2 - Issue",
        "Applicable Law": "Part 3 - Rule",
        "Rule": "Part 3 - Rule",
        "How It Applies": "Part 4 - Application",
        "Analysis": "Part 4 - Application",
        "Next Steps": "Part 4 - Application",
        "Application": "Part 4 - Application",
        "Limits": "Part 5 - Conclusion",
        "Conclusion": "Part 5 - Conclusion",
        "Disclaimer": "Disclaimer",
        "Part 1 - Facts and Legal Issue": "Part 1 - Facts",
        "Part 1 - Acts, Sections and Judgements": "Part 3 - Rule",
        "Part 2 - Applicable Law": "Part 3 - Rule",
        "Part 2 - Exact Steps to Follow": "Part 4 - Application",
        "Part 3 - Analysis": "Part 4 - Application",
        "Part 3 - Limits": "Part 5 - Conclusion",
        "Part 4 - Remedies and Next Steps": "Part 4 - Application",
        "Part 4 - Disclaimer": "Disclaimer",
        "Part 5 - Limits": "Part 5 - Conclusion",
        "Part 6 - Disclaimer": "Disclaimer",
        "Part 1 - Facts": "Part 1 - Facts",
        "Part 2 - Issue": "Part 2 - Issue",
        "Part 3 - Rule": "Part 3 - Rule",
        "Part 4 - Application": "Part 4 - Application",
        "Part 5 - Conclusion": "Part 5 - Conclusion",
    }
    for heading, canonical in heading_map.items():
        answer = re.sub(
            rf"(?m)^\s*\**{re.escape(heading)}\**\s*:\s*$",
            f"**{canonical}**",
            answer,
        )
        answer = re.sub(
            rf"(?m)^\s*\**{re.escape(heading)}\**\s*$",
            f"**{canonical}**",
            answer,
        )
    return answer


def _rebuild_applicable_law(
    answer: str,
    context_blocks: List[Dict[str, Any]],
    suggested_laws: Optional[List[str]] = None,
) -> str:
    authorities: Dict[str, set[str]] = {}
    judgements: List[str] = []
    for block in context_blocks:
        title = _display_law_name(str(block.get("title") or ""))
        section = str(block.get("section_number") or "").strip()
        corpus = str(block.get("corpus") or "").strip().lower()
        if not title:
            continue
        if corpus == "judgements":
            if _is_placeholder_judgement_title(title):
                continue
            if title not in judgements:
                judgements.append(title)
            continue
        authorities.setdefault(title, set())
        if section:
            authorities[title].add(section)

    fallback_laws = [law for law in (suggested_laws or []) if str(law).strip()]
    if not authorities and not judgements and not fallback_laws:
        return answer

    lines = []
    if authorities:
        lines.append("Applicable Acts and Sections:")
        for title, sections in authorities.items():
            if sections:
                for section in sorted(sections, key=lambda x: (len(x), x)):
                    lines.append(f"- **{title}**, Section {section}")
            else:
                lines.append(f"- **{title}**")
    elif fallback_laws:
        lines.append("Likely Applicable Laws:")
        for law in fallback_laws:
            display = _display_law_name(law)
            if display:
                lines.append(f"- **{display}**")

    if judgements:
        if lines:
            lines.append("")
        lines.append("Relevant Judgements:")
        lines.extend(f"- **{title}**" for title in judgements)
    applicable_body = "\n".join(lines)

    pattern = re.compile(
        r"(?ms)(^\*\*Part 3 - Rule\*\*\s*\n)(.*?)(?=^\*\*[A-Za-z0-9][A-Za-z0-9\s/\-]+\*\*\s*$|\Z)"
    )
    match = pattern.search(answer)
    if match:
        return answer[:match.start()] + match.group(1) + applicable_body + "\n\n" + answer[match.end():]

    return f"**Part 3 - Rule**\n{applicable_body}\n\n{answer}".strip()


def _align_section_references(answer: str, context_blocks: List[Dict[str, Any]]) -> str:
    sections = sorted(
        {
            str(block.get("section_number") or "").strip()
            for block in context_blocks
            if str(block.get("section_number") or "").strip()
        },
        key=lambda x: (len(x), x),
    )
    if len(sections) != 1:
        return answer

    allowed_section = sections[0]
    answer = re.sub(r"\bSections?\s+\d+[A-Z]?(?:\s*,\s*\d+[A-Z]?)+", f"Section {allowed_section}", answer)
    answer = re.sub(r"\bSection\s+\d+[A-Z]?\b", f"Section {allowed_section}", answer)
    return answer


def _dedupe_disclaimer(answer: str) -> str:
    answer = re.sub(r"(?ms)\n*---\n\*\*Part 6 - Disclaimer\*\*\s*\nFor information only\. Consult a professional\.\s*$", "", answer)
    answer = re.sub(r"(?ms)\n*---\n\*\*Disclaimer\*\*\s*:?\s*\nFor information only\. Consult a professional\.\s*$", "", answer)
    answer = re.sub(r"(?ms)\n*\*\*Part 6 - Disclaimer\*\*\s*\nFor information only\. Consult a professional\.\s*$", "", answer)
    answer = re.sub(r"(?ms)\n*\*\*Disclaimer\*\*\s*\nFor information only\. Consult a professional\.\s*$", "", answer)
    answer = re.sub(r"(?ms)\n*Part 6 - Disclaimer:\s*For information only\. Consult a professional\.\s*$", "", answer)
    answer = re.sub(r"(?ms)\n*Disclaimer:\s*For information only\. Consult a professional\.\s*$", "", answer)
    return answer.strip()


def _query_mentions_specific_state(user_query: str) -> bool:
    q = (user_query or "").lower()
    return any(term in q for term in INDIAN_STATE_TERMS)


def _is_state_specific_result(item: Dict[str, Any]) -> bool:
    hay = " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("document_id") or ""),
            str(item.get("context_path") or ""),
            str(item.get("source_json") or ""),
            str(item.get("chunk_text") or ""),
            str(item.get("court") or ""),
        ]
    ).lower()
    return any(term in hay for term in INDIAN_STATE_TERMS)


def _filter_state_specific_results(user_query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not results or _query_mentions_specific_state(user_query):
        return results

    filtered = [item for item in results if not _is_state_specific_result(item)]
    return filtered


def _normalize_markdown_layout(answer: str) -> str:
    formatted = answer.replace("\r\n", "\n").strip()

    # Put markdown structural markers on their own lines.
    formatted = re.sub(r"\s+(?=#{1,6}\s)", "\n\n", formatted)
    formatted = re.sub(r"\s+(?=>\s)", "\n", formatted)
    formatted = re.sub(r"\s+(?=---)", "\n\n", formatted)
    formatted = re.sub(r"(?<!\n)(---)", r"\n\n\1", formatted)
    formatted = re.sub(r"(---)(?!\n)", r"\1\n", formatted)
    formatted = re.sub(
        r"\s+(?=(\*\*(?:Section|Official Statutory Text|Legal Answer|Quick Pillars|Facts|Issue|Rule|Application|Conclusion|Disclaimer|Applicable Law|How It Applies|Next Steps|Limits)\*\*))",
        "\n\n",
        formatted,
    )

    # Keep the common "Quick Pillars" fields readable.
    formatted = re.sub(r"(?m)^\s*Actor:\s*", "- **Actor**: ", formatted)
    formatted = re.sub(r"(?m)^\s*Offense:\s*", "- **Offense**: ", formatted)
    formatted = re.sub(r"(?m)^\s*Offence:\s*", "- **Offence**: ", formatted)
    formatted = re.sub(r"(?m)^\s*Penalty:\s*", "- **Penalty**: ", formatted)
    formatted = re.sub(r"\s+\|\s+", "\n", formatted)

    # If the model emits inline markdown headings, separate them.
    formatted = re.sub(r"(?<!\n)(#{1,6}\s)", r"\n\n\1", formatted)
    formatted = re.sub(r"\n{3,}", "\n\n", formatted)
    return formatted.strip()


def _format_next_steps_section(answer: str) -> str:
    pattern = re.compile(
        r"(?ms)(^\*\*Part 4 - Application\*\*\s*\n)(.*?)(?=^\*\*[A-Za-z0-9][A-Za-z0-9\s/\-]+\*\*\s*$|\Z)"
    )
    match = pattern.search(answer)
    if not match:
        return answer

    body = match.group(2).strip()
    if not body:
        return answer

    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    items = []
    for line in lines:
        cleaned = re.sub(r"^[-*•]\s*", "", line)
        cleaned = re.sub(r"^\d+\.\s*", "", cleaned)
        if cleaned:
            items.append(cleaned)

    if not items:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body) if s.strip()]
        items = sentences

    numbered = "\n".join(f"{idx}. {item}" for idx, item in enumerate(items, start=1))
    return answer[:match.start()] + match.group(1) + numbered + "\n\n" + answer[match.end():]


def _enforce_firac_layout(answer: str) -> str:
    normalized = (answer or "").replace("\r\n", "\n").strip()
    if not normalized:
        return normalized

    # Ensure Part headings start on their own line even if the model emits inline prose.
    heading_token = r"(?:\*\*)?Part\s*[1-6]\s*-\s*(?:Facts|Issue|Rule|Application|Conclusion|Disclaimer)(?:\*\*)?"
    normalized = re.sub(rf"(?<!\n)(?={heading_token})", "\n\n", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()

    part_pattern = re.compile(
        r"(?ims)(?:\*\*)?Part\s*([1-6])\s*-\s*(Facts|Issue|Rule|Application|Conclusion|Disclaimer)(?:\*\*)?\s*:?\s*"
        r"(.*?)(?=(?:\n|\A)\s*(?:\*\*)?Part\s*[1-6]\s*-\s*(?:Facts|Issue|Rule|Application|Conclusion|Disclaimer)"
        r"(?:\*\*)?\s*:?\s*|\Z)"
    )

    extracted: Dict[int, str] = {}
    for match in part_pattern.finditer(normalized):
        idx = int(match.group(1))
        body = match.group(3).strip()
        if idx not in extracted:
            extracted[idx] = body
        elif body:
            extracted[idx] = (extracted[idx] + "\n" + body).strip()

    if not extracted:
        return normalized

    # Backfill from legacy parser if any part was not captured by the strict regex.
    parsed = _parse_answer_sections(normalized)
    fallback = {
        1: parsed.get("facts", ""),
        2: parsed.get("issue", ""),
        3: parsed.get("rule", ""),
        4: parsed.get("application", ""),
        5: parsed.get("conclusion", ""),
        6: parsed.get("disclaimer", ""),
    }
    for idx in range(1, 7):
        if idx not in extracted and fallback.get(idx):
            extracted[idx] = fallback[idx].strip()

    if not any(extracted.get(i, "").strip() for i in range(1, 7)):
        return normalized

    ordered_headings = {
        1: "Part 1 - Facts",
        2: "Part 2 - Issue",
        3: "Part 3 - Rule",
        4: "Part 4 - Application",
        5: "Part 5 - Conclusion",
        6: "Disclaimer",
    }

    parts: List[str] = []
    for idx in range(1, 7):
        body = (extracted.get(idx) or "").strip()
        if not body and idx == 6:
            body = "For information only. Consult a professional."
        if not body:
            continue
        parts.append(f"**{ordered_headings[idx]}**\n{body}")

    if not parts:
        return normalized
    return "\n\n".join(parts).strip()


def format_final_answer(
    answer: str,
    context_blocks: List[Dict[str, Any]],
    suggested_laws: Optional[List[str]] = None,
) -> str:
    formatted = _remove_existing_disclaimer_sections(answer)
    formatted = _normalize_markdown_layout(formatted)
    formatted = _strip_context_markers(formatted)
    formatted = _sanitize_section_artifacts(formatted)
    formatted = _align_section_references(formatted, context_blocks)
    formatted = _bold_headings(formatted)
    formatted = _bold_authorities(formatted, context_blocks)
    formatted = _rebuild_applicable_law(formatted, context_blocks, suggested_laws=suggested_laws)
    formatted = _normalize_heading_breaks(formatted)
    formatted = _format_next_steps_section(formatted)
    formatted = _enforce_firac_layout(formatted)
    formatted = re.sub(r"(?m)^Disclaimer\s+(?=For information only\.)", "**Disclaimer**\n", formatted)
    formatted = re.sub(r"(?m)^Part 6 - Disclaimer\s*:?\s*$", "**Disclaimer**", formatted)
    formatted = _dedupe_disclaimer(formatted)
    formatted = re.sub(r"\n{3,}", "\n\n", formatted).strip()
    return formatted


def _plain_act_name(act_label: str) -> str:
    return re.sub(r"\*", "", FULL_ACT_NAMES.get(act_label, act_label)).strip()


def _build_query_act_response(user_query: str, results: List[Any], reasoning: List[str], session_id: str, mode: str) -> QueryResponse:
    top_act, top_sec, top_score = results[0]
    plain_act_name = _plain_act_name(top_act)
    section_text = reconstruct_section(top_act, top_sec)

    if is_explanation_query(user_query):
        answer = call_qwen_act(user_query, section_text, plain_act_name)
    else:
        answer = section_text

    context_block = {
        "citation_id": "C1",
        "corpus": "acts",
        "document_id": plain_act_name,
        "title": plain_act_name,
        "section_number": str(top_sec),
        "section_title": None,
        "context_path": f"Section {top_sec}",
        "source_file": None,
        "chunk_id": None,
        "scores": {
            "final_score": float(top_score),
            "hybrid_score": float(top_score),
            "dense_score": None,
            "bm25_score": None,
            "rerank_score": None,
        },
        "texts": {
            "chunk_text": section_text,
            "parent_text": "",
            "section_text": section_text,
            "court": None,
            "bench": None,
            "date": None,
            "chunk_type": "section",
        },
    }

    applicable_laws = _extract_applicable_law_lines([context_block])
    final_answer = format_final_answer(answer, [context_block], suggested_laws=applicable_laws) + "\n\n---\n**Disclaimer**\nFor information only. Consult a professional."

    return QueryResponse(
        ok=True,
        query=user_query,
        answer=final_answer,
        reasoning=reasoning,
        citations=[
            {
                "citation_id": "C1",
                "title": plain_act_name,
                "section_number": str(top_sec),
                "context_path": f"Section {top_sec}",
                "source_file": None,
                "chunk_id": None,
            }
        ],
        context_blocks=[context_block],
        applicable_laws=applicable_laws,
        meta={"mode": mode, "score": float(top_score), "session_id": session_id},
    )

# =========================
# AUTH / ACCESS ENDPOINTS
# =========================

@app.post("/auth/request-access", response_model=RequestAccessResponse)
def auth_request_access(payload: RequestAccessRequest) -> RequestAccessResponse:
    first_name = payload.first_name.strip()
    last_name = payload.last_name.strip()
    organization = payload.organization.strip()
    use_case = payload.use_case.strip()
    email = payload.email.strip().lower()

    if not first_name or not last_name or not organization or not use_case:
        raise HTTPException(status_code=400, detail="All request access fields are required.")
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Please provide a valid email address.")

    full_name = f"{first_name} {last_name}".strip()

    now = _utc_now_iso()
    with _db_conn() as conn:
        existing = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if existing and existing["role"] == "admin":
            raise HTTPException(status_code=400, detail="This email is reserved for seeded admin access.")

        if existing:
            user_id = int(existing["id"])
            target_status = existing["status"]
            target_access = bool(existing["access_granted"])
            if existing["status"] != "granted" or int(existing["access_granted"]) != 1:
                target_status = "pending"
                target_access = False
            conn.execute(
                """
                UPDATE users
                SET name = ?, organization = ?, use_case = ?, status = ?, access_granted = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    full_name,
                    organization,
                    use_case,
                    target_status,
                    target_access,
                    now,
                    user_id,
                ),
            )
            final_status = target_status
            has_access = bool(target_access)
        else:
            cur = conn.execute(
                """
                INSERT INTO users
                (name, email, organization, use_case, role, status, access_granted, password_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'user', 'pending', FALSE, NULL, ?, ?)
                RETURNING id
                """,
                (
                    full_name,
                    email,
                    organization,
                    use_case,
                    now,
                    now,
                ),
            )
            user_row = cur.fetchone()
            if not user_row:
                raise HTTPException(status_code=500, detail="Failed to create user record.")
            user_id = int(user_row["id"])
            final_status = "pending"
            has_access = False

        conn.execute(
            """
            INSERT INTO access_requests
            (user_id, name, email, organization, use_case, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                full_name,
                email,
                organization,
                use_case,
                final_status,
                now,
            ),
        )
        conn.commit()

    if final_status == "granted" and has_access:
        return RequestAccessResponse(ok=True, message="Account already has product access. Please log in.")
    return RequestAccessResponse(ok=True, message="Access request submitted successfully. Please wait for admin approval.")


@app.post("/auth/login", response_model=LoginResponse)
def auth_login(payload: LoginRequest) -> LoginResponse:
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Please provide a valid email address.")

    with _db_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    user_view = AuthUserView(**_row_to_user_view(row))
    role = row["role"]
    status = row["status"]
    access_granted = bool(row["access_granted"])

    if role == "user" and status == "pending":
        return LoginResponse(ok=True, state="pending_access", message="Your access request is pending admin approval.", user=user_view)

    if role == "user" and (status == "denied" or not access_granted):
        return LoginResponse(ok=True, state="access_denied", message="Access not granted. Please contact admin.", user=user_view)

    if not row["password_hash"]:
        return LoginResponse(
            ok=True,
            state="password_setup_required",
            message="Password setup is required before login.",
            user=user_view,
        )

    if not _verify_password(payload.password, str(row["password_hash"])):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = _create_session_for_user(int(row["id"]))
    return LoginResponse(ok=True, state="success", message="Login successful.", token=token, user=user_view)


@app.post("/auth/logout", response_model=LogoutResponse)
def auth_logout(authorization: Optional[str] = Header(default=None)) -> LogoutResponse:
    raw_token = _extract_bearer_token(authorization)
    now = _utc_now_iso()
    with _db_conn() as conn:
        cur = conn.execute(
            """
            UPDATE sessions
            SET revoked = TRUE, revoked_at = ?
            WHERE token_hash = ? AND revoked = FALSE
            """,
            (now, _hash_token(raw_token)),
        )
        conn.commit()
    if cur.rowcount <= 0:
        raise HTTPException(status_code=401, detail="Session already invalid.")
    return LogoutResponse(ok=True, message="Logged out successfully.")


@app.get("/auth/me", response_model=MeResponse)
def auth_me(authorization: Optional[str] = Header(default=None)) -> MeResponse:
    user_row = _require_authenticated_user(authorization)
    return MeResponse(ok=True, user=AuthUserView(**_row_to_user_view(user_row)))


@app.patch("/auth/me", response_model=AuthUserUpdateResponse)
def auth_update_me(
    payload: UpdateProfileRequest,
    authorization: Optional[str] = Header(default=None),
) -> AuthUserUpdateResponse:
    user_row = _require_authenticated_user(authorization)
    now = _utc_now_iso()

    clean_name = payload.name.strip()
    clean_organization = payload.organization.strip()
    clean_use_case = payload.use_case.strip()
    clean_advocate_address = payload.advocate_address.strip()
    clean_advocate_mobile = payload.advocate_mobile.strip()
    if len(clean_name) < 2:
        raise HTTPException(status_code=400, detail="Name must be at least 2 characters.")
    if len(clean_advocate_address) < 5:
        raise HTTPException(status_code=400, detail="Advocate address is required.")
    if len(clean_advocate_mobile) < 8:
        raise HTTPException(status_code=400, detail="Advocate mobile is required.")

    with _db_conn() as conn:
        conn.execute(
            """
            UPDATE users
            SET name = ?, organization = ?, use_case = ?, advocate_address = ?, advocate_mobile = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                clean_name,
                clean_organization,
                clean_use_case,
                clean_advocate_address,
                clean_advocate_mobile,
                now,
                int(user_row["id"]),
            ),
        )
        conn.commit()
        updated_row = conn.execute("SELECT * FROM users WHERE id = ?", (int(user_row["id"]),)).fetchone()

    if not updated_row:
        raise HTTPException(status_code=404, detail="User not found after update.")

    return AuthUserUpdateResponse(
        ok=True,
        message="Profile details updated successfully.",
        user=AuthUserView(**_row_to_user_view(updated_row)),
    )


@app.post("/auth/change-password", response_model=RequestAccessResponse)
def auth_change_password(
    payload: ChangePasswordRequest,
    authorization: Optional[str] = Header(default=None),
) -> RequestAccessResponse:
    user_row = _require_authenticated_user(authorization)

    existing_password_hash = str(user_row["password_hash"] or "").strip()
    if not existing_password_hash:
        raise HTTPException(status_code=400, detail="Password is not set for this account.")

    if not _verify_password(payload.current_password, existing_password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password.")

    now = _utc_now_iso()
    with _db_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (_hash_password(payload.new_password), now, int(user_row["id"])),
        )
        conn.commit()

    return RequestAccessResponse(ok=True, message="Password changed successfully.")


@app.post("/auth/set-password", response_model=RequestAccessResponse)
def auth_set_password(payload: SetPasswordRequest) -> RequestAccessResponse:
    token_hash = _hash_token(payload.token.strip())
    now = _utc_now_iso()

    with _db_conn() as conn:
        token_row = conn.execute(
            """
            SELECT * FROM password_setup_tokens
            WHERE token_hash = ? AND used = FALSE AND expires_at > ?
            """,
            (token_hash, now),
        ).fetchone()
        if not token_row:
            raise HTTPException(status_code=400, detail="Password setup token is invalid or expired.")

        user_row = conn.execute("SELECT * FROM users WHERE id = ?", (int(token_row["user_id"]),)).fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found for setup token.")

        if user_row["role"] == "user" and (user_row["status"] != "granted" or int(user_row["access_granted"]) != 1):
            raise HTTPException(status_code=400, detail="User is not currently granted product access.")

        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (_hash_password(payload.new_password), now, int(user_row["id"])),
        )
        conn.execute(
            "UPDATE password_setup_tokens SET used = TRUE, used_at = ? WHERE id = ?",
            (now, int(token_row["id"])),
        )
        conn.commit()

    return RequestAccessResponse(ok=True, message="Password set successfully. You can now log in.")


@app.get("/admin/access-requests", response_model=AdminAccessListResponse)
def admin_access_requests(authorization: Optional[str] = Header(default=None)) -> AdminAccessListResponse:
    _require_admin_user(authorization)

    with _db_conn() as conn:
        user_rows = conn.execute(
            """
            SELECT id, name, email, organization, use_case, role, status, access_granted, created_at, updated_at,
                   CASE WHEN password_hash IS NOT NULL THEN 1 ELSE 0 END AS has_password
            FROM users
            WHERE role = 'user'
            ORDER BY updated_at DESC
            """
        ).fetchall()
        request_rows = conn.execute(
            """
            SELECT id, user_id, name, email, organization, use_case, status, reviewed_by, review_notes, created_at, reviewed_at
            FROM access_requests
            ORDER BY created_at DESC
            LIMIT 500
            """
        ).fetchall()

    users_payload = []
    for row in user_rows:
        item = dict(row)
        item["access_granted"] = bool(item.get("access_granted"))
        item["has_password"] = bool(item.get("has_password"))
        users_payload.append(item)

    requests_payload = [dict(row) for row in request_rows]
    return AdminAccessListResponse(ok=True, users=users_payload, requests=requests_payload)


@app.get("/admin/monitoring/access-events", response_model=AdminAccessMonitoringResponse)
def admin_monitoring_access_events(
    authorization: Optional[str] = Header(default=None),
    from_at: Optional[str] = Query(default=None, alias="from"),
    to_at: Optional[str] = Query(default=None, alias="to"),
    ip: Optional[str] = Query(default=None),
    user_id: Optional[int] = Query(default=None),
    email: Optional[str] = Query(default=None),
    path_contains: Optional[str] = Query(default=None),
    status_code: Optional[int] = Query(default=None, ge=100, le=599),
    outcome: Optional[str] = Query(default=None),
    authenticated_only: Optional[bool] = Query(default=None),
    limit: int = Query(default=ADMIN_MONITORING_DEFAULT_LIMIT, ge=1, le=ADMIN_MONITORING_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> AdminAccessMonitoringResponse:
    _require_admin_user(authorization)

    where_clause, where_params = _build_access_event_filters(
        from_at=from_at,
        to_at=to_at,
        ip=ip,
        user_id=user_id,
        email=email,
        path_contains=path_contains,
        status_code=status_code,
        outcome=outcome,
        authenticated_only=authenticated_only,
    )

    with _db_conn() as conn:
        event_rows = conn.execute(
            f"""
            SELECT
                id,
                occurred_at,
                ip_address,
                forwarded_for,
                real_ip,
                method,
                path,
                status_code,
                outcome,
                user_agent,
                referer,
                origin,
                query_string_present,
                user_id,
                user_email,
                user_role,
                session_id,
                is_authenticated
            FROM access_events
            {where_clause}
            ORDER BY occurred_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*where_params, limit + 1, offset],
        ).fetchall()
        summary_row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                COUNT(DISTINCT NULLIF(ip_address, '')) AS unique_ips,
                COALESCE(SUM(CASE WHEN is_authenticated THEN 1 ELSE 0 END), 0) AS authenticated,
                COALESCE(SUM(CASE WHEN NOT is_authenticated THEN 1 ELSE 0 END), 0) AS anonymous,
                COALESCE(SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END), 0) AS failed
            FROM access_events
            {where_clause}
            """,
            where_params,
        ).fetchone()
        top_ip_clause = f"{where_clause} {'AND' if where_clause else 'WHERE'} NULLIF(ip_address, '') IS NOT NULL"
        top_ip_rows = conn.execute(
            f"""
            SELECT
                ip_address,
                COUNT(*) AS hit_count,
                MAX(occurred_at) AS last_seen_at
            FROM access_events
            {top_ip_clause}
            GROUP BY ip_address
            ORDER BY hit_count DESC, last_seen_at DESC
            LIMIT ?
            """,
            [*where_params, ADMIN_MONITORING_TOP_IP_LIMIT],
        ).fetchall()

    summary_data = dict(summary_row) if summary_row else {}
    has_more = len(event_rows) > limit
    serialized_events = [_serialize_access_event(row) for row in event_rows[:limit]]
    summary_payload = {
        "total": int(summary_data.get("total", 0)),
        "unique_ips": int(summary_data.get("unique_ips", 0)),
        "authenticated": int(summary_data.get("authenticated", 0)),
        "anonymous": int(summary_data.get("anonymous", 0)),
        "failed": int(summary_data.get("failed", 0)),
    }
    top_ips_payload = [
        {
            "ip_address": str(row["ip_address"] or ""),
            "hit_count": int(row["hit_count"] or 0),
            "last_seen_at": str(row["last_seen_at"] or ""),
        }
        for row in top_ip_rows
    ]

    return AdminAccessMonitoringResponse(
        ok=True,
        events=[AccessEventView(**item) for item in serialized_events],
        summary=AccessEventSummary(**summary_payload),
        top_ips=[TopIpView(**item) for item in top_ips_payload],
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@app.patch("/admin/users/{user_id}/access", response_model=AdminAccessUpdateResponse)
def admin_update_user_access(
    user_id: int,
    payload: AccessUpdateRequest,
    authorization: Optional[str] = Header(default=None),
) -> AdminAccessUpdateResponse:
    admin_row = _require_admin_user(authorization)
    now = _utc_now_iso()

    target_status = payload.status
    target_access = bool(payload.access_granted)
    if target_status in {"pending", "denied"}:
        target_access = False

    with _db_conn() as conn:
        user_row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found.")
        if user_row["role"] != "user":
            raise HTTPException(status_code=400, detail="Admin user cannot be modified by this endpoint.")

        conn.execute(
            """
            UPDATE users
            SET status = ?, access_granted = ?, updated_at = ?
            WHERE id = ?
            """,
            (target_status, target_access, now, user_id),
        )

        conn.execute(
            """
            INSERT INTO access_requests
            (user_id, name, email, organization, use_case, status, reviewed_by, review_notes, created_at, reviewed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                user_row["name"],
                user_row["email"],
                user_row["organization"] or "",
                user_row["use_case"] or "",
                target_status,
                int(admin_row["id"]),
                payload.review_notes.strip(),
                now,
                now,
            ),
        )
        conn.commit()

        updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    return AdminAccessUpdateResponse(
        ok=True,
        message="User access updated successfully.",
        user=_row_to_user_view(updated),
    )


@app.post("/admin/users/{user_id}/password-setup-link", response_model=PasswordSetupLinkResponse)
def admin_generate_password_setup_link(
    user_id: int,
    authorization: Optional[str] = Header(default=None),
) -> PasswordSetupLinkResponse:
    admin_row = _require_admin_user(authorization)
    now = _utc_now_iso()

    with _db_conn() as conn:
        user_row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found.")
        if user_row["role"] != "user":
            raise HTTPException(status_code=400, detail="Cannot generate setup link for admin account.")
        if user_row["status"] != "granted" or int(user_row["access_granted"]) != 1:
            raise HTTPException(status_code=400, detail="Grant product access before generating a setup link.")

        conn.execute(
            """
            UPDATE password_setup_tokens
            SET used = TRUE, used_at = ?
            WHERE user_id = ? AND used = FALSE
            """,
            (now, user_id),
        )

        raw_token = secrets.token_urlsafe(48)
        expires_at = _utc_iso_after_hours(PASSWORD_SETUP_TOKEN_TTL_HOURS)
        setup_url = f"{FRONTEND_BASE_URL}/?setup_token={raw_token}"
        _send_setup_link_email(str(user_row["email"]), str(user_row["name"]), setup_url)
        conn.execute(
            """
            INSERT INTO password_setup_tokens
            (user_id, token_hash, expires_at, used, created_by_admin_id, created_at)
            VALUES (?, ?, ?, FALSE, ?, ?)
            """,
            (user_id, _hash_token(raw_token), expires_at, int(admin_row["id"]), now),
        )
        conn.commit()

    return PasswordSetupLinkResponse(ok=True, setup_url=setup_url, expires_at=expires_at)


@app.get("/chat/sessions", response_model=ChatSessionListResponse)
def list_chat_sessions(
    authorization: Optional[str] = Header(default=None),
    limit: int = CHAT_HISTORY_LIST_LIMIT,
) -> ChatSessionListResponse:
    user_row = _require_product_access_user(authorization)
    sessions = _list_chat_sessions(int(user_row["id"]), limit=limit)
    return ChatSessionListResponse(ok=True, sessions=sessions)


@app.get("/chat/sessions/{session_id}", response_model=ChatSessionDetailResponse)
def get_chat_session(
    session_id: str,
    authorization: Optional[str] = Header(default=None),
    limit: int = CHAT_HISTORY_DETAIL_LIMIT,
) -> ChatSessionDetailResponse:
    user_row = _require_product_access_user(authorization)
    safe_session_id = _sanitize_chat_session_id(session_id)
    detail = _load_chat_session_detail(int(user_row["id"]), safe_session_id, limit=limit)
    if not detail:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    SESSIONS[safe_session_id] = [
        {"role": str(item["role"]), "content": str(item["content"])}
        for item in detail["messages"]
    ]
    return ChatSessionDetailResponse(ok=True, session=detail["session"], messages=detail["messages"])


@app.patch("/chat/sessions/{session_id}", response_model=ChatSessionMutationResponse)
def rename_chat_session(
    session_id: str,
    payload: ChatSessionRenameRequest,
    authorization: Optional[str] = Header(default=None),
) -> ChatSessionMutationResponse:
    user_row = _require_product_access_user(authorization)
    safe_session_id = _sanitize_chat_session_id(session_id)
    ok = _rename_chat_session(int(user_row["id"]), safe_session_id, payload.title)
    if not ok:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return ChatSessionMutationResponse(ok=True, message="Chat session renamed.")


@app.delete("/chat/sessions/{session_id}", response_model=ChatSessionMutationResponse)
def delete_chat_session(
    session_id: str,
    authorization: Optional[str] = Header(default=None),
) -> ChatSessionMutationResponse:
    user_row = _require_product_access_user(authorization)
    safe_session_id = _sanitize_chat_session_id(session_id)
    ok = _delete_chat_session(int(user_row["id"]), safe_session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return ChatSessionMutationResponse(ok=True, message="Chat session deleted.")


# =========================
# MAIN STRUCTURED RAG FLOW
# =========================

@app.post("/query", response_model=QueryResponse)
def query(payload: QueryRequest, authorization: Optional[str] = Header(default=None)) -> QueryResponse:
    user_row = _require_product_access_user(authorization)
    user_id = int(user_row["id"])
    try:
        raw_query = payload.query
        requested_mode = str(payload.mode or "").strip().lower()
        effective_mode = "query_act" if requested_mode == "query_act" else "lawyer_case"
        reasoning = []
        debug_trace: Dict[str, Any] = {"query": raw_query}
        
        # 🍯 1. Greeting Bypass (No AI, No Filter needed)
        # Move this to the very top to allow simple human interaction
        user_query = sanitize_user_input(raw_query)
        static_answer = get_static_greeting(user_query)
        if static_answer:
            return QueryResponse(
                ok=True, query=user_query, answer=static_answer, 
                reasoning=["Greeting Optimization: Static response used."],
                citations=[], context_blocks=[], 
                applicable_laws=[],
                meta={"mode": "greeting", "effective_mode": effective_mode, "inference": False}
            )

        # 🛡️ 2. Input Validation Layer (CLEARED as per user request)
        pass
        
        # 🛡️ 3. Domain Classifier (CLEARED as per user request)
        pass
        
        # 🔑 Session Management (persistent chat memory)
        s_id = _sanitize_chat_session_id(payload.session_id)
        if payload.session_id:
            _ensure_chat_session(user_id, s_id, seed_text=user_query)
        if payload.reset_session:
            _ensure_chat_session(user_id, s_id, seed_text=user_query)
            _clear_chat_history(user_id, s_id)
        history = _load_chat_history_for_prompt(user_id, s_id, limit=CHAT_HISTORY_PROMPT_LIMIT)
        SESSIONS[s_id] = list(history)

        structured_query = extract_structured_query(user_query, payload.llm_model)
        debug_trace["structured_query"] = structured_query
        reasoning.append(
            "Understanding facts: "
            + "; ".join(structured_query.get("facts", [])[:3])
            if structured_query.get("facts")
            else "Understanding facts from the user query."
        )

        expanded_obj = build_query(user_query)
        intent_route = build_intent_route(user_query, forced_domain=structured_query.get("domain", ""))
        debug_trace["intent_route"] = intent_route
        law_focus = generate_relevant_laws(
            user_query=user_query,
            structured_query=structured_query,
            model_name=payload.llm_model,
            timeout_sec=min(payload.llm_timeout_sec, 20),
        )
        debug_trace["law_focus"] = law_focus
        if law_focus.get("preferred_laws"):
            reasoning.append("Preferred laws: " + ", ".join(law_focus["preferred_laws"]))
        law_candidates = _law_focus_candidates(law_focus)
        precise_statute_query = bool(expanded_obj.filters.get("section_number") and expanded_obj.filters.get("act"))

        # --- STEP 1: Query Rewriter ---
        reasoning.append("Step 1: Rewriting query to dense legal keywords...")
        dense_keywords = expanded_obj.expanded_query

        if precise_statute_query:
            llm_query = user_query
            legal_query = dense_keywords
            reasoning.append("Detected direct act-section lookup; skipped free-form rewrite.")
        else:
            llm_query = rewrite_query(user_query, payload.llm_model, timeout_sec=15)
            llm_query = " ".join((llm_query or "").splitlines()[:1]).strip() or user_query
            legal_query = " ".join(part for part in [llm_query, dense_keywords] if part).strip()

        reasoning.append(f"Rewritten Query: {llm_query}")
        reasoning.append(f"Dense Expansion: {dense_keywords}")
        retrieval_queries = [legal_query] if precise_statute_query else generate_retrieval_queries(
            user_query=user_query,
            structured_query=structured_query,
            dense_query=dense_keywords,
            rewritten_query=llm_query,
            model_name=payload.llm_model,
            timeout_sec=min(payload.llm_timeout_sec, 20),
        )
        reasoning.append(f"Retrieval Queries ({len(retrieval_queries)} max {MAX_RETRIEVAL_QUERIES}): " + " | ".join(retrieval_queries))
        debug_trace["expanded_queries"] = retrieval_queries

        # PHASE 2: Run heuristics BEFORE retrieval — always available
        heuristic_matches = match_heuristics(user_query)
        legal_priors_text = format_heuristics_for_prompt(heuristic_matches)
        debug_trace["heuristics"] = format_heuristics_for_debug(heuristic_matches)
        if heuristic_matches:
            reasoning.append(f"Legal priors matched: {', '.join(m['heuristic_key'] for m in heuristic_matches)}")

        # Temporary bypass: direct LLM answer without embedding retrieval.
        if DISABLE_EMBEDDING_RETRIEVAL and effective_mode != "query_act" and not precise_statute_query:
            reasoning.append("Embedding retrieval disabled; generating direct model answer with legal priors.")
            prompt = build_direct_legal_prompt(user_query, legal_priors=legal_priors_text)
            answer = call_llm(model_name=payload.llm_model, prompt=prompt, timeout_sec=payload.llm_timeout_sec)
            if _is_legal_advice_refusal(answer):
                reasoning.append("Detected legal-advice refusal; retrying with general-information instruction.")
                answer = call_llm(
                    model_name=payload.llm_model,
                    prompt=_retry_prompt_for_general_info(user_query),
                    timeout_sec=payload.llm_timeout_sec,
                )
            disclaimer = "\n\n---\n**Disclaimer**\nFor information only. Consult a professional."
            final_answer = format_final_answer(answer.strip(), [], suggested_laws=law_candidates) + disclaimer

            _record_chat_turn(user_id, s_id, user_query, answer)

            append_query_log(
                {
                    "time": datetime.utcnow().isoformat() + "Z",
                    "user_query": user_query,
                    "structured_query": structured_query,
                    "expanded_queries": retrieval_queries,
                    "retrieved_chunks": [],
                    "filtered_chunks": [],
                    "final_context": [],
                    "final_prompt": prompt,
                    "llm_output": answer,
                    "validation": {"valid": True, "mode": "direct_llm_no_retrieval"},
                    "heuristics": debug_trace.get("heuristics", []),
                }
            )

            return QueryResponse(
                ok=True,
                query=user_query,
                answer=final_answer,
                reasoning=reasoning,
                citations=[],
                context_blocks=[],
                applicable_laws=law_candidates,
                meta={
                    "mode": effective_mode,
                    "requested_mode": requested_mode,
                    "session_id": s_id,
                    "structured_query": structured_query,
                    "retrieval_disabled": True,
                    **({"debug": debug_trace} if payload.debug else {}),
                },
            )

        # --- STEP 2: Rule-Based Metadata Filtering ---
        domain_filter = None
        filter_keywords = {
            "theft", "stole", "murder", "kill", "rape", "assault", "robbery", "police", "fir", "arrest", "bail", "cheating",
            "cyber", "online fraud", "otp", "phishing", "hacking", "hacked", "data breach", "identity theft", "upi fraud",
            "sim swap", "fake profile", "ransomware", "whatsapp fraud",
        }
        if any(w in user_query.lower() for w in filter_keywords):
            domain_filter = "criminal"
            reasoning.append("Metadata Filter applied: Domain = Criminal")
        elif structured_query.get("domain") in {"consumer", "criminal", "contract", "property", "labour"}:
            domain_filter = structured_query["domain"] if structured_query["domain"] == "criminal" else None

        # --- STEP 3: Deep Retrieval ---
        reasoning.append("Step 2: Performing deep retrieval...")
        
        if effective_mode == "query_act" or precise_statute_query:
            load_act_data() 
            results = search_sections(legal_query)
            max_score = 1.0 if results else 0.0 # Deterministic is binary
            if not results:
                missing_section = expanded_obj.filters.get("section_number")
                missing_act = expanded_obj.filters.get("act")
                missing_answer = "No relevant statutory section found in the database."
                if missing_section and missing_act:
                    missing_answer = f"Section {missing_section} was not found in the available text for {missing_act}."
                _record_chat_turn(user_id, s_id, user_query, missing_answer)
                return QueryResponse(
                    ok=True,
                    query=user_query,
                    answer=missing_answer,
                    reasoning=reasoning,
                    citations=[],
                    context_blocks=[],
                    applicable_laws=law_candidates,
                    meta={"mode": effective_mode, "requested_mode": requested_mode, "reason": "no_match", "session_id": s_id},
                )
            reasoning.append("Detected direct statute query; using deterministic section lookup.")
            query_act_response = _build_query_act_response(user_query, results, reasoning, s_id, effective_mode)
            _record_chat_turn(user_id, s_id, user_query, query_act_response.answer)
            return query_act_response
        else:
            retrieval_corpus = "acts" if precise_statute_query else ("all" if USE_JUDGEMENT_EMBEDDINGS else "acts")
            allowed_docs = DEFAULT_ALLOWED_DOCS if structured_query.get("intent") == "legal_query" else {"acts"}
            retrieval_args = SimpleNamespace(
                q=legal_query, 
                mode="understand_case",
                corpus=retrieval_corpus,
                top_k=5,
                dense_k=20,
                bm25_k=20,
                dense_weight=0.7,
                bm25_weight=0.3,
                rerank=True,
                rerank_top_n=20,
                rerank_model="cross-encoder/ms-marco-MiniLM-L-2-v2",
                rerank_batch_size=16,
                domain_filter=domain_filter,
                legal_domain=structured_query.get("domain", "auto"),
                act_filter=expanded_obj.filters.get("act"),
                section_filter=expanded_obj.filters.get("section_number"),
                era_filter=_infer_era_filter(user_query, structured_query),
                intent_route=intent_route,
                relevant_laws=law_focus.get("relevant_laws", []),
                preferred_laws=law_focus.get("preferred_laws", []),
                disallowed_law_hints=law_focus.get("disallowed_law_hints", []),
            )
            results, retrieval_debug = retrieve_for_queries(retrieval_queries, retrieval_args, allowed_docs=allowed_docs)
            debug_trace["retrieval"] = retrieval_debug
            retrieval_summary = retrieval_debug.get("summary", {}) if isinstance(retrieval_debug, dict) else {}
            if retrieval_summary:
                reasoning.append(
                    "Retrieval summary: "
                    f"queries={retrieval_summary.get('queries_executed', 0)}, "
                    f"merged={retrieval_summary.get('merged_count', 0)}, "
                    f"max_score={float(retrieval_summary.get('max_score', 0.0) or 0.0):.2f}, "
                    f"avg_score={float(retrieval_summary.get('avg_score', 0.0) or 0.0):.2f}"
                )
            if not _query_mentions_specific_state(user_query):
                reasoning.append("State-specific authorities suppressed because no Indian state was mentioned in the query.")
                results = _filter_state_specific_results(user_query, results)
                debug_trace["state_filtered_chunks"] = [_result_summary(item) for item in results]
            max_score = max([r.get('final_score', r.get('hybrid_score', 0)) for r in results]) if results else 0
            reasoning.append(
                "Retrieval corpus: acts + judgements (embedding enabled)."
                if retrieval_corpus == "all"
                else "Retrieval corpus: acts only (judgement embeddings disabled)."
            )

            if not results:
                reasoning.append("Primary retrieval returned no usable chunks; trying keyword fallback.")
                fallback_results, fallback_debug = retrieve_with_keyword_fallback(
                    user_query=user_query,
                    base_args=retrieval_args,
                    allowed_docs=allowed_docs,
                )
                if fallback_results:
                    results = fallback_results
                    debug_trace["keyword_fallback"] = fallback_debug
                    max_score = max([r.get('final_score', r.get('hybrid_score', 0)) for r in results]) if results else 0

        # PHASE 2: Determine retrieval confidence mode
        is_low_confidence = _detect_low_confidence(results)
        retrieval_mode = "fallback" if (not results or is_low_confidence) else "normal"
        debug_trace["retrieval_mode"] = retrieval_mode
        debug_trace["heuristics_used"] = bool(heuristic_matches)
        reasoning.append(f"PHASE 2: Retrieval mode = {retrieval_mode} (results={len(results)}, max_score={max_score:.2f})")

        # PHASE 2+3: FALLBACK MODE — no results at all
        if not results:
            reasoning.append("PHASE 2: No retrieval results; using fallback prompt with legal priors.")
            if legal_priors_text:
                prompt = _build_fallback_prompt(user_query, legal_priors_text)
                reasoning.append("Fallback: Using heuristic-augmented expert prompt.")
            else:
                prompt = build_direct_legal_prompt(user_query)
                reasoning.append("Fallback: No heuristic match; using direct legal prompt.")

            # PHASE 3: Dual-generation — Pass 1: Draft
            reasoning.append("PHASE 3: Dual-generation Pass 1 — generating draft...")
            draft_answer = call_llm(model_name=payload.llm_model, prompt=prompt, timeout_sec=payload.llm_timeout_sec)
            if _is_legal_advice_refusal(draft_answer):
                draft_answer = call_llm(
                    model_name=payload.llm_model,
                    prompt=_retry_prompt_for_general_info(user_query),
                    timeout_sec=payload.llm_timeout_sec,
                )

            # PHASE 3: Answer validation
            validation = validate_answer(draft_answer)
            if validation["needs_refinement"]:
                reasoning.append(f"PHASE 3: Draft has issues ({', '.join(validation['issues'])}); refining...")
                refine_prompt = build_refinement_prompt(draft_answer, user_query, legal_priors_text)
                answer = call_llm(model_name=payload.llm_model, prompt=refine_prompt, timeout_sec=payload.llm_timeout_sec)
            else:
                answer = draft_answer

            # PHASE 3: Confidence scoring
            conf_score = compute_confidence([], heuristic_matches, retrieval_mode)
            conf_level = confidence_label(conf_score)
            reasoning.append(f"PHASE 3: Confidence = {conf_score} ({conf_level})")

            # PHASE 3: Mode-aware styling
            answer = apply_confidence_styling(answer.strip(), conf_score, retrieval_mode)
            disclaimer = "\n\n---\n**Disclaimer**\nFor information only. Consult a professional."
            final_answer = format_final_answer(answer, [], suggested_laws=law_candidates) + disclaimer

            append_query_log(
                {
                    "time": datetime.utcnow().isoformat() + "Z",
                    "user_query": user_query,
                    "structured_query": structured_query,
                    "expanded_queries": retrieval_queries,
                    "retrieved_chunks": debug_trace.get("retrieval", {}).get("runs", []),
                    "filtered_chunks": [],
                    "final_context": [],
                    "validation": {"valid": True, "mode": "phase3_fallback", "score": max_score},
                    "heuristics": debug_trace.get("heuristics", []),
                    "retrieval_mode": retrieval_mode,
                    "confidence": conf_score,
                    "answer_validation": validation,
                }
            )
            _record_chat_turn(user_id, s_id, user_query, answer)
            return QueryResponse(
                ok=True, query=user_query,
                answer=final_answer,
                reasoning=reasoning,
                citations=[], context_blocks=[],
                applicable_laws=law_candidates,
                confidence=conf_score,
                confidence_label=conf_level,
                meta={
                    "mode": effective_mode,
                    "requested_mode": requested_mode,
                    "score": max_score,
                    "session_id": s_id,
                    "retrieval_mode": retrieval_mode,
                    "heuristics_matched": len(heuristic_matches),
                    "confidence": conf_score,
                    "confidence_label": conf_level,
                    **({"debug": debug_trace} if payload.debug else {}),
                }
            )

        # --- STEP 4: LLM Re-ranking ---
        if (
            effective_mode == "lawyer_case"
            and len(results) > 3
            and not precise_statute_query
            and not any(item.get("rerank_score") is not None for item in results)
        ):
            reasoning.append(f"Step 3: AI Re-ranking {len(results)} chunks to top 3...")
            results = llm_rerank(user_query, results, payload.llm_model, timeout_sec=20)

        # 📜 Process Context Pack
        reasoning.append(f"Step 4: Extracting best context (Max Score: {max_score:.2f})...")
        acts_lookup = load_acts_chunk_lookup("JSON_acts")
        pack = build_context_pack(query=user_query, results=results, acts_lookup=acts_lookup, max_chars=14000)
        context_blocks = pack.get("context_blocks", [])
        debug_trace["final_context"] = pack.get("citations", [])

        # PHASE 3: Extract citations for prompt injection
        structured_citations = extract_citations(context_blocks)
        citation_text = format_citations_for_prompt(structured_citations)

        # 🧠 PHASE 2+3: Build prompt — augment with heuristic priors + citations
        authority_summary = build_authority_summary(context_blocks)
        base_context = pack.get("prompt_context") or build_context_text(context_blocks)
        context_text = f"{authority_summary}\n\n{base_context}".strip() if authority_summary else base_context

        # PHASE 2: ALWAYS inject heuristic priors into context (even in normal mode)
        context_text = _build_augmented_context(context_text, legal_priors_text)

        # PHASE 3: Inject citation summary into context
        if citation_text:
            context_text = f"{context_text}\n\n{citation_text}"

        if retrieval_mode == "fallback":
            reasoning.append("PHASE 2: Low-confidence retrieval; using fallback prompt with heuristic priors + weak context.")
            prompt = _build_fallback_prompt(user_query, legal_priors_text, citation_text)
            # Append the weak context as supplementary
            prompt += f"\n\nSupplementary Retrieved Context (low confidence):\n{context_text}\n"
        else:
            reasoning.append("Step 5: Preparing analysis with retrieved documents + legal priors + citations...")
            _, tokenizer = get_model_and_tokenizer(payload.llm_model)
            prompt = build_llm_prompt(user_query, context_text, history=history, tokenizer=tokenizer)

        # 🤖 PHASE 3: Dual-generation — Pass 1: Draft
        reasoning.append("Step 6: PHASE 3 — Dual-generation Pass 1 (draft)...")
        draft_answer = call_llm(model_name=payload.llm_model, prompt=prompt, timeout_sec=payload.llm_timeout_sec)
        if _is_legal_advice_refusal(draft_answer):
            reasoning.append("Detected legal-advice refusal; retrying with stronger response instruction.")
            retry_prompt = (
                f"{prompt}\n\n"
                "IMPORTANT:\n"
                "Do not refuse with 'I can't give legal advice'.\n"
                "Provide general legal information from the given Indian context and practical next steps.\n"
            )
            draft_answer = call_llm(model_name=payload.llm_model, prompt=retry_prompt, timeout_sec=payload.llm_timeout_sec)

        # PHASE 3: Answer validation on draft
        draft_validation = validate_answer(draft_answer)
        debug_trace["draft_validation"] = draft_validation

        if draft_validation["needs_refinement"]:
            # PHASE 3: Dual-generation — Pass 2: Refine
            reasoning.append(f"Step 7: PHASE 3 — Dual-generation Pass 2 (refine) — issues: {', '.join(draft_validation['issues'])}")
            refine_prompt = build_refinement_prompt(draft_answer, user_query, legal_priors_text)
            answer = call_llm(model_name=payload.llm_model, prompt=refine_prompt, timeout_sec=payload.llm_timeout_sec)
            # Validate refined answer
            refined_validation = validate_answer(answer)
            if not refined_validation["valid"] and refined_validation.get("issues"):
                # If still weak, try confidence rewrite
                reasoning.append("PHASE 3: Refined answer still weak; applying confidence rewrite...")
                answer = call_llm(
                    model_name=payload.llm_model,
                    prompt=build_confidence_rewrite_prompt(answer),
                    timeout_sec=payload.llm_timeout_sec,
                )
        else:
            answer = draft_answer
            reasoning.append("Step 7: Draft answer passed validation — skipping refinement pass.")
        grounding = validate_grounding(answer, pack)
        if not grounding.get("valid", False) and grounding.get("invalid_sections"):
            reasoning.append("Grounding mismatch detected; retrying with strict allowed-section repair prompt.")
            repair_prompt = _build_grounding_repair_prompt(
                original_prompt=prompt,
                invalid_sections=[str(s) for s in grounding.get("invalid_sections", [])],
                allowed_sections=_allowed_section_numbers(context_blocks),
            )
            repaired_answer = call_llm(
                model_name=payload.llm_model,
                prompt=repair_prompt,
                timeout_sec=payload.llm_timeout_sec,
            )
            repaired_grounding = validate_grounding(repaired_answer, pack)
            if repaired_grounding.get("valid", False):
                answer = repaired_answer
                grounding = repaired_grounding
                reasoning.append("Grounding repaired successfully after one retry.")

        if not grounding.get("valid", False):
            applicable_laws = _extract_applicable_law_lines(context_blocks, fallback_laws=law_candidates)
            conservative_answer = _build_context_grounded_fallback(user_query, context_blocks)
            append_query_log(
                {
                    "time": datetime.utcnow().isoformat() + "Z",
                    "user_query": user_query,
                    "structured_query": structured_query,
                    "expanded_queries": retrieval_queries,
                    "retrieved_chunks": pack.get("citations", []),
                    "filtered_chunks": debug_trace.get("retrieval", {}).get("runs", []),
                    "final_context": pack.get("citations", []),
                    "final_prompt": prompt,
                    "llm_output": answer,
                    "fallback_output": conservative_answer,
                    "validation": grounding,
                }
            )
            _record_chat_turn(user_id, s_id, user_query, conservative_answer)
            return QueryResponse(
                ok=True,
                query=user_query,
                answer=conservative_answer,
                reasoning=reasoning + ["Post-generation validation failed; returned context-grounded conservative fallback."],
                citations=pack.get("citations", []),
                context_blocks=context_blocks,
                applicable_laws=applicable_laws,
                meta={
                    "mode": effective_mode,
                    "requested_mode": requested_mode,
                    "score": max_score,
                    "session_id": s_id,
                    "validation": grounding,
                    **({"debug": debug_trace} if payload.debug else {}),
                },
            )

        # PHASE 3: Confidence scoring
        conf_score = compute_confidence(context_blocks, heuristic_matches, retrieval_mode)
        conf_level = confidence_label(conf_score)
        reasoning.append(f"PHASE 3: Confidence = {conf_score} ({conf_level})")

        # PHASE 3: Mode-aware styling
        answer = apply_confidence_styling(answer, conf_score, retrieval_mode)
        applicable_laws = _extract_applicable_law_lines(context_blocks, fallback_laws=law_candidates)

        # 🤝 Safe Return
        disclaimer = "\n\n---\n**Disclaimer**\nFor information only. Consult a professional."
        final_answer = format_final_answer(answer, context_blocks, suggested_laws=law_candidates) + disclaimer
        append_query_log(
            {
                "time": datetime.utcnow().isoformat() + "Z",
                "user_query": user_query,
                "structured_query": structured_query,
                "expanded_queries": retrieval_queries,
                "retrieved_chunks": pack.get("citations", []),
                "filtered_chunks": debug_trace.get("retrieval", {}).get("runs", []),
                "final_context": pack.get("citations", []),
                "final_prompt": prompt,
                "llm_output": answer,
                "validation": grounding,
                "heuristics": debug_trace.get("heuristics", []),
                "retrieval_mode": debug_trace.get("retrieval_mode", "normal"),
                "confidence": conf_score,
                "draft_validation": debug_trace.get("draft_validation"),
            }
        )

        _record_chat_turn(user_id, s_id, user_query, answer)

        return QueryResponse(
            ok=True, query=user_query, answer=final_answer, reasoning=reasoning,
            citations=pack.get("citations", []),
            context_blocks=context_blocks,
            applicable_laws=applicable_laws,
            confidence=conf_score,
            confidence_label=conf_level,
            meta={
                "mode": effective_mode,
                "requested_mode": requested_mode,
                "score": max_score,
                "session_id": s_id,
                "structured_query": structured_query,
                "retrieval_mode": debug_trace.get("retrieval_mode", "normal"),
                "heuristics_matched": len(heuristic_matches),
                "confidence": conf_score,
                "confidence_label": conf_level,
                **({"debug": debug_trace} if payload.debug else {}),
            }
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": str(exc), "traceback": traceback.format_exc()})


@app.post("/query/user", response_model=UserModeResponse)
def query_user(payload: QueryRequest, authorization: Optional[str] = Header(default=None)) -> UserModeResponse:
    _require_product_access_user(authorization)
    raise HTTPException(
        status_code=410,
        detail="User/consumer endpoint is disabled. This deployment is configured for lawyers only. Use /query."
    )


# =====================================================
# PHASE 2: INTELLIGENT LEGAL INTERVIEW
# =====================================================
@app.post("/query/interview/chat", response_model=InterviewChatResponse)
def interview_chat(
    payload: InterviewChatRequest = Body(...),
    authorization: Optional[str] = Header(default=None),
) -> InterviewChatResponse:
    _require_product_access_user(authorization)
    try:
        s_id = payload.session_id or str(uuid.uuid4())
        
        # 0. Initialize/Load Case Model from Session
        if s_id not in INTERVIEW_SESSIONS:
            INTERVIEW_SESSIONS[s_id] = _fresh_interview_session_state()
        session = INTERVIEW_SESSIONS[s_id]
        auto_session_reset = False
        if _should_auto_reset_interview_session(session, payload.query):
            INTERVIEW_SESSIONS[s_id] = _fresh_interview_session_state()
            session = INTERVIEW_SESSIONS[s_id]
            auto_session_reset = True
        # Backfill guard fields for old sessions.
        session.setdefault("interview_turns", 0)
        session.setdefault("stagnant_turns", 0)
        session.setdefault("pending_confirmation_retries", 0)
        session.setdefault("asked_contradiction_codes", [])
        session["interview_turns"] = int(session.get("interview_turns", 0)) + 1

        status = "interviewing"
        fact_progress = False
        forced_assess = False
        user_confidence = None
        previous_top_law = session.get("last_top_law")

        # 1. NEW Case Model Redesign (Phase 1)
        # If the user is providing a confirmed/edited model from the UI
        if payload.case_model_update:
            session["case_model"] = payload.case_model_update.dict()
            status = "interviewing" # User confirmed, proceed to analysis
            fact_progress = True
        else:
            # Run the new multi-step pipeline
            new_case = run_case_extractor_pipeline(payload.query, payload.llm_model)
            
            # Merge logic (Lossless)
            if not session.get("case_model"):
                session["case_model"] = new_case.dict()
                if new_case.events or new_case.parties:
                    fact_progress = True
            else:
                current_model = CaseModel(**session["case_model"])
                prev_event_count = len(current_model.events)
                # Add new parties/events that aren't duplicates
                for p in new_case.parties:
                    if not any(cp.id == p.id for cp in current_model.parties):
                        current_model.parties.append(p)
                        fact_progress = True
                
                new_events = [e for e in new_case.events if e.sequence > prev_event_count]
                if new_events:
                    current_model.events.extend(new_events)
                    fact_progress = True

                current_model.financials.extend(new_case.financials)
                current_model.documents.extend(new_case.documents)
                current_model.meta.intents = list(set(current_model.meta.intents + new_case.meta.intents))
                current_model.meta.claims = list(set(current_model.meta.claims + new_case.meta.claims))
                current_model.missing_information = new_case.missing_information
                session["case_model"] = current_model.dict()

            # Detection of 'review_required' (New events/parties found)
            if fact_progress:
                status = "review_required"

        case_obj = CaseModel(**session["case_model"])
        
        # 2. Incident Classification (Keep existing for issue tracking)
        extracted_data = extract_facts_llm(payload.query, payload.llm_model, 30)
        candidates = sorted(extracted_data.incident_type_candidates, key=lambda x: x.confidence, reverse=True)
        top_incident = candidates[0].type if candidates else "unknown"
        top_confidence = candidates[0].confidence if candidates else 0.0
        
        # Update issues
        if session["issue"] == "unknown" or top_confidence > 0.8:
            session["issue"] = top_incident
        for c in candidates:
            if c.confidence >= 0.7 and c.type not in session["active_issues"]:
                session["active_issues"].append(c.type)
        
        issue = session["issue"]
        active_issues = session.get("active_issues", [issue])
        subtype = "general"
        employment_issues = {"wage_dispute", "termination_dispute"}

        # 3. Persist heuristic facts from both the case model and raw user turn
        prev_facts_snapshot = json.dumps(session.get("facts", {}), sort_keys=True, default=str)
        session["facts"] = _update_session_facts_from_case_model(case_obj, session["facts"])
        session["facts"] = extract_facts_heuristic(payload.query, issue, session["facts"])
        curr_facts_snapshot = json.dumps(session.get("facts", {}), sort_keys=True, default=str)
        if curr_facts_snapshot != prev_facts_snapshot:
            fact_progress = True

        # 4. PHASE 6.5: Signal accumulation + confidence handling
        signal_updates = extract_signal_updates(payload.query)
        if issue not in employment_issues:
            # Ignore stale employment-specific signal prompts for non-employment matters.
            for signal_name in ["work_relationship", "service_years", "employment_end", "payment_type"]:
                session["signals"].pop(signal_name, None)

        pending_confirmation = session.get("pending_confirmation")
        confirmation_progress = False
        if pending_confirmation:
            user_confidence = normalize_user_confidence(payload.query)
            if user_confidence is not None:
                signal_name = pending_confirmation["signal_name"]
                existing_payload = dict(session["signals"].get(signal_name, {}))
                if existing_payload:
                    existing_payload["user_confidence"] = user_confidence
                    existing_payload["confirmed"] = user_confidence >= 0.6
                    existing_payload["source"] = "user_confirmation"
                    session["signals"][signal_name] = existing_payload
                session["pending_confirmation"] = None
                session["pending_confirmation_retries"] = 0
                confirmation_progress = True
            else:
                session["pending_confirmation_retries"] = int(session.get("pending_confirmation_retries", 0)) + 1
                if signal_updates or session["pending_confirmation_retries"] >= MAX_PENDING_CONFIRMATION_RETRIES:
                    # Don't get stuck waiting for explicit yes/no phrasing forever.
                    session["pending_confirmation"] = None
                    session["pending_confirmation_retries"] = 0

        session["signals"] = merge_signal_state(session.get("signals", {}), signal_updates)
        progress_this_turn = bool(fact_progress or signal_updates or confirmation_progress)
        if progress_this_turn:
            session["stagnant_turns"] = 0
        else:
            session["stagnant_turns"] = int(session.get("stagnant_turns", 0)) + 1

        contradictions = detect_contradictions(session["signals"], session["facts"], case_obj)
        session["contradictions"] = contradictions
        contradictions_present = bool(contradictions)

        # 5. Phase 2: Legal Primitive Detection (Candidate Legal Meanings)
        def bedrock_wrapper(prompt_text: str) -> str:
             return call_bedrock_chat(
                 messages=[{"role": "user", "content": prompt_text}],
                 model_id=payload.llm_model
             )
        
        brain = LegalBrain(llm_fn=bedrock_wrapper)
        brain_response = brain.detect_primitives(case_obj)

        # Attempt to detect domain/relationship from case model for better mapping
        if not case_obj.domain:
            if any(b.name in ["access_without_permission", "account_compromised"] for b in brain_response.behavioral_primitives):
                case_obj.domain = "cyber"
            elif any(b.name == "employment_ended" for b in brain_response.behavioral_primitives):
                case_obj.domain = "employment"
            elif any(b.name in ["possession_removed", "forced_exit"] for b in brain_response.behavioral_primitives):
                case_obj.domain = "property"
            elif any(b.name in ["money_not_paid", "money_not_returned"] for b in brain_response.behavioral_primitives):
                case_obj.domain = "financial"

        if not case_obj.detected_relationship:
             for p in case_obj.parties:
                 rel = (p.relationship_to_client or "").lower()
                 if "employer" in rel:
                     case_obj.detected_relationship = "employer-employee"
                 if "landlord" in rel:
                     case_obj.detected_relationship = "landlord-tenant"

        confirmed_tags, confirmed_tag_confidence = derive_confirmed_tags(session["signals"])
        contradiction_penalty = phase65_contradiction_penalty(contradictions)
        law_engine = LawEngine(llm_fn=bedrock_wrapper)
        laws_response = law_engine.map_laws(
            case_obj,
            brain_response,
            confirmed_tags=confirmed_tags,
            confirmed_tag_confidence=confirmed_tag_confidence,
            contradiction_penalty=contradiction_penalty,
        )

        # 6. Signal Strength & Decision Engine
        strength = compute_signal_strength(
            issue,
            session["facts"],
            signals=session["signals"],
            contradictions=contradictions,
        )
        decision = decide_next_step(issue, session["facts"], strength, contradictions=contradictions)
        
        # Progress Guard: If we got new facts, don't stall in CLARIFY
        if decision == "CLARIFY" and fact_progress:
            decision = "INTERVIEW"
        # Loop guard: if we've stalled too long, move to assessment with assumptions.
        if decision in {"CLARIFY", "INTERVIEW"} and (
            int(session.get("interview_turns", 0)) >= MAX_INTERVIEW_TURNS
            or int(session.get("stagnant_turns", 0)) >= MAX_STAGNANT_TURNS
        ):
            decision = "ASSESS"
            forced_assess = True
            session["pending_confirmation"] = None
            session["pending_confirmation_retries"] = 0

        if decision == "CLARIFY":
            return InterviewChatResponse(
                ok=True,
                session_id=s_id,
                issue=issue,
                secondary_issues=active_issues[1:] if len(active_issues) > 1 else [],
                confidence=strength,
                status="clarification_required",
                is_complete=False,
                questions=["Could you please describe the situation in more detail? I'm having trouble identifying the specific legal issue."],
                legal_output=None,
                case_model=case_obj,
                state_debug={
                    "strength": strength, 
                    "decision": "CLARIFY",
                    "top_confidence": top_confidence,
                    "fact_progress": fact_progress,
                    "auto_session_reset": auto_session_reset,
                }
            )

        # 6. Branching Logic (INTERVIEW vs ASSESS)
        is_complete = (decision == "ASSESS")
        
        final_questions_text = []
        if not is_complete:
            if contradictions_present:
                asked_contradiction_codes = set(session.get("asked_contradiction_codes", []))
                new_contradiction = next((c for c in contradictions if c.get("code") not in asked_contradiction_codes), None)
                if new_contradiction:
                    final_questions_text.append(new_contradiction["clarification_question"])
                    asked_contradiction_codes.add(str(new_contradiction.get("code")))
                    session["asked_contradiction_codes"] = list(asked_contradiction_codes)

            if not final_questions_text:
                confirmation_signal_state = dict(session["signals"])
                if issue not in employment_issues:
                    for signal_name in ["work_relationship", "service_years", "employment_end", "payment_type"]:
                        confirmation_signal_state.pop(signal_name, None)
                confirmation_question = choose_confirmation_question(confirmation_signal_state, session["asked_questions"])
                if confirmation_question:
                    session["pending_confirmation"] = confirmation_question
                    if confirmation_question["id"] not in session["asked_questions"]:
                        session["asked_questions"].append(confirmation_question["id"])
                    final_questions_text.append(confirmation_question["question"])

            if not final_questions_text:
                ranked_signal_questions = rank_signal_questions(
                    laws_response=laws_response,
                    case_model=case_obj,
                    brain_response=brain_response,
                    law_engine=law_engine,
                    current_confirmed_tags=confirmed_tags,
                    confirmed_tag_confidence=confirmed_tag_confidence,
                    signal_state=session["signals"],
                    contradictions=contradictions,
                )
                if ranked_signal_questions:
                    chosen_signal_question = ranked_signal_questions[0]
                    if chosen_signal_question["id"] not in session["asked_questions"]:
                        session["asked_questions"].append(chosen_signal_question["id"])
                    final_questions_text.append(chosen_signal_question["question"])

            # INTERVIEW Mode: Get targeted questions for ALL active issues
            selected_qs = select_questions(
                issue=issue, 
                facts=session["facts"], 
                asked_questions=session["asked_questions"],
                llm_model=payload.llm_model,
                subtype=subtype,
                secondary=active_issues[1:] if len(active_issues) > 1 else []
            )
            
            for q in selected_qs:
                if q["question"] not in final_questions_text:
                    final_questions_text.append(q["question"])
                if q["id"] not in session["asked_questions"]:
                    session["asked_questions"].append(q["id"])
                    
            # If the Case Model has missing info, prioritize its questions
            if case_obj.missing_information and len(final_questions_text) < 2:
                asked_gap_questions = set(session.get("asked_gap_questions", []))
                lawyer_rep_markers = [
                    "i am a lawyer", "i am the lawyer", "my client", "she is my client", "he is my client", "represent",
                ]
                has_lawyer_rep_context = any(marker in payload.query.lower() for marker in lawyer_rep_markers)
                for gap in case_obj.missing_information[:2]:
                    gap_question = str(gap.get("question") or "").strip()
                    if not gap_question or gap_question in asked_gap_questions:
                        continue
                    if has_lawyer_rep_context and "relationship" in gap_question.lower():
                        continue
                    if gap_question not in final_questions_text:
                        final_questions_text.append(gap_question)
                        asked_gap_questions.add(gap_question)
                session["asked_gap_questions"] = list(asked_gap_questions)
        
        # 7. Generate Output
        output_data = generate_legal_output(issue, subtype, session["facts"], is_complete, payload.llm_model)
        output_data["confidence"] = strength 
        legal_output = LegalOutput(**output_data)

        # Final Status determination
        if is_complete:
            final_status = "complete"
        elif contradictions_present or session.get("pending_confirmation"):
            final_status = "clarification_required"
        elif status == "review_required":
            final_status = "review_required"
        else:
            final_status = "interviewing"
        session["last_top_law"] = _top_law_name(laws_response.applicable_laws)

        dashboard_summary = analyze_interaction_logs(INTERACTION_LOG_PATH, days=7)
        if final_questions_text:
            append_interaction_log(
                INTERACTION_LOG_PATH,
                build_log_entry(
                    question_id=session["asked_questions"][-1] if session["asked_questions"] else "unknown",
                    question_text=final_questions_text[0],
                    signal_state=session["signals"],
                    contradictions=contradictions,
                    previous_top_law=previous_top_law,
                    current_top_law=session["last_top_law"],
                    user_confidence=user_confidence,
                ),
            )

        return InterviewChatResponse(
            session_id=s_id,
            issue=issue,
            secondary_issues=active_issues[1:] if len(active_issues) > 1 else [],
            confidence=strength,
            status=final_status,
            is_complete=is_complete,
            questions=final_questions_text,
            legal_output=legal_output,
            case_model=case_obj,
            behavioral_primitives=brain_response.behavioral_primitives,
            interpretations=brain_response.interpretations,
            applicable_laws=laws_response.applicable_laws,
            state_debug={
                "strength": strength,
                "decision": decision,
                "forced_assess": forced_assess,
                "auto_session_reset": auto_session_reset,
                "behavioral_count": len(brain_response.behavioral_primitives),
                "interpretation_count": len(brain_response.interpretations),
                "law_count": len(laws_response.applicable_laws),
                "active_issues": active_issues,
                "interview_turns": session.get("interview_turns", 0),
                "stagnant_turns": session.get("stagnant_turns", 0),
                "pending_confirmation_retries": session.get("pending_confirmation_retries", 0),
                "signals": summarize_signal_state(session["signals"]),
                "confirmed_tags": confirmed_tags,
                "confirmed_tag_confidence": confirmed_tag_confidence,
                "contradictions": contradictions,
                "contradiction_penalty": contradiction_penalty,
                "last_top_law": session.get("last_top_law"),
                "dashboard_summary": dashboard_summary,
            }
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": str(exc), "traceback": traceback.format_exc()})


# =====================================================
# PHASE 3: LAWYER MODE (LLM DRIVEN)
# =====================================================
@app.post("/query/lawyer/init", response_model=LawyerModeResponse)
def query_lawyer_init(payload: LawyerInitRequest, authorization: Optional[str] = Header(default=None)) -> LawyerModeResponse:
    _require_product_access_user(authorization)
    user_query = sanitize_user_input(payload.query)
    session_id = payload.session_id or str(uuid.uuid4())
    LAWYER_SESSIONS[session_id] = {}

    structured_query = extract_structured_query(user_query, payload.llm_model)
    law_focus = generate_relevant_laws(
        user_query=user_query,
        structured_query=structured_query,
        model_name=payload.llm_model,
        timeout_sec=min(payload.llm_timeout_sec, 20),
    )
    init_payload = _generate_lawyer_init_payload(
        user_query=user_query,
        structured_query=structured_query,
        law_focus=law_focus,
        model_name=payload.llm_model,
        timeout_sec=min(payload.llm_timeout_sec, 30),
    )

    LAWYER_SESSIONS[session_id] = {
        "query": user_query,
        "structured_query": structured_query,
        "law_focus": law_focus,
        "issues": init_payload["issues"],
        "facts": init_payload["facts"],
        "questions": init_payload["questions"],
        "legal_pathways": init_payload["legal_pathways"],
        "llm_model": payload.llm_model,
        "llm_timeout_sec": payload.llm_timeout_sec,
    }

    return LawyerModeResponse(
        ok=True,
        session_id=session_id,
        facts=init_payload["facts"],
        issues=init_payload["issues"],
        legal_pathways=init_payload["legal_pathways"],
        questions=init_payload["questions"],
        final_analysis=None,
        meta={"debug": LAWYER_SESSIONS[session_id]} if payload.debug else {},
    )


@app.post("/query/lawyer/refine", response_model=LawyerModeResponse)
def query_lawyer_refine(payload: LawyerRefineRequest, authorization: Optional[str] = Header(default=None)) -> LawyerModeResponse:
    _require_product_access_user(authorization)
    session = LAWYER_SESSIONS.get(payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Lawyer session not found. Start with /query/lawyer/init.")

    answers = {str(k): str(v).strip() for k, v in (payload.answers or {}).items() if str(v).strip()}
    retrieval_queries, law_focus, refined_structured = _build_lawyer_retrieval_inputs(session, answers)
    intent_route = build_intent_route(session.get("query", ""), forced_domain=refined_structured.get("domain", ""))

    retrieval_args = SimpleNamespace(
        q=session.get("query", ""),
        mode="understand_case",
        corpus="all" if USE_JUDGEMENT_EMBEDDINGS else "acts",
        top_k=6,
        dense_k=20,
        bm25_k=20,
        dense_weight=0.7,
        bm25_weight=0.3,
        rerank=True,
        rerank_top_n=20,
        rerank_model="cross-encoder/ms-marco-MiniLM-L-2-v2",
        rerank_batch_size=16,
        domain_filter=refined_structured.get("domain") if refined_structured.get("domain") == "criminal" else None,
        legal_domain=refined_structured.get("domain", "auto"),
        act_filter=None,
        section_filter=None,
        era_filter=_infer_era_filter(session.get("query", ""), refined_structured),
        intent_route=intent_route,
        relevant_laws=law_focus.get("relevant_laws", []),
        preferred_laws=law_focus.get("preferred_laws", []),
        disallowed_law_hints=law_focus.get("disallowed_law_hints", []),
    )

    results, retrieval_debug = retrieve_for_queries(retrieval_queries, retrieval_args, allowed_docs=DEFAULT_ALLOWED_DOCS)
    if not _query_mentions_specific_state(session.get("query", "")):
        results = _filter_state_specific_results(session.get("query", ""), results)
    if not results:
        fallback_results, fallback_debug = retrieve_with_keyword_fallback(
            user_query=session.get("query", ""),
            base_args=retrieval_args,
            allowed_docs=DEFAULT_ALLOWED_DOCS,
        )
        if fallback_results:
            results = fallback_results
            retrieval_debug["keyword_fallback"] = fallback_debug

    acts_lookup = load_acts_chunk_lookup("JSON_acts")
    pack = build_context_pack(query=session.get("query", ""), results=results, acts_lookup=acts_lookup, max_chars=14000)
    context_blocks = pack.get("context_blocks", [])
    final_analysis = _generate_lawyer_final_analysis(
        session=session,
        answers=answers,
        context_blocks=context_blocks,
        model_name=payload.llm_model,
        timeout_sec=min(payload.llm_timeout_sec, 40),
    )

    session["answers"] = answers
    session["final_analysis"] = final_analysis

    return LawyerModeResponse(
        ok=True,
        session_id=payload.session_id,
        facts=session.get("facts", ""),
        issues=session.get("issues", []),
        legal_pathways=session.get("legal_pathways", []),
        questions=session.get("questions", []),
        final_analysis=final_analysis,
        meta={"retrieval": retrieval_debug, "context": pack.get("citations", [])} if payload.debug else {},
    )


@app.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat() + "Z"}


# =====================================================
# LEGAL NOTICE GENERATION ENDPOINTS
# =====================================================

class NoticeRequest(BaseModel):
    sender_name: str = Field(..., min_length=2)
    sender_address: str = Field(..., min_length=5)
    advocate_name: Optional[str] = Field(
        default=None,
        description="Advocate name used in notice signature block",
    )
    advocate_address: Optional[str] = Field(
        default=None,
        description="Advocate address used in notice signature block",
    )
    advocate_mobile: Optional[str] = Field(
        default=None,
        description="Advocate mobile number used in notice signature block",
    )
    advocate_contact: Optional[str] = Field(
        default=None,
        description="Advocate contact detail (email/phone) used in notice signature",
    )
    # Backward-compat alias for older clients. Prefer advocate_contact.
    sender_contact: Optional[str] = None
    receiver_name: str = Field(..., min_length=2)
    receiver_address: str = Field(..., min_length=5)
    relationship: str = Field("", description="e.g. employee-employer, landlord-tenant")
    facts: List[str] = Field(..., min_items=1)
    claim: str = Field(..., min_length=2)
    notice_type: str = "auto"  # "auto" or one of NOTICE_TYPES keys
    jurisdiction: str = "India"
    tone: str = "firm"  # "firm", "aggressive", "polite"
    custom_relief: Optional[List[str]] = None
    custom_deadline: Optional[int] = None
    llm_model: str = DEFAULT_BEDROCK_MODEL_ID
    llm_timeout_sec: int = 300

class NoticeResponse(BaseModel):
    ok: bool
    notice: str
    laws_used: List[str]
    notice_type: str
    notice_type_label: str
    confidence: float
    confidence_label: str
    meta: Dict[str, Any] = {}


def _compose_advocate_contact_line(advocate_mobile: str, advocate_email: str) -> str:
    parts: List[str] = []
    if advocate_mobile:
        parts.append(f"Mobile: {advocate_mobile}")
    if advocate_email:
        parts.append(f"Email: {advocate_email}")
    return " | ".join(parts).strip()


def _replace_notice_identity_placeholders(
    notice_text: str,
    advocate_name: str,
    advocate_address: str,
    advocate_mobile: str,
    advocate_email: str,
    advocate_contact: str,
) -> str:
    """Resolve common signature placeholders to advocate identity details."""
    text = str(notice_text or "")
    if not text:
        return text

    clean_name = str(advocate_name or "").strip()
    clean_address = str(advocate_address or "").strip()
    clean_mobile = str(advocate_mobile or "").strip()
    clean_email = str(advocate_email or "").strip()
    clean_contact = str(advocate_contact or "").strip()

    if clean_name:
        text = re.sub(r"\[\s*your\s+name\s*\]", clean_name, text, flags=re.IGNORECASE)
        text = re.sub(
            r"(?im)^\s*your\s+name\s*[:\-]?\s*$",
            f"Name: {clean_name}",
            text,
        )
        text = re.sub(
            r"(?im)^\s*name\s*[:\-]\s*(?:\[\s*your\s+name\s*\]|your\s+name)?\s*$",
            f"Name: {clean_name}",
            text,
        )

    if clean_address:
        text = re.sub(r"\[\s*your\s+address\s*\]", clean_address, text, flags=re.IGNORECASE)
        text = re.sub(
            r"(?im)^\s*your\s+address\s*[:\-]?\s*$",
            f"Address: {clean_address}",
            text,
        )

    if clean_contact:
        text = re.sub(r"\[\s*your\s+contact\s+details?\s*\]", clean_contact, text, flags=re.IGNORECASE)
        text = re.sub(r"\[\s*contact\s+details?\s*\]", clean_contact, text, flags=re.IGNORECASE)
        text = re.sub(
            r"(?im)^\s*your\s+contact\s+details?\s*[:\-]?\s*$",
            f"Contact Details: {clean_contact}",
            text,
        )
        text = re.sub(
            r"(?im)^\s*contact\s+details?\s*[:\-]\s*(?:\[\s*contact\s+details?\s*\])?\s*$",
            f"Contact Details: {clean_contact}",
            text,
        )
        text = re.sub(r"(?im)^\s*email\s*[:\-]\s*$", f"Email: {clean_contact}", text)

    if clean_mobile:
        text = re.sub(r"\[\s*your\s+mobile\s*\]", clean_mobile, text, flags=re.IGNORECASE)
        text = re.sub(
            r"(?im)^\s*mobile\s*[:\-]\s*(?:\[\s*your\s+mobile\s*\])?\s*$",
            f"Mobile: {clean_mobile}",
            text,
        )

    if clean_email:
        text = re.sub(r"\[\s*your\s+email\s*\]", clean_email, text, flags=re.IGNORECASE)
        text = re.sub(
            r"(?im)^\s*email\s*[:\-]\s*(?:\[\s*your\s+email\s*\])?\s*$",
            f"Email: {clean_email}",
            text,
        )

    return text


def _replace_party_address_placeholders(notice_text: str, sender_address: str, receiver_address: str) -> str:
    """Resolve sender/receiver generic [Address] placeholders in notice headers."""
    text = str(notice_text or "")
    if not text:
        return text

    clean_sender = str(sender_address or "").strip()
    clean_receiver = str(receiver_address or "").strip()

    if clean_receiver:
        text = re.sub(r"\[\s*receiver\s+address\s*\]", clean_receiver, text, flags=re.IGNORECASE)
    if clean_sender:
        text = re.sub(r"\[\s*sender\s+address\s*\]", clean_sender, text, flags=re.IGNORECASE)

    address_values: List[str] = []
    if clean_receiver:
        address_values.append(clean_receiver)
    if clean_sender:
        address_values.append(clean_sender)

    if address_values:
        idx = {"value": 0}

        def _replace_generic_address(_: re.Match) -> str:
            if idx["value"] < len(address_values):
                value = address_values[idx["value"]]
                idx["value"] += 1
                return value
            return _.group(0)

        text = re.sub(r"\[\s*address\s*\]", _replace_generic_address, text, flags=re.IGNORECASE)

    return text


def _enforce_notice_heading_and_subject_format(notice_text: str) -> str:
    """Normalize heading/subject format for deterministic presentation."""
    text = str(notice_text or "").strip()
    if not text:
        return text

    lines = text.splitlines()
    heading_idx = -1
    for idx, line in enumerate(lines):
        if re.fullmatch(r"\s*(?:\#{1,6}\s*)?legal\s+notice\s*", line, flags=re.IGNORECASE):
            heading_idx = idx
            break
        if re.search(r"formal\s+complaint", line, flags=re.IGNORECASE):
            heading_idx = idx
            break

    if heading_idx >= 0:
        lines[heading_idx] = "LEGAL NOTICE"
    else:
        lines = ["LEGAL NOTICE", "", *lines]

    for idx, line in enumerate(lines):
        plain = re.sub(r"\*+", "", line).strip()
        if re.match(r"(?i)^subject\s*:", plain):
            lines[idx] = f"**{plain}**"
            break

    text = "\n".join(lines).strip()

    # Replace valedictions with an explicit signature line.
    text = re.sub(
        r"(?im)^\s*yours\s+(?:faithfully|sincerely|truly)\s*,?\s*$",
        "Signature: ________________________",
        text,
    )

    # Fix broken bullet markers where marker appears on one line and content starts on the next line.
    bullet_marker_re = re.compile(r"^(\s*(?:[-*•]|\d+[.)]|[A-Za-z][.)]))\s*$")
    src_lines = text.splitlines()
    normalized_lines: List[str] = []
    i = 0
    while i < len(src_lines):
        line = src_lines[i]
        marker_match = bullet_marker_re.match(line)
        if marker_match:
            j = i + 1
            while j < len(src_lines) and not src_lines[j].strip():
                j += 1
            if j < len(src_lines):
                normalized_lines.append(f"{marker_match.group(1)} {src_lines[j].lstrip()}")
                i = j + 1
                continue
        normalized_lines.append(line)
        i += 1

    return "\n".join(normalized_lines).strip()


@app.get("/generate/notice-types")
def get_notice_types(authorization: Optional[str] = Header(default=None)):
    _require_product_access_user(authorization)
    """Return available notice types for the frontend dropdown."""
    return {"ok": True, "types": get_available_notice_types()}


@app.post("/generate/notice", response_model=NoticeResponse)
def generate_notice(payload: NoticeRequest, authorization: Optional[str] = Header(default=None)) -> NoticeResponse:
    requesting_user = _require_product_access_user(authorization)
    """Generate a professional legal notice from structured input."""
    try:
        advocate_name = str(payload.advocate_name or requesting_user["name"] or "").strip()
        advocate_email = str(requesting_user["email"] or "").strip()
        advocate_address = str(
            payload.advocate_address or requesting_user["advocate_address"] or ""
        ).strip()
        advocate_mobile = str(
            payload.advocate_mobile or requesting_user["advocate_mobile"] or ""
        ).strip()
        advocate_contact = str(payload.advocate_contact or payload.sender_contact or "").strip()
        if not advocate_contact:
            advocate_contact = _compose_advocate_contact_line(advocate_mobile, advocate_email)

        if not advocate_address or not advocate_mobile:
            raise HTTPException(
                status_code=400,
                detail="Advocate address and mobile are required. Update them in Settings > Details.",
            )

        # STEP 1: Determine notice type
        if payload.notice_type == "auto":
            detected_type = auto_detect_notice_type(payload.claim, payload.facts)
        else:
            detected_type = payload.notice_type if payload.notice_type in NOTICE_TYPES else "general"

        config = NOTICE_TYPES.get(detected_type, NOTICE_TYPES["general"])

        # STEP 2: Get heuristic priors
        heuristic_matches = match_heuristics(f"{payload.claim} {' '.join(payload.facts)}")
        legal_priors_text = format_heuristics_for_prompt(heuristic_matches)

        # STEP 3: Retrieve supporting context (optional RAG)
        retrieved_context = ""
        try:
            search_query = f"{payload.claim} legal provisions India {' '.join(config.get('keywords', []))}"
            retrieval_args = SimpleNamespace(
                q=search_query,
                mode="understand_case",
                corpus="acts",
                top_k=3,
                dense_k=10,
                bm25_k=10,
                dense_weight=0.7,
                bm25_weight=0.3,
                rerank=False,
                rerank_top_n=5,
                rerank_model="cross-encoder/ms-marco-MiniLM-L-2-v2",
                rerank_batch_size=16,
                domain_filter=None,
                legal_domain="auto",
                act_filter=None,
                section_filter=None,
                era_filter=_infer_era_filter(search_query, {}),
                intent_route=None,
                relevant_laws=[],
                preferred_laws=[],
                disallowed_law_hints=[],
            )
            results, _ = retrieve_for_queries([search_query], retrieval_args, allowed_docs={"acts"})
            if results:
                chunks_text = []
                for r in results[:3]:
                    title = r.get("title", "")
                    section = r.get("section_number", "")
                    text = r.get("chunk_text", "")[:300]
                    chunks_text.append(f"{title} — Section {section}\n{text}")
                retrieved_context = "\n\n".join(chunks_text)
        except Exception:
            pass  # RAG is optional; notice generation works without it

        # STEP 4: Build notice prompt
        prompt = build_notice_prompt(
            sender_name=payload.sender_name,
            sender_address=payload.sender_address,
            advocate_name=advocate_name,
            advocate_address=advocate_address,
            advocate_mobile=advocate_mobile,
            advocate_email=advocate_email,
            advocate_contact=advocate_contact,
            receiver_name=payload.receiver_name,
            receiver_address=payload.receiver_address,
            relationship=payload.relationship,
            facts=payload.facts,
            claim=payload.claim,
            notice_type=detected_type,
            jurisdiction=payload.jurisdiction,
            retrieved_context=retrieved_context,
            legal_priors=legal_priors_text,
            custom_relief=payload.custom_relief,
            custom_deadline=payload.custom_deadline,
            tone=payload.tone,
        )

        # STEP 5: Generate draft (Pass 1)
        draft_notice = call_llm(
            model_name=payload.llm_model,
            prompt=prompt,
            timeout_sec=payload.llm_timeout_sec,
        )

        # STEP 6: Refine (Pass 2 — mandatory)
        refine_prompt = build_notice_refinement_prompt(draft_notice, tone=payload.tone)
        refined_notice = call_llm(
            model_name=payload.llm_model,
            prompt=refine_prompt,
            timeout_sec=payload.llm_timeout_sec,
        )

        # STEP 7: Append authority section
        laws_used = config["laws"][:]
        # Add any laws from heuristic matches not already in the list
        for match in heuristic_matches:
            for law in match.get("laws", []):
                if law not in laws_used:
                    laws_used.append(law)

        authority_appendix = build_authority_appendix(laws_used)
        final_notice = refined_notice.strip()
        if authority_appendix:
            final_notice += "\n" + authority_appendix
        final_notice = _replace_notice_identity_placeholders(
            final_notice,
            advocate_name=advocate_name,
            advocate_address=advocate_address,
            advocate_mobile=advocate_mobile,
            advocate_email=advocate_email,
            advocate_contact=advocate_contact,
        )
        final_notice = _replace_party_address_placeholders(
            final_notice,
            sender_address=payload.sender_address,
            receiver_address=payload.receiver_address,
        )
        final_notice = _enforce_notice_heading_and_subject_format(final_notice)

        # STEP 8: Compute confidence
        has_retrieval = bool(retrieved_context)
        has_heuristics = bool(heuristic_matches)
        conf = 0.5  # base
        if has_retrieval:
            conf += 0.25
        if has_heuristics:
            conf += 0.15
        if detected_type != "general":
            conf += 0.10
        conf = round(min(conf, 1.0), 2)
        conf_level = confidence_label(conf)

        return NoticeResponse(
            ok=True,
            notice=final_notice,
            laws_used=laws_used,
            notice_type=detected_type,
            notice_type_label=config["label"],
            confidence=conf,
            confidence_label=conf_level,
            meta={
                "tone": payload.tone,
                "deadline_days": payload.custom_deadline or config["deadline_days"],
                "heuristics_matched": len(heuristic_matches),
                "has_retrieval_context": has_retrieval,
                "detected_type": detected_type,
                "advocate_name_applied": bool(advocate_name),
                "advocate_address_applied": bool(advocate_address),
                "advocate_mobile_applied": bool(advocate_mobile),
                "advocate_contact_applied": bool(advocate_contact),
            },
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": str(exc), "traceback": traceback.format_exc()})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
