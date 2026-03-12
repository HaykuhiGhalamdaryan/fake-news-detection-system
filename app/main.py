# main.py

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.routers import analyze, health, history, analytics
from app.database.db import engine
from app.database import models

from dotenv import load_dotenv
load_dotenv() 

# Force full tracebacks to appear in the terminal
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Fake News Detection System",
    description="Social Media Fake News & Credibility Analysis",
    version="1.0"
)

# --- Global error handler: prints full traceback to terminal ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error("UNHANDLED EXCEPTION on %s\n%s", request.url, tb)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "traceback": tb},
    )

app.include_router(analyze.router)
app.include_router(health.router)
app.include_router(history.router)
app.include_router(analytics.router)

@app.get("/")
def root():
    return {"status": "Fake News Detection API is running"}