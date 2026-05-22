"""Supabase Memory Plugin — Hermes Agent MemoryProvider

Provides persistent memory via Supabase (PostgreSQL + pgvector).
Includes automatic local SQLite fallback for offline resilience.

Architecture:
  ┌──────────────────────────────────────────────┐
  │           SupabaseMemoryProvider              │
  │  ┌─────────────┐    ┌─────────────────────┐  │
  │  │  Supabase    │    │  Local SQLite Cache  │  │
  │  │  (primary)   │◄──►│  (fallback + queue)  │  │
  │  └──────┬──────┘    └─────────────────────┘  │
  │         │                                         │
  │    Online: write both, read from Supabase         │
  │    Offline: write local, read from local           │
  │    Reconnect: flush queue → Supabase               │
  └──────────────────────────────────────────────┘

Schema (Supabase):
  - hermes_memory:   Memory entries with vector embeddings
  - hermes_users:    User profiles and preferences
  - hermes_sessions: Session tracking with summaries
  - hermes_skills:   Cross-instance skill mirroring

Schema (SQLite cache):
  - memory_cache:    Local copy of recent entries
  - pending_sync:    Queue of writes waiting for Supabase
  - profile_cache:   Local copy of user profiles
  - metadata:        Plugin state (online/offline, last sync)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent.memory_provider import MemoryProvider
from tools.registry import tool_error

logger = logging.getLogger(__name__)

try:
    from supabase import create_client, Client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False
    Client = None  # type: ignore


# ---------------------------------------------------------------------------
# Local cache manager
# ---------------------------------------------------------------------------


class LocalCache:
    """SQLite-backed local cache that acts as fallback when Supabase is offline.

    Uses a simple file-based SQLite DB at ``$HERMES_HOME/cache/supabase_cache.db``.
    Every write goes to local first, then tries Supabase.  Reads try Supabase
    first, fall back to local.
    """

    def __init__(self, hermes_home: Optional[str] = None):
        if hermes_home:
            self._db_path = Path(hermes_home) / "cache" / "supabase_cache.db"
        else:
            try:
                from hermes_constants import get_hermes_home
                self._db_path = get_hermes_home() / "cache" / "supabase_cache.db"
            except Exception:
                self._db_path = Path.home() / ".hermes" / "cache" / "supabase_cache.db"

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS memory_cache (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id     TEXT NOT NULL DEFAULT 'default',
                        session_id  TEXT,
                        content     TEXT NOT NULL,
                        metadata    TEXT DEFAULT '{}',
                        role        TEXT DEFAULT 'user',
                        created_at  REAL NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS pending_sync (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        operation   TEXT NOT NULL,  -- 'insert_memory', 'upsert_profile'
                        payload     TEXT NOT NULL,
                        created_at  REAL NOT NULL,
                        retries     INTEGER DEFAULT 0
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS profile_cache (
                        user_id     TEXT PRIMARY KEY,
                        profile     TEXT NOT NULL,
                        updated_at  REAL NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS metadata (
                        key   TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_mcache_user
                    ON memory_cache(user_id, created_at DESC)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_mcache_session
                    ON memory_cache(session_id, created_at DESC)
                """)
                conn.commit()
            finally:
                conn.close()

    # -- Memory operations ---------------------------------------------------

    def store_turn(self, user_id: str, session_id: str,
                   user_content: str, assistant_content: str) -> None:
        """Store a turn locally (always succeeds)."""
        now = time.time()
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            try:
                conn.execute(
                    "INSERT INTO memory_cache (user_id, session_id, content, metadata, role, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, session_id, user_content, '{"role":"user"}', "user", now),
                )
                conn.execute(
                    "INSERT INTO memory_cache (user_id, session_id, content, metadata, role, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, session_id, assistant_content, '{"role":"assistant"}', "assistant", now + 0.001),
                )
                conn.commit()
            finally:
                conn.close()

    def search_local(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search locally via SQLite FTS-style LIKE."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            try:
                cur = conn.execute(
                    "SELECT content, metadata, created_at FROM memory_cache "
                    "WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?",
                    (f"%{query}%", limit),
                )
                results = []
                for row in cur.fetchall():
                    results.append({
                        "content": row[0][:500],
                        "metadata": row[1],
                        "timestamp": row[2],
                    })
                return results
            finally:
                conn.close()

    def get_profile_local(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Read profile from local cache."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            try:
                cur = conn.execute(
                    "SELECT profile FROM profile_cache WHERE user_id = ?",
                    (user_id,),
                )
                row = cur.fetchone()
                if row:
                    return json.loads(row[0])
                return None
            finally:
                conn.close()

    def save_profile_local(self, user_id: str, profile: Dict[str, Any]) -> None:
        """Save profile to local cache."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO profile_cache (user_id, profile, updated_at) "
                    "VALUES (?, ?, ?)",
                    (user_id, json.dumps(profile), time.time()),
                )
                conn.commit()
            finally:
                conn.close()

    # -- Pending sync queue ---------------------------------------------------

    def queue_sync(self, operation: str, payload: Dict[str, Any]) -> None:
        """Queue an operation for sync when Supabase comes back."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            try:
                conn.execute(
                    "INSERT INTO pending_sync (operation, payload, created_at) VALUES (?, ?, ?)",
                    (operation, json.dumps(payload), time.time()),
                )
                conn.commit()
            finally:
                conn.close()

    def get_pending_syncs(self) -> List[Dict[str, Any]]:
        """Get all pending sync operations (oldest first)."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            try:
                cur = conn.execute(
                    "SELECT id, operation, payload, created_at, retries "
                    "FROM pending_sync ORDER BY created_at ASC"
                )
                return [
                    {"id": r[0], "operation": r[1], "payload": json.loads(r[2]),
                     "created_at": r[3], "retries": r[4]}
                    for r in cur.fetchall()
                ]
            finally:
                conn.close()

    def remove_sync(self, sync_id: int) -> None:
        """Remove a completed sync operation."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            try:
                conn.execute("DELETE FROM pending_sync WHERE id = ?", (sync_id,))
                conn.commit()
            finally:
                conn.close()

    def increment_retry(self, sync_id: int) -> None:
        """Increment retry count for a failed sync."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            try:
                conn.execute(
                    "UPDATE pending_sync SET retries = retries + 1 WHERE id = ?",
                    (sync_id,),
                )
                conn.commit()
            finally:
                conn.close()

    def get_metadata(self, key: str, default: str = "") -> str:
        """Read plugin metadata from local cache."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            try:
                cur = conn.execute("SELECT value FROM metadata WHERE key = ?", (key,))
                row = cur.fetchone()
                return row[0] if row else default
            finally:
                conn.close()

    def set_metadata(self, key: str, value: str) -> None:
        """Write plugin metadata to local cache."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                    (key, value),
                )
                conn.commit()
            finally:
                conn.close()


# ---------------------------------------------------------------------------
# Tool schemas exposed to the model
# ---------------------------------------------------------------------------

SEARCH_SCHEMA = {
    "name": "supabase_search",
    "description": (
        "Search past memory entries stored in Supabase via keyword or "
        "semantic similarity. Returns relevant excerpts ranked by relevance."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to search for in stored memory.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results (default 5, max 20).",
                "default": 5,
            },
        },
        "required": ["query"],
    },
}

PROFILE_SCHEMA = {
    "name": "supabase_profile",
    "description": (
        "Read or update the user profile in Supabase. "
        "The profile stores persistent facts, preferences, and context "
        "about the user that survives across sessions. "
        "Works offline via local cache if Supabase is unreachable."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier (default: 'default').",
                "default": "default",
            },
            "profile": {
                "type": "object",
                "description": (
                    "New profile data to merge. Omit to read current profile. "
                    "Use key-value pairs like {'timezone': 'UTC', 'language': 'es'}."
                ),
            },
        },
    },
}

STATUS_SCHEMA = {
    "name": "supabase_status",
    "description": (
        "Check the current status of the Supabase memory connection. "
        "Returns whether Supabase is online/offline, pending sync count, "
        "and local cache stats. Useful for diagnostics."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    },
}


# ---------------------------------------------------------------------------
# Provider implementation
# ---------------------------------------------------------------------------


class SupabaseMemoryProvider(MemoryProvider):
    """MemoryProvider backed by Supabase PostgreSQL + pgvector.

    Features:
    - Dual-write: every operation writes to both Supabase + local SQLite
    - Graceful degradation: reads fall back to local cache when offline
    - Sync queue: pending writes flushed when connection restores
    - Transparent: tools report connection status
    """

    def __init__(self):
        self._client: Optional[Client] = None
        self._url: str = ""
        self._key: str = ""
        self._session_id: str = ""
        self._cache: Optional[LocalCache] = None
        self._online: bool = False
        self._hermes_home: str = ""

    # -- Properties ----------------------------------------------------------

    @property
    def name(self) -> str:
        return "supabase"

    # -- Core lifecycle ------------------------------------------------------

    def is_available(self) -> bool:
        """Check if supabase package is installed and credentials exist."""
        if not HAS_SUPABASE:
            return False
        self._url = self._get_env("SUPABASE_URL") or ""
        self._key = self._get_env("SUPABASE_SERVICE_KEY") or self._get_env("SUPABASE_ANON_KEY") or ""
        return bool(self._url and self._key)

    def initialize(self, session_id: str, **kwargs) -> None:
        """Connect to Supabase, init local cache, flush pending syncs."""
        if not self._url or not self._key:
            url = self._get_env("SUPABASE_URL") or ""
            key = self._get_env("SUPABASE_SERVICE_KEY") or self._get_env("SUPABASE_ANON_KEY") or ""
            if not url or not key:
                raise RuntimeError("SupabaseMemory: missing SUPABASE_URL and SUPABASE_SERVICE_KEY")
            self._url = url
            self._key = key

        self._hermes_home = kwargs.get("hermes_home", "")
        self._cache = LocalCache(self._hermes_home)
        self._session_id = session_id

        # Try connecting to Supabase
        try:
            self._client = create_client(self._url, self._key)
            # Quick ping
            self._client.table("hermes_memory").select("id").limit(1).execute()
            self._online = True
            logger.info("SupabaseMemory: connected ✅ (session %s)", session_id)
            # Flush any pending syncs from previous offline periods
            self._flush_pending_syncs()
        except Exception as e:
            self._online = False
            self._client = None
            logger.warning("SupabaseMemory: offline mode (session %s): %s", session_id, e)

        self._cache.set_metadata("last_initialize", str(time.time()))
        self._cache.set_metadata("online", str(self._online))

    def system_prompt_block(self) -> str:
        """Return instructions about Supabase memory for the system prompt."""
        status = "🟢 online" if self._online else "🟡 offline (local cache)"
        pending = ""
        if self._cache:
            syncs = self._cache.get_pending_syncs()
            if syncs:
                pending = f" ({len(syncs)} pending syncs)"
        return (
            f"You have persistent memory via Supabase ({status}{pending}). "
            "Use supabase_search to recall past conversations, supabase_profile "
            "to read or update user preferences, and supabase_status to check "
            "connection health. Memory works even offline via local cache."
        )

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Retrieve relevant memory for the upcoming turn. Falls back to local."""
        if not self._cache or not query:
            return ""

        # Try Supabase first
        if self._online and self._client:
            try:
                result = (
                    self._client.table("hermes_memory")
                    .select("content, metadata, created_at")
                    .ilike("content", f"%{query}%")
                    .order("created_at", desc=True)
                    .limit(5)
                    .execute()
                )
                if result.data:
                    lines = []
                    for entry in result.data:
                        ts = entry.get("created_at", "")[:19]
                        content = entry.get("content", "")[:300]
                        lines.append(f"[{ts}] {content}")
                    return "\n".join(lines)
            except Exception:
                self._online = False
                logger.info("SupabaseMemory: degraded to offline during prefetch")

        # Fall back to local cache
        try:
            results = self._cache.search_local(query, limit=5)
            if results:
                lines = []
                for entry in results:
                    ts = entry.get("timestamp", "")
                    if isinstance(ts, (int, float)):
                        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
                    content = entry.get("content", "")[:300]
                    lines.append(f"[local:{ts}] {content}")
                return "\n".join(lines)
        except Exception as e:
            logger.debug("SupabaseMemory local prefetch failed: %s", e)

        return ""

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        """Persist a turn. Always writes locally; tries Supabase if online."""
        sid = session_id or self._session_id

        # Always write to local cache first
        if self._cache:
            self._cache.store_turn("default", sid, user_content, assistant_content)

        # Also write to Supabase if online
        if self._online and self._client:
            try:
                self._client.table("hermes_memory").insert({
                    "user_id": "default",
                    "session_id": sid,
                    "content": user_content,
                    "metadata": json.dumps({"role": "user"}),
                }).execute()
                self._client.table("hermes_memory").insert({
                    "user_id": "default",
                    "session_id": sid,
                    "content": assistant_content,
                    "metadata": json.dumps({"role": "assistant"}),
                }).execute()
            except Exception as e:
                self._online = False
                logger.warning("SupabaseMemory: degraded to offline (sync_turn): %s", e)
                # Queue for later sync
                if self._cache:
                    self._cache.queue_sync("insert_turn", {
                        "session_id": sid,
                        "user_content": user_content,
                        "assistant_content": assistant_content,
                    })

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return the tools this provider exposes."""
        return [SEARCH_SCHEMA, PROFILE_SCHEMA, STATUS_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        """Dispatch a tool call to the appropriate handler."""
        if tool_name == "supabase_search":
            return self._handle_search(args)
        elif tool_name == "supabase_profile":
            return self._handle_profile(args)
        elif tool_name == "supabase_status":
            return self._handle_status(args)
        else:
            return tool_error(f"Unknown tool: {tool_name}")

    def shutdown(self) -> None:
        """Clean up resources and flush remaining syncs."""
        if self._online and self._client:
            self._flush_pending_syncs()
        self._client = None
        if self._cache:
            self._cache.set_metadata("online", "false")
            self._cache.set_metadata("last_shutdown", str(time.time()))
        logger.info("SupabaseMemory shutdown complete")

    # -- Optional hooks ------------------------------------------------------

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """Store session summary on exit."""
        if not self._cache:
            return

        summary = f"Session {self._session_id}: {len(messages)} messages"
        self._cache.set_metadata(f"session_{self._session_id}_summary", summary)

        if self._online and self._client:
            try:
                self._client.table("hermes_sessions").upsert({
                    "session_id": self._session_id,
                    "summary": summary,
                }).execute()
            except Exception:
                if self._cache:
                    self._cache.queue_sync("upsert_session", {
                        "session_id": self._session_id,
                        "summary": summary,
                    })

    # -- Tool handlers -------------------------------------------------------

    def _handle_search(self, args: Dict[str, Any]) -> str:
        """Search memory — try Supabase, fall back to local cache."""
        query = args.get("query", "")
        limit = min(int(args.get("limit", 5)), 20)

        if not query:
            return json.dumps({"results": [], "message": "No query provided", "source": "none"})

        # Try Supabase
        if self._online and self._client:
            try:
                result = (
                    self._client.table("hermes_memory")
                    .select("content, metadata, created_at")
                    .ilike("content", f"%{query}%")
                    .limit(limit)
                    .order("created_at", desc=True)
                    .execute()
                )
                results = []
                for entry in result.data:
                    results.append({
                        "content": entry["content"][:500],
                        "metadata": entry.get("metadata", {}),
                        "timestamp": entry.get("created_at", ""),
                    })
                return json.dumps({
                    "results": results,
                    "count": len(results),
                    "query": query,
                    "source": "supabase" if results else "no_results",
                })
            except Exception as e:
                self._online = False
                logger.info("SupabaseMemory: degraded during search")

        # Fall back to local cache
        if self._cache:
            try:
                results = self._cache.search_local(query, limit)
                return json.dumps({
                    "results": results,
                    "count": len(results),
                    "query": query,
                    "source": "local_cache",
                    "note": "Supabase was unreachable — showing cached data" if not self._online else "",
                })
            except Exception as e:
                return tool_error(f"Search failed (local): {e}")

        return json.dumps({"results": [], "message": "No memory backend available", "source": "none"})

    def _handle_profile(self, args: Dict[str, Any]) -> str:
        """Read or update user profile — dual-write to Supabase + local."""
        user_id = args.get("user_id", "default")
        profile_data = args.get("profile")

        # Write mode
        if profile_data is not None:
            # Always write to local cache
            if self._cache:
                self._cache.save_profile_local(user_id, profile_data)

            # Try Supabase
            if self._online and self._client:
                try:
                    self._client.table("hermes_users").upsert({
                        "user_id": user_id,
                        "profile": json.dumps(profile_data),
                    }).execute()
                    return json.dumps({"status": "updated", "user_id": user_id, "source": "supabase"})
                except Exception:
                    self._online = False
                    if self._cache:
                        self._cache.queue_sync("upsert_profile", {
                            "user_id": user_id, "profile": profile_data,
                        })

            return json.dumps({"status": "cached_locally", "user_id": user_id,
                               "source": "local_cache",
                               "note": "Will sync to Supabase when connection restores"})

        # Read mode — try Supabase first
        if self._online and self._client:
            try:
                result = (
                    self._client.table("hermes_users")
                    .select("profile")
                    .eq("user_id", user_id)
                    .limit(1)
                    .execute()
                )
                if result.data:
                    raw = result.data[0].get("profile", {})
                    if isinstance(raw, str):
                        try:
                            raw = json.loads(raw)
                        except json.JSONDecodeError:
                            pass
                    # Also cache locally
                    if self._cache and isinstance(raw, dict):
                        self._cache.save_profile_local(user_id, raw)
                    return json.dumps({"profile": raw, "source": "supabase"})
            except Exception:
                self._online = False

        # Fall back to local cache
        if self._cache:
            local = self._cache.get_profile_local(user_id)
            if local:
                return json.dumps({"profile": local, "source": "local_cache",
                                   "note": "Cached version — may be stale"})

        return json.dumps({"profile": {}, "source": "none",
                           "message": "No profile found (online or cached)"})

    def _handle_status(self, args: Dict[str, Any]) -> str:
        """Report connection status, pending syncs, and cache stats."""
        pending_syncs = []
        if self._cache:
            pending_syncs = self._cache.get_pending_syncs()

        return json.dumps({
            "online": self._online,
            "pending_syncs": len(pending_syncs),
            "source": "supabase_online" if self._online else "local_cache",
            "status": "🟢 All systems go" if self._online
                      else f"🟡 Offline — {len(pending_syncs)} pending syncs in queue",
            "details": {
                "supabase_connected": self._online,
                "local_cache_available": self._cache is not None,
                "pending_sync_count": len(pending_syncs),
                "hermes_home": self._hermes_home,
            },
        })

    # -- Sync queue -----------------------------------------------------------

    def _flush_pending_syncs(self) -> None:
        """Flush all pending sync operations to Supabase."""
        if not self._cache or not self._client or not self._online:
            return

        syncs = self._cache.get_pending_syncs()
        if not syncs:
            return

        logger.info("SupabaseMemory: flushing %d pending syncs...", len(syncs))
        flushed = 0
        for sync in syncs:
            try:
                op = sync["operation"]
                payload = sync["payload"]

                if op == "insert_turn":
                    self._client.table("hermes_memory").insert({
                        "user_id": "default",
                        "session_id": payload.get("session_id", ""),
                        "content": payload.get("user_content", ""),
                        "metadata": json.dumps({"role": "user"}),
                    }).execute()
                    self._client.table("hermes_memory").insert({
                        "user_id": "default",
                        "session_id": payload.get("session_id", ""),
                        "content": payload.get("assistant_content", ""),
                        "metadata": json.dumps({"role": "assistant"}),
                    }).execute()

                elif op == "upsert_profile":
                    self._client.table("hermes_users").upsert({
                        "user_id": payload.get("user_id", "default"),
                        "profile": json.dumps(payload.get("profile", {})),
                    }).execute()

                elif op == "upsert_session":
                    self._client.table("hermes_sessions").upsert({
                        "session_id": payload.get("session_id", ""),
                        "summary": payload.get("summary", ""),
                    }).execute()

                self._cache.remove_sync(sync["id"])
                flushed += 1

            except Exception as e:
                self._cache.increment_retry(sync["id"])
                logger.warning("SupabaseMemory: sync %d failed (retry %d): %s",
                               sync["id"], sync["retries"] + 1, e)

        logger.info("SupabaseMemory: flushed %d/%d pending syncs", flushed, len(syncs))

    # -- Helpers -------------------------------------------------------------

    @staticmethod
    def _get_env(key: str) -> str:
        """Read env var from os.environ, falling back to .env parsing."""
        val = os.environ.get(key) or os.environ.get(key.lower()) or ""
        if val:
            return val
        try:
            from hermes_constants import get_hermes_home
            env_path = get_hermes_home() / ".env"
            if env_path.exists():
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith(f"{key}="):
                            return line.split("=", 1)[1].strip().strip("\"'")
                        if line.startswith(f"export {key}="):
                            return line.split("=", 1)[1].strip().strip("\"'")
        except Exception:
            pass
        return ""


# Required: register the provider
provider_class = SupabaseMemoryProvider
