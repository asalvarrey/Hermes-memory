"""Embedding providers for the Supabase memory plugin.

This module is intentionally self-contained and does not depend on Hermes core
for provider selection. The plugin asks for embeddings; the configured provider
decides how to obtain them.

Supported providers:
- OpenAIEmbedder
- OllamaEmbedder
- NullEmbedder (safe default)

Future support:
- VoyageAIEmbedder (documented, not implemented yet)
"""

from __future__ import annotations

import abc
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, ClassVar, Dict, List, Literal, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class EmbedProviderError(Exception):
    """Base class for embedding-related failures."""


class EmbedConfigError(EmbedProviderError):
    """Raised when configuration is missing or invalid."""


class EmbedUnavailableError(EmbedProviderError):
    """Raised when a provider is intentionally unavailable."""


class EmbedBackendError(EmbedProviderError):
    """Raised when the remote embedding backend fails."""


class EmbedDimensionError(EmbedProviderError):
    """Raised when returned embeddings do not match expected dimensions."""


# ---------------------------------------------------------------------------
# Base interface
# ---------------------------------------------------------------------------


class EmbedProvider(abc.ABC):
    """Abstract embedding provider.

    Concrete providers implement `embed()` and may expose `healthcheck()`.
    """

    @abc.abstractmethod
    def embed(
        self,
        texts: Sequence[str],
        *,
        kind: Literal["query", "document"] = "document",
    ) -> List[List[float]]:
        """Return one embedding vector per input text, preserving order."""

    def healthcheck(self) -> bool:
        """Return whether the provider is ready for use.

        Default implementation uses the provider's availability flag.
        """
        return bool(getattr(self, "is_available", False))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_nonempty_texts(texts: Sequence[str]) -> List[str]:
    if not texts:
        return []
    cleaned = []
    for text in texts:
        if text is None:
            cleaned.append("")
        else:
            cleaned.append(str(text))
    return cleaned


def _truncate_text(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return text
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _read_json_response(request: Request, timeout_s: int) -> Dict[str, Any]:
    try:
        with urlopen(request, timeout=timeout_s) as response:
            raw = response.read()
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))
    except HTTPError as exc:
        details = ""
        try:
            payload = exc.read().decode("utf-8", errors="replace")
            details = f": {payload}" if payload else ""
        except Exception:
            details = ""
        raise EmbedBackendError(
            f"HTTP {exc.code} from embedding backend{details}"
        ) from exc
    except URLError as exc:
        raise EmbedBackendError(f"Network error contacting embedding backend: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise EmbedBackendError("Embedding backend returned invalid JSON") from exc


def _validate_embedding_shape(
    vectors: Sequence[Sequence[float]],
    *,
    expected_dimension: Optional[int],
    provider_name: str,
) -> List[List[float]]:
    normalized: List[List[float]] = []
    for idx, vector in enumerate(vectors):
        vec = [float(v) for v in vector]
        if expected_dimension is not None and len(vec) != expected_dimension:
            raise EmbedDimensionError(
                f"{provider_name} returned vector #{idx} with dimension {len(vec)} "
                f"but expected {expected_dimension}"
            )
        normalized.append(vec)
    return normalized


def _normalize_base_url(base_url: Optional[str], default: str) -> str:
    if not base_url:
        return default
    return base_url.rstrip("/") + "/"


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


@dataclass
class NullEmbedder(EmbedProvider):
    """Safe default that disables embeddings and forces keyword fallback."""

    name: str = "null"
    model: Optional[str] = None
    dimension: Optional[int] = None
    supports_batch: bool = False
    is_available: bool = False

    def embed(
        self,
        texts: Sequence[str],
        *,
        kind: Literal["query", "document"] = "document",
    ) -> List[List[float]]:
        raise EmbedUnavailableError("NullEmbedder is disabled; falling back to ilike")


@dataclass
class OpenAIEmbedder(EmbedProvider):
    """OpenAI-compatible embedding provider.

    The API key name is configurable via `api_key_env`; the code only reads the
    environment variable whose name is provided by config.
    """

    model: str
    api_key_env: str
    base_url: Optional[str] = None
    dimension: int = 1536
    timeout_s: int = 30
    max_chars: int = 8000
    name: str = "openai"
    supports_batch: bool = True
    is_available: bool = True

    def _get_api_key(self) -> str:
        env_name = (self.api_key_env or "").strip()
        if not env_name:
            raise EmbedConfigError("OpenAIEmbedder requires api_key_env")
        api_key = os.environ.get(env_name, "").strip()
        if not api_key:
            raise EmbedConfigError(
                f"Missing OpenAI API key in environment variable {env_name}"
            )
        return api_key

    def _endpoint(self) -> str:
        # Default OpenAI-compatible embeddings endpoint
        return urljoin(_normalize_base_url(self.base_url, "https://api.openai.com/v1/"), "embeddings")

    def embed(
        self,
        texts: Sequence[str],
        *,
        kind: Literal["query", "document"] = "document",
    ) -> List[List[float]]:
        texts = _ensure_nonempty_texts(texts)
        if not texts:
            return []

        api_key = self._get_api_key()
        endpoint = self._endpoint()
        inputs = [_truncate_text(text, self.max_chars) for text in texts]

        payload = {
            "model": self.model,
            "input": inputs if len(inputs) > 1 else inputs[0],
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

        result = _read_json_response(request, timeout_s=self.timeout_s)
        data = result.get("data")
        if not isinstance(data, list):
            raise EmbedBackendError("OpenAI embeddings response missing 'data' list")

        # OpenAI returns a list of objects; each item should contain `embedding`
        vectors: List[List[float]] = []
        for item in data:
            if not isinstance(item, dict) or "embedding" not in item:
                raise EmbedBackendError("OpenAI embeddings response missing 'embedding' field")
            embedding = item["embedding"]
            if not isinstance(embedding, list):
                raise EmbedBackendError("OpenAI embeddings response 'embedding' is not a list")
            vectors.append([float(v) for v in embedding])

        if len(vectors) != len(texts):
            raise EmbedBackendError(
                f"OpenAI returned {len(vectors)} embeddings for {len(texts)} inputs"
            )

        return _validate_embedding_shape(
            vectors,
            expected_dimension=self.dimension,
            provider_name=self.name,
        )


@dataclass
class OllamaEmbedder(EmbedProvider):
    """Ollama embedding provider.

    Supports local or remote Ollama-compatible endpoints.
    """

    model: str
    base_url: Optional[str] = None
    dimension: int = 1536
    timeout_s: int = 30
    max_chars: int = 8000
    name: str = "ollama"
    supports_batch: bool = True
    is_available: bool = True

    def _endpoint_embed(self) -> str:
        # Newer Ollama servers support /api/embed for batch input.
        return urljoin(_normalize_base_url(self.base_url, "http://localhost:11434/"), "api/embed")

    def _endpoint_embeddings(self) -> str:
        return urljoin(_normalize_base_url(self.base_url, "http://localhost:11434/"), "api/embeddings")

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return _read_json_response(request, timeout_s=self.timeout_s)

    def embed(
        self,
        texts: Sequence[str],
        *,
        kind: Literal["query", "document"] = "document",
    ) -> List[List[float]]:
        texts = _ensure_nonempty_texts(texts)
        if not texts:
            return []

        inputs = [_truncate_text(text, self.max_chars) for text in texts]
        vectors: List[List[float]] = []

        # Try batch endpoint first.
        try:
            result = self._post(
                self._endpoint_embed(),
                {
                    "model": self.model,
                    "input": inputs,
                },
            )
            embeddings = result.get("embeddings")
            if isinstance(embeddings, list) and embeddings:
                for item in embeddings:
                    if not isinstance(item, list):
                        raise EmbedBackendError("Ollama /api/embed returned non-list embedding")
                    vectors.append([float(v) for v in item])

                if len(vectors) != len(texts):
                    raise EmbedBackendError(
                        f"Ollama returned {len(vectors)} embeddings for {len(texts)} inputs"
                    )

                return _validate_embedding_shape(
                    vectors,
                    expected_dimension=self.dimension,
                    provider_name=self.name,
                )
        except EmbedBackendError:
            # Fall through to single-input compatibility path below.
            pass
        except Exception as exc:
            logger.debug("Ollama /api/embed path failed; falling back to /api/embeddings: %s", exc)

        # Compatibility path: call /api/embeddings once per input.
        for text in inputs:
            result = self._post(
                self._endpoint_embeddings(),
                {
                    "model": self.model,
                    "prompt": text,
                },
            )
            embedding = result.get("embedding")
            if not isinstance(embedding, list):
                raise EmbedBackendError("Ollama /api/embeddings response missing 'embedding'")
            vectors.append([float(v) for v in embedding])

        return _validate_embedding_shape(
            vectors,
            expected_dimension=self.dimension,
            provider_name=self.name,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class EmbedProviderFactory:
    """Create embedding providers from plugin settings."""

    @staticmethod
    def create(settings: Dict[str, Any]) -> EmbedProvider:
        embedding = settings.get("embedding") or {}
        if not isinstance(embedding, dict):
            raise EmbedConfigError("Invalid embedding settings: expected mapping")

        enabled = bool(embedding.get("enabled", False))
        provider_name = str(embedding.get("provider") or "").strip().lower()
        model = str(embedding.get("model") or "").strip()
        dimension = embedding.get("dimension", 1536)
        base_url = embedding.get("base_url")
        timeout_s = int(embedding.get("timeout_s", 30))
        api_key_env = str(embedding.get("api_key_env") or "").strip()

        if not enabled or not provider_name:
            return NullEmbedder()

        if provider_name == "openai":
            if not model:
                raise EmbedConfigError("OpenAI embedder requires embedding.model")
            if not api_key_env:
                raise EmbedConfigError("OpenAI embedder requires embedding.api_key_env")
            return OpenAIEmbedder(
                model=model,
                api_key_env=api_key_env,
                base_url=base_url,
                dimension=int(dimension),
                timeout_s=timeout_s,
            )

        if provider_name == "ollama":
            if not model:
                raise EmbedConfigError("Ollama embedder requires embedding.model")
            return OllamaEmbedder(
                model=model,
                base_url=base_url,
                dimension=int(dimension),
                timeout_s=timeout_s,
            )

        if provider_name == "voyageai":
            raise EmbedConfigError(
                "VoyageAI embedder is not implemented yet. "
                "It is reserved as the next supported provider."
            )

        raise EmbedConfigError(f"Unsupported embedding provider: {provider_name}")


__all__ = [
    "EmbedProvider",
    "EmbedProviderError",
    "EmbedConfigError",
    "EmbedUnavailableError",
    "EmbedBackendError",
    "EmbedDimensionError",
    "OpenAIEmbedder",
    "OllamaEmbedder",
    "NullEmbedder",
    "EmbedProviderFactory",
]
