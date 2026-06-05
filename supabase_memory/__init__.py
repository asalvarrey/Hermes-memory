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
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure vendored dependencies bundled with the plugin are importable even when
# the Hermes runtime does not install supabase into the active environment.
_VENDOR_DIR = Path(__file__).resolve().parents[1] / "vendor"
if _VENDOR_DIR.exists() and str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from agent.memory_provider import MemoryProvider
from tools.registry import tool_error

from .embeddings import (
    EmbedBackendError,
    EmbedConfigError,
    EmbedDimensionError,
    EmbedProvider,
    EmbedProviderError,
    EmbedProviderFactory,
    EmbedUnavailableError,
    NullEmbedder,
)
from .settings import EnhancedMemorySettings, PluginSettings, load_plugin_settings

logger = logging.getLogger(__name__)

try:
    from supabase import create_client  # type: ignore[reportMissingImports]
    HAS_SUPABASE = True
except ImportError:
    create_client = None  # type: ignore[assignment]
    HAS_SUPABASE = False


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
                    CREATE TABLE IF NOT EXISTS dead_letter (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        operation   TEXT NOT NULL,
                        payload     TEXT NOT NULL,
                        created_at  REAL NOT NULL,
                        failed_at   REAL NOT NULL,
                        retries     INTEGER NOT NULL,
                        last_error  TEXT
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

    def move_to_dead_letter(self, sync: Dict[str, Any], last_error: str = "") -> None:
        """Atomically move an exhausted pending_sync entry to dead_letter."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            try:
                conn.execute(
                    "INSERT INTO dead_letter "
                    "(operation, payload, created_at, failed_at, retries, last_error) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        sync["operation"],
                        json.dumps(sync["payload"]),
                        sync["created_at"],
                        time.time(),
                        sync["retries"],
                        last_error,
                    ),
                )
                conn.execute("DELETE FROM pending_sync WHERE id = ?", (sync["id"],))
                conn.commit()
            finally:
                conn.close()

    def get_dead_letter_count(self) -> int:
        """Return the number of entries in the dead_letter table."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            try:
                cur = conn.execute("SELECT COUNT(*) FROM dead_letter")
                row = cur.fetchone()
                return int(row[0]) if row else 0
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
        self._client: Optional[Any] = None
        self._url: str = ""
        self._key: str = ""
        self._session_id: str = ""
        self._cache: Optional[LocalCache] = None
        self._online: bool = False
        self._hermes_home: str = ""
        self._user_id: str = "default"

        # Plugin-local settings and embedding configuration.
        self._settings: Optional[PluginSettings] = None
        self._embedder: EmbedProvider = NullEmbedder()
        self._vector_enabled: bool = False
        self._vector_top_k: int = 10
        self._vector_min_similarity: float = 0.75
        self._keyword_top_k: int = 20
        self._fallback_to_ilike: bool = True
        self._enhanced_memory: Optional[EnhancedMemorySettings] = None

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
        # Load plugin-local settings once per provider instance.
        self._settings = load_plugin_settings()
        self._enhanced_memory = self._settings.enhanced_memory

        # Cache retrieval knobs locally for fast access on the hot path.
        self._vector_enabled = bool(self._settings.retrieval.vector_enabled)
        self._vector_top_k = int(self._settings.retrieval.vector_top_k)
        self._vector_min_similarity = float(self._settings.retrieval.vector_min_similarity)
        self._keyword_top_k = int(self._settings.retrieval.keyword_top_k)
        self._fallback_to_ilike = bool(self._settings.retrieval.fallback_to_ilike)

        # Build the embedder from plugin.yaml. If config is missing/invalid, fall
        # back to the safe NullEmbedder so keyword search remains the default path.
        try:
            self._embedder = EmbedProviderFactory.create(self._settings.raw)
        except EmbedConfigError as exc:
            logger.warning(
                "SupabaseMemory: invalid embedding config; using NullEmbedder: %s",
                exc,
            )
            self._embedder = NullEmbedder()

        # If the provider is not usable, keep vector search disabled and rely on ilike.
        if isinstance(self._embedder, NullEmbedder):
            self._vector_enabled = False

        if not self._url or not self._key:
            url = self._get_env("SUPABASE_URL") or ""
            key = self._get_env("SUPABASE_SERVICE_KEY") or self._get_env("SUPABASE_ANON_KEY") or ""
            if not url or not key:
                raise RuntimeError("SupabaseMemory: missing SUPABASE_URL and SUPABASE_SERVICE_KEY")
            self._url = url
            self._key = key

        self._hermes_home = kwargs.get("hermes_home", "")
        self._user_id = (
            kwargs.get("user_id")
            or kwargs.get("user_name")
            or self._get_env("HERMES_USER_ID")
            or "default"
        )
        self._cache = LocalCache(self._hermes_home)
        self._session_id = session_id

        # Try connecting to Supabase
        try:
            if create_client is None:
                raise RuntimeError("SupabaseMemory: supabase package is not installed")
            client = create_client(self._url, self._key)
            # Quick ping
            client.table("hermes_memory").select("id").limit(1).execute()
            self._client = client
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

        logger.info(
            "SupabaseMemory: embeddings=%s vector_enabled=%s fallback_to_ilike=%s",
            getattr(self._embedder, "name", "unknown"),
            self._vector_enabled,
            self._fallback_to_ilike,
        )

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
        """Retrieve relevant memory for the upcoming turn.

        Resolution order:
        1) Vector search via match_hermes_memory when embeddings are available
        2) Keyword search via Supabase ilike
        3) Local SQLite cache fallback
        """
        if not self._cache or not query:
            return ""

        sid = session_id or self._session_id

        def _format_supabase_rows(rows: List[Dict[str, Any]], *, prefix: str = "") -> str:
            lines: List[str] = []
            for entry in rows:
                ts = str(entry.get("created_at", ""))[:19]
                content = str(entry.get("content", ""))[:300]
                similarity = entry.get("similarity")
                if isinstance(similarity, (int, float)):
                    lines.append(f"{prefix}[{ts} | score={similarity:.3f}] {content}")
                else:
                    lines.append(f"{prefix}[{ts}] {content}")
            return "\n".join(lines)

        # ------------------------------------------------------------------
        # 1) Semantic retrieval via RPC if enabled and embedders are usable
        # ------------------------------------------------------------------
        if (
            self._online
            and self._client
            and self._vector_enabled
            and not isinstance(self._embedder, NullEmbedder)
        ):
            try:
                query_vectors = self._embedder.embed([query], kind="query")
                if query_vectors:
                    query_vector = query_vectors[0]
                    rpc_args: Dict[str, Any] = {
                        "query_embedding": query_vector,
                        "match_threshold": self._vector_min_similarity,
                        "match_count": self._vector_top_k,
                        "filter_user_id": self._user_id,
                        "filter_session_id": sid or None,
                    }

                    result = self._client.rpc("match_hermes_memory", rpc_args).execute()
                    if result.data:
                        return _format_supabase_rows(result.data)
            except EmbedProviderError as exc:
                logger.info("SupabaseMemory: vector prefetch unavailable, falling back to keyword search: %s", exc)
            except Exception as exc:
                logger.warning("SupabaseMemory: vector prefetch failed, falling back to keyword search: %s", exc)

        # ------------------------------------------------------------------
        # 2) Keyword fallback in Supabase
        # ------------------------------------------------------------------
        if self._online and self._client:
            try:
                result = (
                    self._client.table("hermes_memory")
                    .select("content, metadata, created_at")
                    .ilike("content", f"%{query}%")
                    .order("created_at", desc=True)
                    .limit(self._keyword_top_k)
                    .execute()
                )
                if result.data:
                    return _format_supabase_rows(result.data, prefix="")
            except Exception:
                self._online = False
                logger.info("SupabaseMemory: degraded to offline during prefetch")

        # ------------------------------------------------------------------
        # 3) Local SQLite fallback
        # ------------------------------------------------------------------
        try:
            results = self._cache.search_local(query, limit=self._keyword_top_k)
            if results:
                lines: List[str] = []
                for entry in results:
                    ts = entry.get("timestamp", "")
                    if isinstance(ts, (int, float)):
                        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
                    content = str(entry.get("content", ""))[:300]
                    lines.append(f"[local:{ts}] {content}")
                return "\n".join(lines)
        except Exception as e:
            logger.debug("SupabaseMemory local prefetch failed: %s", e)

        return ""

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Persist a turn.

        Always writes locally. If Supabase is online, also writes to Supabase with
        embeddings when available. If embedding generation or Supabase insert fails,
        the turn is queued for later sync and the provider degrades safely.
        """
        sid = session_id or self._session_id

        def _embedding_or_none(text: str) -> Optional[List[float]]:
            if not self._vector_enabled or isinstance(self._embedder, NullEmbedder):
                return None
            try:
                vectors = self._embedder.embed([text], kind="document")
                if not vectors:
                    return None
                return vectors[0]
            except EmbedProviderError as exc:
                logger.warning("SupabaseMemory: embedding failed, falling back to non-vector insert: %s", exc)
                return None
            except Exception as exc:
                logger.warning("SupabaseMemory: embedding backend error, falling back to non-vector insert: %s", exc)
                return None

        def _supabase_payload(role: str, content: str) -> Dict[str, Any]:
            payload: Dict[str, Any] = {
                "user_id": self._user_id,
                "session_id": sid,
                "content": content,
                "metadata": json.dumps({"role": role}),
            }
            embedding = _embedding_or_none(content)
            if embedding is not None:
                payload["embedding"] = embedding
            return payload

        # Always write to local cache first
        if self._cache:
            self._cache.store_turn(self._user_id, sid, user_content, assistant_content)

        # Also write to Supabase if online
        if self._online and self._client:
            try:
                self._client.table("hermes_memory").insert(_supabase_payload("user", user_content)).execute()
                self._client.table("hermes_memory").insert(_supabase_payload("assistant", assistant_content)).execute()
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
        """Store session summary on exit.

        When enhanced_memory is enabled, attempts a structured LLM summary first
        and stores it in hermes_sessions.metadata. Falls back to basic summary on
        any failure so shutdown is never blocked.
        """
        if not self._cache:
            return

        # -- Intentar resumen estructurado si está habilitado -----------------
        structured: Optional[Dict[str, Any]] = None
        if self._enhanced_memory and self._enhanced_memory.enabled:
            structured = self._generate_structured_summary(messages)

        # -- Resumen básico (siempre se genera como fallback) -----------------
        basic_summary = f"Session {self._session_id}: {len(messages)} messages"
        self._cache.set_metadata(f"session_{self._session_id}_summary", basic_summary)

        if self._online and self._client:
            try:
                upsert_payload: Dict[str, Any] = {
                    "session_id": self._session_id,
                    "user_id": self._user_id,
                    "summary": basic_summary,
                }
                if structured:
                    upsert_payload["metadata"] = structured
                self._client.table("hermes_sessions").upsert(upsert_payload, on_conflict="session_id").execute()
            except Exception:
                if self._cache:
                    queue_payload: Dict[str, Any] = {
                        "session_id": self._session_id,
                        "summary": basic_summary,
                    }
                    if structured:
                        queue_payload["metadata"] = structured
                    self._cache.queue_sync("upsert_session", queue_payload)

    def _generate_structured_summary(
        self,
        messages: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Call the OpenAI chat completions API via urllib to produce a structured
        JSON summary of the session.

        Uses the same api_key_env as the embedder — no new dependencies beyond
        what is already required for embeddings.
        Returns None on any failure; caller falls back to basic summary.
        """
        if not self._enhanced_memory or not self._settings:
            return None

        # -- Resolver API key (mismo env que el embedder) ---------------------
        api_key_env = self._settings.embedding.api_key_env or "OPENAI_API_KEY"
        api_key = self._get_env(api_key_env) or self._get_env("OPENAI_API_KEY")
        if not api_key:
            logger.debug(
                "SupabaseMemory: enhanced_memory skipped — no API key (%s)", api_key_env
            )
            return None

        # -- Construir transcript (últimos N mensajes) -------------------------
        max_msgs = self._enhanced_memory.max_messages_to_summarize
        window = messages[-max_msgs:] if len(messages) > max_msgs else messages

        transcript_lines: List[str] = []
        for msg in window:
            role = str(msg.get("role", "unknown")).upper()
            content = str(msg.get("content", ""))[:800]
            transcript_lines.append(f"{role}: {content}")
        transcript = "\n".join(transcript_lines)

        if not transcript.strip():
            return None

        # -- Construir prompt con los campos configurados ----------------------
        field_hints: Dict[str, str] = {
            "topics":      "list of strings — main topics discussed",
            "decisions":   "list of strings — decisions or agreements reached",
            "user_prefs":  "object — user preferences or facts learned (key-value pairs)",
            "key_context": "list of strings — important context for future sessions",
        }
        fields = self._enhanced_memory.summary_fields
        schema_lines = [
            f'  "{f}": <{field_hints.get(f, "list of strings")}>'
            for f in fields
        ]
        prompt = (
            "Analyze this conversation and return ONLY a valid JSON object "
            "with exactly these fields:\n"
            "{\n" + "\n".join(schema_lines) + "\n}\n\n"
            "Rules: no markdown, no explanation, no extra fields. Only the JSON.\n\n"
            f"CONVERSATION:\n{transcript}"
        )

        # -- Llamada HTTP vía urllib (mismo patrón que OpenAIEmbedder) --------
        endpoint = "https://api.openai.com/v1/chat/completions"
        payload: Dict[str, Any] = {
            "model": self._enhanced_memory.summary_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 512,
            "response_format": {"type": "json_object"},
        }
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
            result: Dict[str, Any] = json.loads(raw)
        except HTTPError as exc:
            details = ""
            try:
                details = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            logger.warning(
                "SupabaseMemory: enhanced_memory HTTP %d — %s", exc.code, details[:200]
            )
            return None
        except URLError as exc:
            logger.warning("SupabaseMemory: enhanced_memory network error — %s", exc)
            return None
        except json.JSONDecodeError as exc:
            logger.warning(
                "SupabaseMemory: enhanced_memory invalid JSON response — %s", exc
            )
            return None
        except Exception as exc:
            logger.warning("SupabaseMemory: enhanced_memory failed — %s", exc)
            return None

        # -- Parsear y validar la respuesta -----------------------------------
        try:
            content = result["choices"][0]["message"]["content"]
            structured = json.loads(content)
            if not isinstance(structured, dict):
                logger.warning("SupabaseMemory: enhanced_memory response is not a dict")
                return None
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            logger.warning("SupabaseMemory: enhanced_memory parse failed — %s", exc)
            return None

        # -- Loguear uso de tokens si disponible ------------------------------
        usage = result.get("usage", {})
        if usage:
            logger.info(
                "SupabaseMemory: enhanced_memory — %d prompt + %d completion tokens (session %s)",
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
                self._session_id,
            )

        return structured

    # -- Tool handlers -------------------------------------------------------

    def _handle_search(self, args: Dict[str, Any]) -> str:
        """Search memory with vector-first retrieval and keyword fallback."""
        query = str(args.get("query", "")).strip()
        limit = min(int(args.get("limit", 5)), 20)

        if not query:
            return json.dumps({"results": [], "message": "No query provided", "source": "none"})

        def _format_rows(rows: List[Dict[str, Any]], source: str) -> str:
            results: List[Dict[str, Any]] = []
            for entry in rows:
                content = str(entry.get("content", ""))[:500]
                metadata = entry.get("metadata", {})
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except Exception:
                        pass
                result_item: Dict[str, Any] = {
                    "content": content,
                    "metadata": metadata if isinstance(metadata, dict) else {},
                    "timestamp": entry.get("created_at", entry.get("timestamp", "")),
                }
                if "similarity" in entry and isinstance(entry["similarity"], (int, float)):
                    result_item["similarity"] = float(entry["similarity"])
                results.append(result_item)

            payload: Dict[str, Any] = {
                "results": results,
                "count": len(results),
                "query": query,
                "source": source,
            }
            if source == "local_cache" and not self._online:
                payload["note"] = "Supabase was unreachable — showing cached data"
            return json.dumps(payload)

        # ------------------------------------------------------------------
        # 1) Vector search via RPC if enabled and embeddings are available
        # ------------------------------------------------------------------
        if (
            self._online
            and self._client
            and self._vector_enabled
            and not isinstance(self._embedder, NullEmbedder)
        ):
            try:
                query_vectors = self._embedder.embed([query], kind="query")
                if query_vectors:
                    query_vector = query_vectors[0]
                    rpc_args: Dict[str, Any] = {
                        "query_embedding": query_vector,
                        "match_threshold": self._vector_min_similarity,
                        "match_count": limit,
                        "filter_user_id": self._user_id,
                        "filter_session_id": None,
                    }
                    result = self._client.rpc("match_hermes_memory", rpc_args).execute()
                    if result.data:
                        return json.dumps({
                            "results": [
                                {
                                    "content": str(entry.get("content", ""))[:500],
                                    "metadata": entry.get("metadata", {}) if isinstance(entry.get("metadata", {}), dict) else {},
                                    "timestamp": entry.get("created_at", ""),
                                    "similarity": float(entry.get("similarity", 0.0)) if entry.get("similarity") is not None else 0.0,
                                }
                                for entry in result.data
                            ],
                            "count": len(result.data),
                            "query": query,
                            "source": "supabase_vector",
                        })
            except EmbedProviderError as exc:
                logger.info(
                    "SupabaseMemory: vector search unavailable, falling back to keyword search: %s",
                    exc,
                )
            except Exception as exc:
                logger.warning(
                    "SupabaseMemory: vector search failed, falling back to keyword search: %s",
                    exc,
                )

        # ------------------------------------------------------------------
        # 2) Keyword search in Supabase
        # ------------------------------------------------------------------
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
                rows = result.data or []
                return _format_rows(rows, "supabase")
            except Exception as e:
                self._online = False
                logger.info("SupabaseMemory: degraded during search: %s", e)

        # ------------------------------------------------------------------
        # 3) Local cache fallback
        # ------------------------------------------------------------------
        if self._cache:
            try:
                results = self._cache.search_local(query, limit)
                return json.dumps({
                    "results": results,
                    "count": len(results),
                    "query": query,
                    "source": "local_cache",
                    "note": "Cached version — may be stale" if not self._online else "",
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
                    self._client.table("hermes_users").upsert(
                        {
                            "user_id": user_id,
                            "profile": json.dumps(profile_data),
                        },
                        on_conflict="user_id",
                    ).execute()
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
        pending_syncs: List[Dict[str, Any]] = []
        if self._cache:
            pending_syncs = self._cache.get_pending_syncs()

        embedder_name = getattr(self._embedder, "name", "unknown")
        embedder_model = getattr(self._embedder, "model", None)
        embedder_dimension = getattr(self._embedder, "dimension", None)

        return json.dumps({
            "online": self._online,
            "source": "supabase_online" if self._online else "local_cache",
            "status": "🟢 All systems go" if self._online
                      else f"🟡 Offline — {len(pending_syncs)} pending syncs in queue",
            "pending_syncs": len(pending_syncs),
            "details": {
                "supabase_connected": self._online,
                "local_cache_available": self._cache is not None,
                "pending_sync_count": len(pending_syncs),
                "dead_letter_count": self._cache.get_dead_letter_count() if self._cache else 0,
                "hermes_home": self._hermes_home,
                "session_id": self._session_id,
                "vector_enabled": self._vector_enabled,
                "vector_top_k": self._vector_top_k,
                "vector_min_similarity": self._vector_min_similarity,
                "keyword_top_k": self._keyword_top_k,
                "fallback_to_ilike": self._fallback_to_ilike,
                "embedding": {
                    "enabled": self._vector_enabled and not isinstance(self._embedder, NullEmbedder),
                    "provider": embedder_name,
                    "model": embedder_model,
                    "dimension": embedder_dimension,
                },
            },
        })

    def _is_vector_search_ready(self) -> bool:
        """Return True when vector search can be attempted safely."""
        return bool(
            self._online
            and self._client
            and self._vector_enabled
            and not isinstance(self._embedder, NullEmbedder)
        )

    def _embed_texts_safe(
        self,
        texts: List[str],
        *,
        kind: str = "document",
    ) -> List[List[float]]:
        """Embed texts safely, returning [] on any soft failure.

        This helper never raises on provider failures; it only returns an empty list
        and logs the problem so callers can fall back to keyword search.
        """
        if not texts or not self._is_vector_search_ready():
            return []

        try:
            vectors = self._embedder.embed(texts, kind=kind)  # type: ignore[arg-type]
            return vectors
        except EmbedProviderError as exc:
            logger.info("SupabaseMemory: embedding unavailable, falling back to keyword search: %s", exc)
            return []
        except Exception as exc:
            logger.warning("SupabaseMemory: embedding failed, falling back to keyword search: %s", exc)
            return []

    def _vector_search(self, query: str, *, session_id: str = "", limit: int = 5) -> List[Dict[str, Any]]:
        """Run vector search through the SQL RPC and normalize rows."""
        if not query or not self._is_vector_search_ready():
            return []

        query_vectors = self._embed_texts_safe([query], kind="query")
        if not query_vectors:
            return []

        rpc_args: Dict[str, Any] = {
            "query_embedding": query_vectors[0],
            "match_threshold": self._vector_min_similarity,
            "match_count": limit,
            "filter_user_id": self._user_id,
            "filter_session_id": session_id or None,
        }

        result = self._client.rpc("match_hermes_memory", rpc_args).execute()  # type: ignore[union-attr]
        rows = result.data or []
        normalized: List[Dict[str, Any]] = []

        for entry in rows:
            metadata = entry.get("metadata", {})
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = {}

            normalized.append({
                "id": entry.get("id"),
                "user_id": entry.get("user_id", "default"),
                "session_id": entry.get("session_id", session_id),
                "content": str(entry.get("content", ""))[:500],
                "metadata": metadata if isinstance(metadata, dict) else {},
                "timestamp": entry.get("created_at", ""),
                "similarity": float(entry.get("similarity", 0.0)) if entry.get("similarity") is not None else 0.0,
                "source": "supabase_vector",
            })

        return normalized

    def _keyword_search(self, query: str, *, limit: int = 5) -> List[Dict[str, Any]]:
        """Run keyword search against Supabase and normalize rows."""
        if not query or not self._online or not self._client:
            return []

        try:
            result = (
                self._client.table("hermes_memory")
                .select("id, user_id, session_id, content, metadata, created_at")
                .ilike("content", f"%{query}%")
                .limit(limit)
                .order("created_at", desc=True)
                .execute()
            )

            rows = result.data or []
            normalized: List[Dict[str, Any]] = []
            for entry in rows:
                metadata = entry.get("metadata", {})
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except Exception:
                        metadata = {}

                normalized.append({
                    "id": entry.get("id"),
                    "user_id": entry.get("user_id", "default"),
                    "session_id": entry.get("session_id", ""),
                    "content": str(entry.get("content", ""))[:500],
                    "metadata": metadata if isinstance(metadata, dict) else {},
                    "timestamp": entry.get("created_at", ""),
                    "source": "supabase_keyword",
                })

            return normalized
        except Exception as exc:
            self._online = False
            logger.info("SupabaseMemory: keyword search failed, switching to local cache: %s", exc)
            return []

    def _merge_search_results(
        self,
        vector_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
        *,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Merge vector + keyword results, de-duplicating and preserving ranking."""
        merged: List[Dict[str, Any]] = []
        seen: set[str] = set()

        def _key(entry: Dict[str, Any]) -> str:
            entry_id = entry.get("id")
            if entry_id:
                return f"id:{entry_id}"
            return f"content:{entry.get('content', '')}"

        for entry in vector_results + keyword_results:
            key = _key(entry)
            if key in seen:
                continue
            seen.add(key)
            merged.append(entry)
            if len(merged) >= limit:
                break

        return merged

    # -- Sync queue -----------------------------------------------------------

    def _flush_pending_syncs(self) -> None:
        """Flush all pending sync operations to Supabase."""
        MAX_SYNC_RETRIES = 5
        if not self._cache or not self._client or not self._online:
            return

        syncs = self._cache.get_pending_syncs()
        if not syncs:
            return

        logger.info("SupabaseMemory: flushing %d pending syncs...", len(syncs))
        flushed = 0

        def _maybe_embed(text: str) -> Optional[List[float]]:
            if not self._vector_enabled or isinstance(self._embedder, NullEmbedder):
                return None
            try:
                vectors = self._embedder.embed([text], kind="document")
                if vectors:
                    return vectors[0]
            except EmbedProviderError as exc:
                logger.warning("SupabaseMemory: pending sync embedding unavailable: %s", exc)
            except Exception as exc:
                logger.warning("SupabaseMemory: pending sync embedding failed: %s", exc)
            return None

        for sync in syncs:
            if sync["retries"] >= MAX_SYNC_RETRIES:
                self._cache.move_to_dead_letter(sync, last_error="max retries exceeded")
                logger.warning(
                    "SupabaseMemory: sync %d dead-lettered after %d retries (op=%s)",
                    sync["id"], sync["retries"], sync["operation"],
                )
                continue

            try:
                op = sync["operation"]
                payload = sync["payload"]

                if op == "insert_turn":
                    user_content = payload.get("user_content", "")
                    assistant_content = payload.get("assistant_content", "")
                    session_id = payload.get("session_id", "")

                    user_row: Dict[str, Any] = {
                        "user_id": self._user_id,
                        "session_id": session_id,
                        "content": user_content,
                        "metadata": json.dumps({"role": "user"}),
                    }
                    user_embedding = _maybe_embed(user_content)
                    if user_embedding is not None:
                        user_row["embedding"] = user_embedding

                    assistant_row: Dict[str, Any] = {
                        "user_id": self._user_id,
                        "session_id": session_id,
                        "content": assistant_content,
                        "metadata": json.dumps({"role": "assistant"}),
                    }
                    assistant_embedding = _maybe_embed(assistant_content)
                    if assistant_embedding is not None:
                        assistant_row["embedding"] = assistant_embedding

                    self._client.table("hermes_memory").insert(user_row).execute()
                    self._client.table("hermes_memory").insert(assistant_row).execute()

                elif op == "upsert_profile":
                    user_id = payload.get("user_id", "default")
                    profile = payload.get("profile", {})

                    profile_row: Dict[str, Any] = {
                        "user_id": user_id,
                        "profile": json.dumps(profile),
                    }
                    profile_embedding = _maybe_embed(json.dumps(profile, sort_keys=True))
                    if profile_embedding is not None:
                        profile_row["embedding"] = profile_embedding

                    self._client.table("hermes_users").upsert(profile_row, on_conflict="user_id").execute()

                elif op == "upsert_session":
                    self._client.table("hermes_sessions").upsert({
                        "session_id": payload.get("session_id", ""),
                        "summary": payload.get("summary", ""),
                    }, on_conflict="session_id").execute()

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
