<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# Run frontend with your Legal RAG backend

This frontend now uses `src/components/LegalChat.tsx` as the default module and calls your FastAPI backend at `/query`.

## Run locally

**Prerequisites:**  Node.js

1. Install dependencies:
   `npm install`
2. Optional: set backend URL in `.env.local`:
   `VITE_API_BASE_URL=http://localhost:8000`
   If you do not set this, the frontend will automatically call `http://<current-browser-host>:8000`.
3. Start the frontend:
   `npm run dev`
4. Start backend (from `New code` folder):
   `venv/bin/python retrieval_api.py`

## Share with teammates on the same network

1. Start backend on all interfaces:
   `uvicorn retrieval_api:app --host 0.0.0.0 --port 8000`
2. Start frontend:
   `npm run dev`
3. Share your machine IP and Vite port:
   `http://10.16.140.253:3000`

Because the frontend now resolves the backend from the browser host, users opening the UI from your IP will automatically hit:
`http://10.16.140.253:8000`
