"""
FastAPI application entry point.

Initializes:
- Database connection pool
- Redis client (for caching and Pub/Sub)
- WebSocket connection manager
- Message broker (Redis Pub/Sub)
- Presence and typing services
- Rate limiter
- API routers

Uses the lifespan context manager for clean startup/shutdown.
"""

import logging
import os
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db.session import init_db, close_db
from app.messaging.connection_manager import ConnectionManager
from app.messaging.redis_broker import RedisBroker
from app.services.presence_service import PresenceService
from app.services.typing_service import TypingService
from app.core.rate_limiter import RateLimiter

from app.api.routes import auth, rooms, messages, health
from app.api.websocket import chat

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    try:
        await init_db()
        logger.info("Database initialized")

        redis_client = aioredis.from_url(
            settings.REDIS_URL, decode_responses=True, retry_on_timeout=True
        )
        app.state.redis_client = redis_client
        logger.info("Redis client connected")

        app.state.settings = settings
        app.state.connection_manager = ConnectionManager()
        app.state.presence_service = PresenceService(redis_client)
        app.state.typing_service = TypingService(redis_client)
        app.state.rate_limiter = RateLimiter(redis_client)

        redis_broker = RedisBroker()
        await redis_broker.connect()
        app.state.redis_broker = redis_broker
        logger.info("Redis Pub/Sub broker started")

        logger.info("DEBUG: ABOUT TO YIELD")
        yield  
        logger.info("DEBUG: YIELD FINISHED")

    except Exception as e:
        logger.error(f"Error in lifespan: {e}")
        raise

    logger.info("Shutting down...")
    await redis_broker.disconnect()
    await redis_client.close()
    await close_db()
    logger.info("Shutdown complete")


# === Create FastAPI app ===
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "A production-grade distributed real-time chat system built with "
        "FastAPI, WebSockets, Redis Pub/Sub, and PostgreSQL. "
        "Designed for horizontal scaling and fault tolerance."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# === CORS Middleware ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Register Routers ===
API_PREFIX = "/api/v1"
app.include_router(health.router)
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(rooms.router, prefix=API_PREFIX)
app.include_router(messages.router, prefix=API_PREFIX)
app.include_router(chat.router)

# === Static Files (Client) ===
client_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "client")
if os.path.exists(client_path):
    app.mount("/client", StaticFiles(directory=client_path, html=True), name="client")


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint — application info."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "client": "/client/index.html",
        "health": "/health",
    }
