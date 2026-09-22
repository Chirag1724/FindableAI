from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthCheckResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """System health check endpoint."""
    return HealthCheckResponse(status="healthy", service="FindableAI Core API", version="0.1.0")
