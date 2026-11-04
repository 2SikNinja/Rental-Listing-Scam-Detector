"""
Database connection pool.

A pool keeps a few open connections and lends them out per request,
instead of opening a new connection (slow: TLS handshake plus login) for
every analysis.

Persistence is optional (PERSISTENCE_ENABLED). With it off, the API still
analyzes listings; it just doesn't remember them. That keeps local
development and tests free of a database dependency.
"""

from functools import lru_cache
import logging

from psycopg_pool import ConnectionPool

from app.config import getSettings

logger = logging.getLogger(__name__)


@lru_cache
def getConnectionPool() -> ConnectionPool | None:
    settings = getSettings()
    if not settings.persistenceEnabled:
        return None
    return ConnectionPool(
        conninfo=settings.databaseUrl.get_secret_value(),
        min_size=1,
        max_size=4,          # Cloud Run instances are small; Supabase free tier limits connections
        timeout=5,           # seconds to wait for a free connection before giving up
        open=True,
        # Supabase's connection pooler doesn't support server-side
        # prepared statements, so psycopg must not create them.
        kwargs={"prepare_threshold": None, "connect_timeout": 5},
        name="scamApiPool",
    )


def closeConnectionPool() -> None:
    connectionPool = getConnectionPool()
    if connectionPool is not None:
        connectionPool.close()
