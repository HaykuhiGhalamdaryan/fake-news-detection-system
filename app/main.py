# main.py

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.routers import analyze, health, history, analytics
from app.database.db import engine
from app.database import models
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Fake News Detection System",
    description="Social Media Fake News & Credibility Analysis",
    version="1.0"
)

# --- CORS: allow browser to call the API from index.html ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Global error handler ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error("UNHANDLED EXCEPTION on %s\n%s", request.url, tb)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "traceback": tb},
    )

# --- Routers ---
app.include_router(analyze.router)
app.include_router(health.router)
app.include_router(history.router)
app.include_router(analytics.router)

# --- Serve static files (index.html) ---
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Root: open index.html directly at http://127.0.0.1:8000 ---
@app.get("/")
def root():
    return FileResponse("static/index.html")