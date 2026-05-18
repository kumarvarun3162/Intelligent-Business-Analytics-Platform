# backend/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from storage.database import init_db
from api.routes.upload import router as upload_router


# ── Lifespan: runs once at startup and shutdown ──────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup."""
    print("🚀 Starting IBAP backend...")
    init_db()
    print("✅ Database initialized")
    yield
    print("🛑 Shutting down IBAP backend...")


# ── App factory ──────────────────────────────────────────────────
app = FastAPI(
    title="IBAP — Intelligent Business Analytics Platform",
    description="Upload raw data, get cleaned data, insights, and interactive visualizations.",
    version="0.1.0",
    lifespan=lifespan,
)


# ── CORS ─────────────────────────────────────────────────────────
# In development: allow localhost:5173 (Vite dev server)
# In production: replace with your actual Render frontend URL
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ──────────────────────────────────────────────────────
app.include_router(upload_router)


# ── Health check ─────────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health_check():
    return {
        "status": "healthy",
        "app": "IBAP",
        "version": "0.1.0",
    }