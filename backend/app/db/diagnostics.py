"""Opt-in numeric diagnostics; never retain SQL, parameters, or result contents.

Bytes estimate UTF-8 representations of fetched DBAPI values, not PostgreSQL wire
traffic or Neon billing. Disabled by default, including cursor wrapping.
"""

import json
import logging
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from time import perf_counter

from sqlalchemy import event


@dataclass
class ReadStats:
    queries: int = 0
    query_ms: float = 0
    rows: int = 0
    estimated_result_bytes: int = 0
    checkouts: int = 0
    connections: int = 0
    cache_hits: int = 0
    cache_misses: int = 0


current_stats: ContextVar[ReadStats | None] = ContextVar("db_read_stats", default=None)
logger = logging.getLogger("app.db.diagnostics")


class CountingCursor:
    def __init__(self, cursor, stats):
        self.cursor, self.stats = cursor, stats

    def __getattr__(self, name):
        return getattr(self.cursor, name)

    def count(self, rows):
        self.stats.rows += len(rows)
        self.stats.estimated_result_bytes += sum(
            len(json.dumps(tuple(row), ensure_ascii=False, default=str).encode("utf-8"))
            for row in rows
        )
        return rows

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is not None:
            self.count([row])
        return row

    def fetchall(self):
        return self.count(self.cursor.fetchall())

    def fetchmany(self, *args):
        return self.count(self.cursor.fetchmany(*args))

    def __iter__(self):
        return self

    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row


def install_diagnostics(engine):
    logger.setLevel(logging.INFO)
    if not logger.hasHandlers():
        logger.addHandler(logging.StreamHandler())

    @event.listens_for(engine, "before_cursor_execute")
    def before(connection, cursor, statement, parameters, context, many):
        if (stats := current_stats.get()) is not None:
            stats.queries += 1
            context._diagnostic_start = perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def after(connection, cursor, statement, parameters, context, many):
        stats = current_stats.get()
        if stats is not None:
            stats.query_ms += (perf_counter() - context._diagnostic_start) * 1000
            if cursor.description:
                context.cursor = CountingCursor(cursor, stats)

    @event.listens_for(engine, "checkout")
    def checkout(*args):
        if (stats := current_stats.get()) is not None:
            stats.checkouts += 1

    @event.listens_for(engine, "connect")
    def connect(*args):
        if (stats := current_stats.get()) is not None:
            stats.connections += 1


def log_stats(route, status, stats):
    logger.info("db_read %s", json.dumps(dict(route=route, status=status, **asdict(stats))))
