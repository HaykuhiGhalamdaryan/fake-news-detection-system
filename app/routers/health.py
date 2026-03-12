#health.py

from fastapi import APIRouter

router = APIRouter(
    prefix="/health",
    tags=["Health"]
)

@router.get("/")
def health_check():
    """
    Health check endpoint.
    Used to verify that the API is running.
    """
    return {
        "status": "ok",
        "service": "Fake News Detection API"
    }
