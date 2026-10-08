"""Bounded process-local configuration cache; OCR execution never uses it."""

from copy import deepcopy
from threading import Condition
from time import monotonic

from sqlalchemy import event

from app.db.diagnostics import current_stats
from app.db.models import Category, DocumentType, OCRModel, PipelineConfig


class ConfigCache:
    def __init__(self, ttl=60, clock=monotonic):
        self.ttl, self.clock = ttl, clock
        self._entries = {}
        self._condition = Condition()
        self._versions = {}
        self._loading = set()

    def get(self, key, load, *, fresh=False):
        with self._condition:
            if fresh:
                self.invalidate(key)
            while True:
                entry = self._entries.get(key)
                stats = current_stats.get()
                if entry and entry[0] > self.clock():
                    if stats:
                        stats.cache_hits += 1
                    return deepcopy(entry[1])
                version = self._versions.get(key, 0)
                flight = (key, version)
                if flight not in self._loading:
                    self._loading.add(flight)
                    started = self.clock()
                    break
                self._condition.wait()
        if stats:
            stats.cache_misses += 1
        try:
            # Never hold the cache lock while checking out a connection or querying.
            # A successful commit can invalidate without waiting for a slow reader.
            value = load()
            with self._condition:
                if self._versions.get(key, 0) == version:
                    self._entries[key] = (started + self.ttl, deepcopy(value))
            return value
        finally:
            with self._condition:
                self._loading.discard(flight)
                self._condition.notify_all()

    def invalidate(self, *keys):
        with self._condition:
            for key in keys:
                self._entries.pop(key, None)
                self._versions[key] = self._versions.get(key, 0) + 1
            self._condition.notify_all()


def install_invalidation(session_factory, cache):
    @event.listens_for(session_factory, "after_flush")
    def changed(session, context):
        keys = session.info.setdefault("changed_catalogs", set())
        for record in session.new | session.dirty | session.deleted:
            if isinstance(record, (PipelineConfig, OCRModel)):
                keys.update(("pipelines", "models"))
            elif isinstance(record, DocumentType):
                keys.add("document-types")
            elif isinstance(record, Category):
                keys.add("categories")

    @event.listens_for(session_factory, "after_commit")
    def committed(session):
        cache.invalidate(*session.info.pop("changed_catalogs", ()))

    @event.listens_for(session_factory, "after_rollback")
    def rolled_back(session):
        session.info.pop("changed_catalogs", None)


def catalog(request, key, load, *, fresh=False):
    def read():
        with request.app.state.database.session_factory() as session:
            return load(session)

    return request.app.state.config_cache.get(key, read, fresh=fresh)
