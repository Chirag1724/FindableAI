import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1 import api_v1_router
from .api.v1.scans import router as scans_router
from .core.config import settings

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Connect to DB / Redis / Browser pool
    print(f"Starting {settings.PROJECT_NAME} API v{settings.VERSION} [{settings.ENVIRONMENT}]")
    yield
    # Shutdown: Clean up resources
    print(f"Shutting down {settings.PROJECT_NAME} API")


app = FastAPI(
    title="FindableAI API",
    description="Evidence-Grounded Autonomous Machine-Discoverability Optimization (MDO) Engine",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(api_v1_router)

# Mount alias for Contract 2 compatibility (/api/scans alongside /api/v1/scans)
app.include_router(scans_router, prefix="/api/scans", tags=["Scans (Contract 2)"])


@app.get("/")
async def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "documentation": "/docs",
        "api_v1": "/api/v1",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
