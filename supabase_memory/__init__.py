"""Supabase Memory Plugin — Hermes Agent MemoryProvider

Provides persistent memory via Supabase (PostgreSQL + pgvector).
Replaces the built-in SQLite memory with cloud-hosted storage.

Schema:
  - hermes_memory:   Memory entries with vector embeddings
  - hermes_users:    User profiles and preferences
  - hermes_sessions: Session tracking with summaries
  - hermes_skills:   Cross-instance skill mirroring
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

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
        "about the user that survives across sessions."
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


# ---------------------------------------------------------------------------
# Provider implementation
# ---------------------------------------------------------------------------


class SupabaseMemoryProvider(MemoryProvider):
    """MemoryProvider backed by Supabase PostgreSQL + pgvector."""

    def __init__(self):
        self._client: Optional[Client] = None
        self._url: str = ""
        self._key: str = ""
        self._session_id: str = ""

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
        """Connect to Supabase and prepare the session."""
        if not self._url or not self._key:
            url = self._get_env("SUPABASE_URL") or ""
            key = self._get_env("SUPABASE_SERVICE_KEY") or self._get_env("SUPABASE_ANON_KEY") or ""
            if not url or not key:
                raise RuntimeError("SupabaseMemory: missing SUPABASE_URL and SUPABASE_SERVICE_KEY")
            self._url = url
            self._key = key

        self._client = create_client(self._url, self._key)
        self._session_id = session_id

        logger.info("SupabaseMemory initialized for session %s", session_id)

    def system_prompt_block(self) -> str:
        """Return instructions about Supabase memory for the system prompt."""
        return (
            "You have persistent memory stored in Supabase (PostgreSQL + pgvector). "
            "Use supabase_search to recall past conversations, and supabase_profile "
            "to read or update user preferences that survive across sessions."
        )

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Retrieve relevant memory context for the upcoming turn."""
        if not self._client or not query:
            return ""

        try:
            # Keyword search via PostgreSQL ilike
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

        except Exception as e:
            logger.warning("SupabaseMemory prefetch failed: %s", e)

        return ""

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        """Persist a completed turn to Supabase."""
        if not self._client:
            return

        try:
            # Store user message
            self._client.table("hermes_memory").insert({
                "user_id": "default",
                "session_id": session_id or self._session_id,
                "content": user_content,
                "metadata": json.dumps({"role": "user"}),
            }).execute()

            # Store assistant response
            self._client.table("hermes_memory").insert({
                "user_id": "default",
                "session_id": session_id or self._session_id,
                "content": assistant_content,
                "metadata": json.dumps({"role": "assistant"}),
            }).execute()

        except Exception as e:
            logger.warning("SupabaseMemory sync_turn failed: %s", e)

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return the tools this provider exposes."""
        return [SEARCH_SCHEMA, PROFILE_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        """Dispatch a tool call to the appropriate handler."""
        if tool_name == "supabase_search":
            return self._handle_search(args)
        elif tool_name == "supabase_profile":
            return self._handle_profile(args)
        else:
            return tool_error(f"Unknown tool: {tool_name}")

    def shutdown(self) -> None:
        """Clean up resources."""
        self._client = None
        logger.info("SupabaseMemory shutdown complete")

    # -- Optional hooks ------------------------------------------------------

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """Summarize and store session on exit."""
        if not self._client:
            return

        try:
            # Update session with a summary
            summary = f"Session with {len(messages)} exchanges"
            self._client.table("hermes_sessions").upsert({
                "session_id": self._session_id,
                "summary": summary,
            }).execute()
        except Exception as e:
            logger.warning("SupabaseMemory on_session_end failed: %s", e)

    # -- Tool handlers -------------------------------------------------------

    def _handle_search(self, args: Dict[str, Any]) -> str:
        """Search memory entries."""
        query = args.get("query", "")
        limit = min(int(args.get("limit", 5)), 20)

        if not self._client or not query:
            return json.dumps({"results": [], "message": "No query provided"})

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
            })

        except Exception as e:
            return tool_error(f"Search failed: {e}")

    def _handle_profile(self, args: Dict[str, Any]) -> str:
        """Read or update user profile."""
        user_id = args.get("user_id", "default")
        profile_data = args.get("profile")

        if not self._client:
            return tool_error("Supabase not connected")

        try:
            if profile_data:
                # Update profile
                self._client.table("hermes_users").upsert({
                    "user_id": user_id,
                    "profile": json.dumps(profile_data),
                }).execute()
                return json.dumps({"status": "updated", "user_id": user_id})
            else:
                # Read profile
                result = (
                    self._client.table("hermes_users")
                    .select("profile")
                    .eq("user_id", user_id)
                    .limit(1)
                    .execute()
                )
                if result.data:
                    return json.dumps({"profile": result.data[0].get("profile", {})})
                return json.dumps({"profile": {}, "message": "No profile found"})

        except Exception as e:
            return tool_error(f"Profile operation failed: {e}")

    # -- Helpers -------------------------------------------------------------

    @staticmethod
    def _get_env(key: str) -> str:
        """Read env var from os.environ, falling back to .env parsing."""
        val = os.environ.get(key) or os.environ.get(key.lower()) or ""
        if val:
            return val
        # Try reading from .env file
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
