"""MongoDB Client and InMemory fallback collection manager.

Contract (PLAN.md Section 3 & Section 5.3):
Sync pymongo client for plain def FastAPI endpoints.
Collections:
  - detections
  - events
  - commands
  - sim_runs
  - security_events
"""

import datetime
import logging
import threading
from abc import ABC, abstractmethod
from typing import Any

from pymongo import MongoClient

logger = logging.getLogger(__name__)


class MongoClientBase(ABC):
    """Abstract interface for database operations."""

    @abstractmethod
    def insert_detection(self, doc: dict[str, Any]) -> str:
        pass

    @abstractmethod
    def insert_event(self, doc: dict[str, Any]) -> str:
        pass

    @abstractmethod
    def update_event(self, event_id: str, updates: dict[str, Any]) -> bool:
        pass

    @abstractmethod
    def get_events(self, limit: int = 50, skip: int = 0) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    def insert_command(self, doc: dict[str, Any]) -> str:
        pass

    @abstractmethod
    def insert_sim_run(self, doc: dict[str, Any]) -> str:
        pass

    @abstractmethod
    def get_sim_run(self, run_id: str) -> dict[str, Any] | None:
        pass

    @abstractmethod
    def get_all_sim_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    def insert_security_event(self, doc: dict[str, Any]) -> str:
        pass

    @abstractmethod
    def get_security_events(self, limit: int = 50, skip: int = 0) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    def health_check(self) -> bool:
        pass


class InMemoryMongoClient(MongoClientBase):
    """Thread-safe in-memory collections for CI, offline tests, and mock mode."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.detections: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.commands: list[dict[str, Any]] = []
        self.sim_runs: dict[str, dict[str, Any]] = {}
        self.security_events: list[dict[str, Any]] = []

    def insert_detection(self, doc: dict[str, Any]) -> str:
        with self._lock:
            item = dict(doc)
            item.setdefault("received_at", datetime.datetime.now(datetime.UTC).isoformat())
            self.detections.append(item)
            return str(len(self.detections))

    def insert_event(self, doc: dict[str, Any]) -> str:
        with self._lock:
            item = dict(doc)
            item.setdefault("started_at", datetime.datetime.now(datetime.UTC).isoformat())
            self.events.append(item)
            return item.get("event_id", str(len(self.events)))

    def update_event(self, event_id: str, updates: dict[str, Any]) -> bool:
        with self._lock:
            for ev in self.events:
                if ev.get("event_id") == event_id:
                    ev.update(updates)
                    return True
            return False

    def get_events(self, limit: int = 50, skip: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            sorted_events = sorted(
                self.events,
                key=lambda x: str(x.get("started_at", "")),
                reverse=True,
            )
            return [dict(e) for e in sorted_events[skip : skip + limit]]

    def insert_command(self, doc: dict[str, Any]) -> str:
        with self._lock:
            item = dict(doc)
            item.setdefault("issued_at", datetime.datetime.now(datetime.UTC).isoformat())
            self.commands.append(item)
            return str(item.get("seq", len(self.commands)))

    def insert_sim_run(self, doc: dict[str, Any]) -> str:
        with self._lock:
            item = dict(doc)
            run_id = item.get("run_id", f"run_{len(self.sim_runs)+1}")
            item.setdefault("created_at", datetime.datetime.now(datetime.UTC).isoformat())
            self.sim_runs[run_id] = item
            return run_id

    def get_sim_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            val = self.sim_runs.get(run_id)
            return dict(val) if val else None

    def get_all_sim_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            runs = list(self.sim_runs.values())
            runs.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
            return [dict(r) for r in runs[:limit]]

    def insert_security_event(self, doc: dict[str, Any]) -> str:
        with self._lock:
            item = dict(doc)
            item.setdefault("ts", datetime.datetime.now(datetime.UTC).isoformat())
            self.security_events.append(item)
            return str(len(self.security_events))

    def get_security_events(self, limit: int = 50, skip: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            sorted_sec = sorted(
                self.security_events,
                key=lambda x: str(x.get("ts", "")),
                reverse=True,
            )
            return [dict(s) for s in sorted_sec[skip : skip + limit]]

    def health_check(self) -> bool:
        return True


class PyMongoClient(MongoClientBase):
    """Synchronous PyMongo client."""

    def __init__(self, uri: str, db_name: str) -> None:
        self.client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        self.db = self.client[db_name]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        try:
            self.db.detections.create_index("received_at")
            self.db.events.create_index("started_at")
            self.db.security_events.create_index("ts")
            self.db.sim_runs.create_index("run_id", unique=True)
        except Exception as e:
            logger.warning("Could not create mongo indexes: %s", e)

    def insert_detection(self, doc: dict[str, Any]) -> str:
        item = dict(doc)
        item.setdefault("received_at", datetime.datetime.now(datetime.UTC).isoformat())
        res = self.db.detections.insert_one(item)
        return str(res.inserted_id)

    def insert_event(self, doc: dict[str, Any]) -> str:
        item = dict(doc)
        item.setdefault("started_at", datetime.datetime.now(datetime.UTC).isoformat())
        res = self.db.events.insert_one(item)
        return item.get("event_id", str(res.inserted_id))

    def update_event(self, event_id: str, updates: dict[str, Any]) -> bool:
        res = self.db.events.update_one({"event_id": event_id}, {"$set": updates})
        return res.modified_count > 0

    def get_events(self, limit: int = 50, skip: int = 0) -> list[dict[str, Any]]:
        cursor = self.db.events.find({}, {"_id": 0}).sort("started_at", -1).skip(skip).limit(limit)
        return list(cursor)

    def insert_command(self, doc: dict[str, Any]) -> str:
        item = dict(doc)
        item.setdefault("issued_at", datetime.datetime.now(datetime.UTC).isoformat())
        res = self.db.commands.insert_one(item)
        return str(res.inserted_id)

    def insert_sim_run(self, doc: dict[str, Any]) -> str:
        item = dict(doc)
        item.setdefault("created_at", datetime.datetime.now(datetime.UTC).isoformat())
        self.db.sim_runs.replace_one({"run_id": item["run_id"]}, item, upsert=True)
        return str(item["run_id"])

    def get_sim_run(self, run_id: str) -> dict[str, Any] | None:
        return self.db.sim_runs.find_one({"run_id": run_id}, {"_id": 0})

    def get_all_sim_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self.db.sim_runs.find({}, {"_id": 0}).sort("created_at", -1).limit(limit))

    def insert_security_event(self, doc: dict[str, Any]) -> str:
        item = dict(doc)
        item.setdefault("ts", datetime.datetime.now(datetime.UTC).isoformat())
        res = self.db.security_events.insert_one(item)
        return str(res.inserted_id)

    def get_security_events(self, limit: int = 50, skip: int = 0) -> list[dict[str, Any]]:
        cursor = self.db.security_events.find({}, {"_id": 0}).sort("ts", -1).skip(skip).limit(limit)
        return list(cursor)

    def health_check(self) -> bool:
        try:
            self.client.admin.command("ping")
            return True
        except Exception:
            return False


_in_memory_mongo: InMemoryMongoClient | None = None


def get_mongo_client(
    mode: str = "memory",
    uri: str = "mongodb://localhost:27017",
    db_name: str = "smart_intersection",
) -> MongoClientBase:
    """Factory retrieving appropriate Mongo client."""
    global _in_memory_mongo
    if mode.lower() == "mongo":
        try:
            return PyMongoClient(uri, db_name)
        except Exception as e:
            logger.warning("Failed to connect to Mongo (%s), falling back to in-memory", e)
    if _in_memory_mongo is None:
        _in_memory_mongo = InMemoryMongoClient()
    return _in_memory_mongo
