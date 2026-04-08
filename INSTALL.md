# Installation and Setup Guide

This guide explains how to set up and run the Legal AI Assistant on your local machine (Mac/Linux) while connecting to your **vLLM Inference Engine** on Vast.ai.

## 1. Prerequisites

- **Python 3.10+** (recommended: 3.12)
- **Node.js 18+ and npm**
- **Vast.ai Instance**: Using the "vLLM Inference Engine" template.

## 2. Vast.ai Configuration (Important!)

Before running the code, ensure your Vast.ai instance is configured correctly:

1.  **VLLM_MODEL**: In your Vast.ai instance settings, ensure `VLLM_MODEL` is set to the model you intend to use (e.g., `Qwen/Qwen2.5-7B-Instruct`).
2.  **Get Your Token**: Click the **"Open"** button on your Vast.ai instance or run `echo $OPEN_BUTTON_TOKEN` in the instance terminal. **Copy this token.**
3.  **Check IP & Port**: Your API endpoint is `http://13.203.229.0:8000`.

## 3. Local Environment Setup

From the project root directory:

```bash
# 1. Create a virtual environment
python3 -m venv venv

# 2. Activate the virtual environment
source venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Set your API Token (If your cloud LLM requires one)
# export QWEN_API_KEY="<YOUR_TOKEN>"

# 5. Set Model Name (Ensure this matches the VLLM_MODEL on Vast.ai)
export QWEN_MODEL_NAME="Qwen/Qwen2.5-7B-Instruct"
```

## 4. Frontend Setup

```bash
cd ui
npm install
cd ..
```

## 5. How to Run

### Step 1: Start the Backend API
```bash
# Ensure venv is active and environment variables are set
uvicorn retrieval_api:app --reload --port 8000
```

### Step 2: Start the Frontend UI
In a **new terminal tab**:
```bash
cd ui
npm run dev
```

### Step 3: Access the App
Open your browser to: **[http://localhost:5173](http://localhost:5173)**

---

## Configuration Reference
- **LLM API Endpoint**: `http://13.203.229.0:8000/v1/chat/completions`
- **Backend Port**: `8000`
- **Frontend Port**: `5173`
