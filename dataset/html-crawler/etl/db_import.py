"""Shared Postgres import helpers: ID cache, batching, reconnect."""

from __future__ import annotations

import logging
from typing import Any, Callable, TypeVar

try:
    import psycopg
    from psycopg import OperationalError
except ImportError:  # pragma: no cover
    psycopg = None
    OperationalError = Exception  # type: ignore[misc, assignment]

LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_BATCH_SIZE = 500
DEFAULT_PROGRESS_EVERY = 500


def connect_db(db_url: str) -> Any:
    if psycopg is None:
        raise RuntimeError("psycopg is required")
    return psycopg.connect(db_url)


def preload_ids(connection: Any, table: str, *, schema: str = "public") -> set[str]:
    sql = f"SELECT id::text FROM {schema}.{table}"
    ids: set[str] = set()
    with connection.cursor() as cursor:
        cursor.execute(sql)
        for (entity_id,) in cursor.fetchall():
            if entity_id is not None:
                ids.add(str(entity_id))
    return ids


def with_reconnect(
    connection: Any,
    db_url: str,
    operation: Callable[[Any], T],
) -> tuple[T, Any]:
    try:
        return operation(connection), connection
    except OperationalError as exc:
        LOGGER.warning("connection lost, reconnecting: %s", exc)
        try:
            connection.close()
        except Exception:
            pass
        new_connection = connect_db(db_url)
        return operation(new_connection), new_connection


def log_progress(label: str, stats: Any, *, every: int) -> None:
    if stats.scanned % every != 0:
        return
    versioned = getattr(stats, "versioned", 0)
    LOGGER.info(
        "%s progress scanned=%s inserted=%s updated=%s versioned=%s skipped=%s failed=%s",
        label,
        stats.scanned,
        stats.inserted,
        stats.updated,
        versioned,
        stats.skipped,
        stats.failed,
    )
