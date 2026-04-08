import json
import os
from typing import Optional
from legal_engine.models import ConversationState

SESSIONS_DIR = "sessions"

def save_state(state: ConversationState) -> str:
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    file_path = os.path.join(SESSIONS_DIR, f"{state.conversation_id}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(state.model_dump_json(indent=2))
    return file_path

def load_state(conversation_id: str) -> Optional[ConversationState]:
    file_path = os.path.join(SESSIONS_DIR, f"{conversation_id}.json")
    if not os.path.exists(file_path):
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        return ConversationState(**data)
