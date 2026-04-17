# How to Run Legal AI on Your Local System (Mac)

Follow these steps to run the platform on your Mac while connecting to your remote AI server on Vast.ai.

### 1. Prerequisites
- **Python 3.10+** (Install via `brew install python`)
- **Node.js & npm** (Install via `brew install node`)
- **Virtual Environment**: 
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  ```

### 3. Run the Tools (2 Terminals Required)

You must run the following components in two separate terminal tabs/windows:

#### **Tab 1: Start the Legal AI Backend (Local Port 8000)**
This is your **FastAPI** logic. It is already configured to talk to your **AWS Qwen Server** at `13.203.229.0:8000`.
```bash
source venv/bin/activate
uvicorn retrieval_api:app --host 0.0.0.0 --port 8000
```

#### **Tab 2: Start the Legal AI Frontend (Local Port 3000)**
This is your **React** UI.
```bash
cd ui
npm run dev
```

### 4. Access the App
Open your browser to: **[http://localhost:3000](http://localhost:3000)**

### 5. Share on Your Local Network
Because the frontend now automatically calls the backend on the same host IP, your teammates can use your machine's LAN address directly as long as both services are running on your Mac.

Current LAN IP on this machine:
```text
10.16.140.253
```

Share this URL with teammates on the same network:
```text
http://10.16.140.253:3000
```

The frontend will call:
```text
http://10.16.140.253:8000
```

Important:
- Keep the backend running with `--host 0.0.0.0`
- Keep the frontend running with Vite host enabled
- Make sure macOS Firewall allows incoming connections for Python / node if prompted
- If your IP changes, share the new IP; no frontend code change is needed anymore

---
### Mode Selection:
- **Understand Case**: For general legal questions (RAG).
- **Query Act**: For direct section matching (Deterministic).


## 🏢 Sharing on Local Network (Team Access)

If you have stopped ngrok and want your team to access the app via your IP address:

### 1. Identify your Server IP
Your server's current IP is: `13.203.229.0`

### 2. Configure Frontend
I have updated your `/Volumes/Expansion/AI Legal/New code/ui/.env` to point directly to your IP:
```env
VITE_API_BASE_URL=http://13.203.229.0:8001
```

### 3. Share the Link
Your team can now access the assistant at:
`http://10.16.140.253:3000`

> [!IMPORTANT]
> If your computer's IP address changes, you will need to update the `.env` file and restart the UI.

---
## 🏛 Data Management (Re-indexing)

If you add new legal documents or need to update the AI's knowledge base with the new high-performance **BGE-large** (1024-dim) model:

### 1. Re-index Statutory Acts
Run this command from the root directory:
```bash
./venv/bin/python3 embed_acts.py build --json-dir JSON_acts --output-dir embedding_acts
```

### 2. Re-index Judicial Judgements
Run this command from the root directory:
```bash
./venv/bin/python3 embed_judgements.py build --json-dir json_judgements --output-dir embedding_judgements
```

> [!NOTE]
> The source directories (`JSON_acts` and `json_judgements`) should contain your legal documents in structured JSON format.
