<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# Run frontend with your Legal RAG backend

This frontend now uses `src/components/LegalChat.tsx` as the default module and calls your backend through `/api` by default.

## Run locally

**Prerequisites:**  Node.js

1. Install dependencies:
   `npm install`
2. Optional: set backend URL in `.env.local`:
   `VITE_API_BASE_URL=http://localhost:8000`
   If you do not set this, the frontend will call `/api` (recommended with reverse proxy).
3. Start the frontend:
   `npm run dev`
4. Start backend (from `New code` folder):
   `venv/bin/python retrieval_api.py`

## Share with teammates on the same network

1. Configure your reverse proxy to route `/api/*` to your backend service.
2. Start frontend:
   `npm run dev`
3. Share your frontend URL.

The frontend keeps API endpoints configurable via `VITE_API_BASE_URL` and does not hardcode server IP/port in source files.
