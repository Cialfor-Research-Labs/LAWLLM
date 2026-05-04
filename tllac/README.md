# TLLAC — Trained Legal AI Chat Backend

> **Fully isolated** backend for the Experimental Chat UI.
> Runs on **port 9001** — does NOT interfere with the existing LAW LLM backend.

---

## 📁 Folder Structure

```
tllac/
 ├── app/
 │    ├── main.py                    # FastAPI application entry point
 │    ├── routes/
 │    │    └── chat.py               # POST /chat endpoint
 │    ├── services/
 │    │    ├── llm_service.py        # Response generation (template-based)
 │    │    └── validation_service.py # Indian legal context + data validation
 │    ├── data/
 │    │    └── trained_data.json     # Structured Indian legal knowledge base
 │    ├── db/
 │    │    └── db_client.py          # Read-only DB client (placeholder)
 │    └── utils/
 │         └── prompt_builder.py     # System prompt (strict Indian law rules)
 ├── requirements.txt
 └── README.md
```

---

## 🚀 Quick Start

### 1. Create a virtual environment

```bash
cd tllac
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the backend

```bash
uvicorn app.main:app --reload --port 9001
```

The server will start at `http://localhost:9001`.

- **API Docs**: http://localhost:9001/docs
- **Health Check**: http://localhost:9001/

---

## 🔗 API Contract

### `POST /chat`

**Request:**
```json
{
  "query": "What is adverse possession in India?"
}
```

**Response:**
```json
{
  "response": "🔎 Adverse Possession (India)\n\n**Summary:**\n..."
}
```

### Fallback Responses

| Condition | Response |
|-----------|----------|
| Query not related to Indian law | `"This is out of context"` |
| No matching trained data found | `"This is not in my trained data"` |

---

## 🧠 System Prompt (Strict)

Located in `app/utils/prompt_builder.py`. The system enforces:

1. **ONLY** Indian legal system context
2. **NO** global / US / UK / generic legal answers
3. **NO** hallucination — only facts from trained data
4. Structured response format (Title → Summary → Key Points → Law)
5. Mandatory fallback when unsure

---

## 🔐 Isolation Rules

| Rule | Status |
|------|--------|
| No imports from existing LAW LLM modules | ✅ |
| No `legal_engine`, `legal_pipeline`, `retrieval_api` | ✅ |
| No `rag_embeddings` or any shared backend code | ✅ |
| No external API calls | ✅ |
| No live web search | ✅ |
| Independent virtual environment | ✅ |
| Runs on separate port (9001) | ✅ |

---

## 📊 Trained Data Topics

The `trained_data.json` file contains structured knowledge on:

| # | Topic | Primary Law |
|---|-------|-------------|
| 1 | Adverse Possession | Limitation Act, 1963 |
| 2 | Contract Law | Indian Contract Act, 1872 |
| 3 | AI Regulations | DPDP Act, IT Act |
| 4 | Property Disputes | Transfer of Property Act, 1882 |
| 5 | Fundamental Rights | Constitution of India, Part III |
| 6 | IPC Offences | IPC, 1860 / BNS, 2023 |
| 7 | Bail Provisions | CrPC, 1973 / BNSS, 2023 |
| 8 | Consumer Protection | Consumer Protection Act, 2019 |
| 9 | Divorce Law | Hindu Marriage Act, 1955 + others |
| 10 | Right to Information | RTI Act, 2005 |
| 11 | GST | Central GST Act, 2017 |
| 12 | Cyber Crime | IT Act, 2000 |
| 13 | Labour Law | Four Labour Codes (2019–2020) |
| 14 | Writ Jurisdiction | Constitution Articles 32, 226 |
| 15 | Motor Accident Claims | Motor Vehicles Act, 1988 |

---

## 🔗 Frontend Integration

The experimental chat UI must call **only**:

```
POST http://localhost:9001/chat
```

❌ Must NOT call any existing LAW LLM backend endpoints.

---

## 📝 License

Internal project — Cialfor Research Labs.
