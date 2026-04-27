"""
Health check endpoint for load balancer and monitoring.
"""

import logging
from fastapi import APIRouter
import redis.asyncio as aioredis
from sqlalchemy import text

from app.db.session import async_session_factory
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """
    Comprehensive health check endpoint.
    
    Checks:
    - Application status
    - PostgreSQL connectivity
    - Redis connectivity
    
    Returns 200 if all services are healthy, 503 if any check fails.
    Used by Nginx for upstream health monitoring.
    """
    health = {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "checks": {},
    }

    # Check PostgreSQL
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        health["checks"]["postgres"] = "ok"
    except Exception as e:
        health["checks"]["postgres"] = f"error: {str(e)}"
        health["status"] = "unhealthy"

    # Check Redis
    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.close()
        health["checks"]["redis"] = "ok"
    except Exception as e:
        health["checks"]["redis"] = f"error: {str(e)}"
        health["status"] = "unhealthy"

    status_code = 200 if health["status"] == "healthy" else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(content=health, status_code=status_code)
