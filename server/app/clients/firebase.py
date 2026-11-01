"""Firebase Realtime Database Client (REST & InMemory).

Contract (PLAN.md Section 5.1 & Section 9):
Paths:
  /intersections/{id}/command
  /intersections/{id}/state
  /intersections/{id}/heartbeat
"""

import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class FirebaseClientBase(ABC):
    """Abstract interface shared by RestFirebase and InMemoryFirebase."""

    @abstractmethod
    def get_command(self, intersection_id: str = "i1") -> dict[str, Any] | None:
        pass

    @abstractmethod
    def set_command(self, command: dict[str, Any], intersection_id: str = "i1") -> None:
        pass

    @abstractmethod
    def get_state(self, intersection_id: str = "i1") -> dict[str, Any] | None:
        pass

    def get_state_age_s(self, intersection_id: str = "i1") -> float | None:
        """Age of the last state value received from the controller, if known."""
        return None

    @abstractmethod
    def set_state(self, state: dict[str, Any], intersection_id: str = "i1") -> None:
        pass

    @abstractmethod
    def get_heartbeat(self, intersection_id: str = "i1") -> int:
        pass

    @abstractmethod
    def increment_heartbeat(self, intersection_id: str = "i1") -> int:
        pass

    @abstractmethod
    def health_check(self) -> bool:
        pass


class InMemoryFirebase(FirebaseClientBase):
    """Thread-safe in-memory mailbox for offline execution and tests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._commands: dict[str, dict[str, Any] | None] = {}
        self._states: dict[str, dict[str, Any] | None] = {}
        self._state_updated_at: dict[str, float] = {}
        self._heartbeats: dict[str, int] = {}

    def get_command(self, intersection_id: str = "i1") -> dict[str, Any] | None:
        with self._lock:
            cmd = self._commands.get(intersection_id)
            return dict(cmd) if cmd else None

    def set_command(self, command: dict[str, Any], intersection_id: str = "i1") -> None:
        with self._lock:
            self._commands[intersection_id] = dict(command)

    def get_state(self, intersection_id: str = "i1") -> dict[str, Any] | None:
        with self._lock:
            state = self._states.get(intersection_id)
            return dict(state) if state else None

    def set_state(self, state: dict[str, Any], intersection_id: str = "i1") -> None:
        with self._lock:
            self._states[intersection_id] = dict(state)
            self._state_updated_at[intersection_id] = time.time()

    def get_state_age_s(self, intersection_id: str = "i1") -> float | None:
        with self._lock:
            updated_at = self._state_updated_at.get(intersection_id)
        return max(0.0, time.time() - updated_at) if updated_at is not None else None

    def get_heartbeat(self, intersection_id: str = "i1") -> int:
        with self._lock:
            return self._heartbeats.get(intersection_id, 0)

    def increment_heartbeat(self, intersection_id: str = "i1") -> int:
        with self._lock:
            val = self._heartbeats.get(intersection_id, 0) + 1
            self._heartbeats[intersection_id] = val
            return val

    def health_check(self) -> bool:
        return True


class RestFirebase(FirebaseClientBase):
    """Realtime Database client using standard Firebase REST endpoints."""

    def __init__(self, db_url: str, db_secret: str | None = None, timeout_s: float = 3.0) -> None:
        self.db_url = db_url.rstrip("/")
        self.db_secret = db_secret
        self.timeout = timeout_s
        self._client = httpx.Client(timeout=timeout_s)
        self._state_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
        self._state_progress: dict[str, tuple[int | float, float]] = {}
        self._heartbeat_cache: dict[str, tuple[float, int]] = {}
        self._cache_lock = threading.Lock()
        self._state_fetch_lock = threading.Lock()
        self._next_state_retry_at = 0.0

    def _url(self, path: str) -> str:
        url = f"{self.db_url}/{path.lstrip('/')}.json"
        if self.db_secret:
            url += f"?auth={self.db_secret}"
        return url

    def get_command(self, intersection_id: str = "i1") -> dict[str, Any] | None:
        try:
            resp = self._client.get(self._url(f"intersections/{intersection_id}/command"))
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, dict) else None
        except Exception as e:
            logger.error("RestFirebase get_command error: %s", e)
        return None

    def set_command(self, command: dict[str, Any], intersection_id: str = "i1") -> None:
        resp = self._client.put(
            self._url(f"intersections/{intersection_id}/command"),
            json=command,
        )
        resp.raise_for_status()

    def get_state(self, intersection_id: str = "i1") -> dict[str, Any] | None:
        with self._state_fetch_lock:
            now = time.time()
            with self._cache_lock:
                cached = self._state_cache.get(intersection_id)
            if cached and now - cached[0] < 0.2:
                return cached[1]
            if now < self._next_state_retry_at:
                return cached[1] if cached else None

            try:
                resp = self._client.get(self._url(f"intersections/{intersection_id}/state"))
                if resp.status_code == 200:
                    data = resp.json()
                    res = data if isinstance(data, dict) else None
                    with self._cache_lock:
                        self._state_cache[intersection_id] = (time.time(), res)
                        uptime = res.get("uptime_ms") if res else None
                        if isinstance(uptime, (int, float)):
                            previous = self._state_progress.get(intersection_id)
                            observed_at = time.time()
                            if previous is None or uptime < previous[0] or uptime != previous[0]:
                                self._state_progress[intersection_id] = (uptime, observed_at)
                    self._next_state_retry_at = 0.0
                    return res
                logger.warning("RestFirebase get_state returned HTTP %s", resp.status_code)
            except Exception as e:
                logger.error("RestFirebase get_state error: %s", e)
            self._next_state_retry_at = time.time() + 0.5
            with self._cache_lock:
                cached = self._state_cache.get(intersection_id)
                return cached[1] if cached else None

    def set_state(self, state: dict[str, Any], intersection_id: str = "i1") -> None:
        with self._cache_lock:
            self._state_cache[intersection_id] = (time.time(), state)
        try:
            resp = self._client.put(
                self._url(f"intersections/{intersection_id}/state"),
                json=state,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error("RestFirebase set_state error: %s", e)

    def get_state_age_s(self, intersection_id: str = "i1") -> float | None:
        with self._cache_lock:
            cached = self._state_cache.get(intersection_id)
            progress = self._state_progress.get(intersection_id)
        if not cached or cached[1] is None:
            return None
        timestamp = progress[1] if progress else cached[0]
        return max(0.0, time.time() - timestamp)

    def get_heartbeat(self, intersection_id: str = "i1") -> int:
        now = time.time()
        with self._cache_lock:
            cached = self._heartbeat_cache.get(intersection_id)
        if cached:
            ts, val = cached
            if now - ts < 1.0:
                return val

        try:
            resp = self._client.get(self._url(f"intersections/{intersection_id}/heartbeat"))
            if resp.status_code == 200 and resp.json() is not None:
                val = int(resp.json())
                with self._cache_lock:
                    self._heartbeat_cache[intersection_id] = (now, val)
                return val
        except Exception as e:
            logger.error("RestFirebase get_heartbeat error: %s", e)

        with self._cache_lock:
            cached = self._heartbeat_cache.get(intersection_id)
            return cached[1] if cached else 0

    def increment_heartbeat(self, intersection_id: str = "i1") -> int:
        current = self.get_heartbeat(intersection_id)
        next_val = current + 1
        with self._cache_lock:
            self._heartbeat_cache[intersection_id] = (time.time(), next_val)
        try:
            resp = self._client.put(
                self._url(f"intersections/{intersection_id}/heartbeat"),
                json=next_val,
            )
            resp.raise_for_status()
            return next_val
        except Exception as e:
            logger.error("RestFirebase increment_heartbeat error: %s", e)
            return next_val

    def health_check(self) -> bool:
        try:
            resp = self._client.get(self._url(".settings/rules"), timeout=2.0)
            return resp.status_code in (200, 401, 403)
        except Exception:
            return False


# Singleton instances
_in_memory_instance: InMemoryFirebase | None = None
_rest_instances: dict[tuple[str, str | None], RestFirebase] = {}
_client_factory_lock = threading.Lock()


def get_firebase_client(
    mode: str = "memory",
    db_url: str = "",
    db_secret: str | None = None,
) -> FirebaseClientBase:
    """Factory to retrieve appropriate Firebase client based on mode."""
    global _in_memory_instance
    if mode.lower() == "rest" and db_url:
        key = (db_url.rstrip("/"), db_secret)
        with _client_factory_lock:
            if key not in _rest_instances:
                _rest_instances[key] = RestFirebase(db_url, db_secret, timeout_s=3.0)
            return _rest_instances[key]
    if _in_memory_instance is None:
        _in_memory_instance = InMemoryFirebase()
    return _in_memory_instance
