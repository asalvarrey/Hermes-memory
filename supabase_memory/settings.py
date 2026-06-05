"""Plugin settings loader for the Supabase memory plugin.

This module keeps plugin configuration local to the plugin package so the
memory provider remains self-contained and does not depend on Hermes core
runtime details for embedding configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml  # pyright: ignore[reportMissingModuleSource]
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


@dataclass
class EmbeddingSettings:
    enabled: bool = False
    provider: str = ""
    model: str = ""
    dimension: int = 1536
    api_key_env: str = ""
    base_url: Optional[str] = None
    timeout_s: int = 30
    batch_size: int = 16
    strict_dimension: bool = True


@dataclass
class RetrievalSettings:
    vector_enabled: bool = True
    vector_top_k: int = 10
    vector_min_similarity: float = 0.75
    keyword_top_k: int = 20
    fallback_to_ilike: bool = True


@dataclass
class PluginSettings:
    embedding: EmbeddingSettings
    retrieval: RetrievalSettings
    raw: Dict[str, Any]


def _plugin_root() -> Path:
    return Path(__file__).resolve().parent


def _plugin_manifest_path() -> Path:
    return _plugin_root() / "plugin.yaml"


def _load_yaml_file(path: Path) -> Dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to read plugin configuration")
    if not path.exists():
        raise FileNotFoundError(f"Missing plugin manifest: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid plugin manifest structure in {path}")
    return data


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _read_embedding_settings(raw: Dict[str, Any]) -> EmbeddingSettings:
    embedding = raw.get("embedding") or {}
    if not isinstance(embedding, dict):
        embedding = {}

    base_url = embedding.get("base_url")
    return EmbeddingSettings(
        enabled=_coerce_bool(embedding.get("enabled"), False),
        provider=str(embedding.get("provider") or "").strip().lower(),
        model=str(embedding.get("model") or "").strip(),
        dimension=_coerce_int(embedding.get("dimension"), 1536),
        api_key_env=str(embedding.get("api_key_env") or "").strip(),
        base_url=(str(base_url).strip() or None) if base_url is not None else None,
        timeout_s=_coerce_int(embedding.get("timeout_s"), 30),
        batch_size=_coerce_int(embedding.get("batch_size"), 16),
        strict_dimension=_coerce_bool(embedding.get("strict_dimension"), True),
    )


def _read_retrieval_settings(raw: Dict[str, Any]) -> RetrievalSettings:
    retrieval = raw.get("retrieval") or {}
    if not isinstance(retrieval, dict):
        retrieval = {}

    return RetrievalSettings(
        vector_enabled=_coerce_bool(retrieval.get("vector_enabled"), True),
        vector_top_k=_coerce_int(retrieval.get("vector_top_k"), 10),
        vector_min_similarity=_coerce_float(retrieval.get("vector_min_similarity"), 0.75),
        keyword_top_k=_coerce_int(retrieval.get("keyword_top_k"), 20),
        fallback_to_ilike=_coerce_bool(retrieval.get("fallback_to_ilike"), True),
    )


def load_plugin_settings() -> PluginSettings:
    """Load and normalize plugin settings from plugin.yaml.

    Env var names are not hardcoded here; the embedding provider will read the
    API key using the configured api_key_env value.
    """
    raw = _load_yaml_file(_plugin_manifest_path())
    return PluginSettings(
        embedding=_read_embedding_settings(raw),
        retrieval=_read_retrieval_settings(raw),
        raw=raw,
    )
