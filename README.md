# 📊 Intelligent Business Analytics Platform (IBAP)

An **end-to-end Business Intelligence and Analytics platform** that empowers companies to transform raw business data into actionable insights. IBAP automates data cleaning, preprocessing, feature engineering, statistical analysis, and generates **interactive dashboards** with **AI-driven narrated reports**.

🔗 **Live Demo:** [Intelligent Business Analytics Platform](https://intelligent-business-analytics-platform.onrender.com)

---

## 🚀 Key Features
- **Automated Data Pipeline**: Upload raw CSV/Excel/JSON → cleaning → feature engineering → analysis → visualization → narrated report.
- **AI-Powered Insights**: Uses Groq LLM (Llama-3.3-70B) for natural language explanations and PDF reports.
- **Interactive Dashboards**: Built with Plotly.js for dynamic visualizations.
- **One-Click Deployment**: Render Blueprint support for easy deployment.
- **Business-Ready Outputs**: Generates Power BI–ready datasets and PDF reports.

---

## 🛠 Tech Stack
- **Backend**: FastAPI + Uvicorn (Python 3.11)  
- **Frontend**: React 19 + Vite + Tailwind v4  
- **Visualization**: Plotly.js  
- **AI/LLM**: Groq API (free tier)  
- **Storage**: SQLite + Render Disk  
- **Deployment**: Render (single web service + 1 GB disk)  
- **PDF Reports**: WeasyPrint  

---

## ⚙️ Pipeline Workflow
| Phase | Endpoint | Description |
|-------|----------|-------------|
| 1 | `POST /api/upload` | Ingest CSV/Excel/JSON |
| 2 | `POST /api/clean` | 8-stage cleaning + quality score |
| 3 | `POST /api/engineer` | Encoding, scaling, feature derivation |
| 4 | `POST /api/analyze` | EDA, correlations, PCA, hypothesis tests |
| 5 | `POST /api/charts` | Interactive Plotly dashboard |
| 6 | `POST /api/report/generate` | AI narration + PDF + data passport |

---

## 💻 Local Development

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # Add GROQ_API_KEY
uvicorn main:app --reload --port 8080
```

### Frontend
```bash
cd frontend
npm install
npm run dev   # Runs on localhost:5173
```

---

## 🔑 Environment Variables
Configure in `backend/.env`:
- `GROQ_API_KEY` → Required for LLM narration

---

## ☁️ Deployment
Deploy instantly with Render using `render.yaml`.  
Supports **one-click deployment** with Render Blueprint.

---

## 📘 About
IBAP is designed for **business analysts, data scientists, and enterprises** who want to streamline analytics workflows. It bridges the gap between raw data and **decision-ready insights**, reducing manual effort and enabling faster reporting.

---

## 📂 Repository Structure
- `backend/` → FastAPI services  
- `frontend/` → React + Vite UI  
- `render.yaml` → Deployment config  
- `test_data.csv` → Sample dataset  

---

## 🤝 Contributing
Contributions are welcome!  
- Fork the repo  
- Create a feature branch  
- Submit a pull request  

---

## 📜 License
This project is licensed under the MIT License.

---

👉 Would you like me to also create a **visual architecture diagram** (backend ↔ frontend ↔ AI ↔ database) for the README to make it more appealing?
