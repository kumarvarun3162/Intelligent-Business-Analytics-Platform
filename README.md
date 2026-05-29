# IBAP — Intelligent Business Analytics Platform

Upload raw data → automated cleaning → feature engineering →
statistical analysis → interactive dashboard → LLM-narrated report.

## Live demo
https://ibap.onrender.com

## Tech stack
- **Backend**: FastAPI + Uvicorn (Python 3.11)
- **Frontend**: React 19 + Vite + Tailwind v4
- **Charts**: Plotly.js (direct, no react-plotly.js)
- **LLM**: Groq API (llama-3.3-70b-versatile) — free tier
- **PDF**: WeasyPrint
- **Storage**: SQLite + Render Disk
- **Deployment**: Render (single web service + 1 GB disk)

## Local development

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # fill in GROQ_API_KEY
uvicorn main:app --reload --port 8080
```

### Frontend
```bash
cd frontend
npm install
npm run dev                    # runs on localhost:5173
```

## Pipeline
| Phase | Endpoint | What it does |
|---|---|---|
| 1 | POST /api/upload | Ingest CSV/Excel/JSON |
| 2 | POST /api/clean | 8-stage cleaning + quality score |
| 3 | POST /api/engineer | Encoding, scaling, feature derivation |
| 4 | POST /api/analyze | EDA, correlations, PCA, hypothesis tests |
| 5 | POST /api/charts | Interactive Plotly dashboard |
| 6 | POST /api/report/generate | Groq LLM narration + PDF + data passport |

## Environment variables
See `backend/.env.example`

## Deployment
See `render.yaml` — one-click deploy via Render Blueprint.