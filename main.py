from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.config import settings
from app.routers import chat_router, timeline_router
from app.utils import setup_logging
from app.agents.orchestrator import create_mortgage_broker_orchestrator

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    setup_logging()

    logger = logging.getLogger("app.main")
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Debug mode: {settings.debug}")

    app.state.orchestrator = create_mortgage_broker_orchestrator()
    logger.info("Created global orchestrator agent")

    try:
        yield
    finally:
        logger.info("Shutting down application")
        app.state.orchestrator = None


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="A FastAPI application for mortgage analysis using financial documents",
    lifespan=lifespan,
    debug=settings.debug,
)

app.state.orchestrator = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

app.include_router(chat_router)
app.include_router(timeline_router)


@app.get("/")
async def root():
    """Root endpoint returning basic API information."""
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "status": "operational",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": settings.app_version,
    }
