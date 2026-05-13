"""Semantic embedding utilities with optional transformer support."""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache
from typing import Iterable

from app.core.config import settings


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9+#.]+", text.lower())


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


def _dot(lhs: Iterable[float], rhs: Iterable[float]) -> float:
    return sum(a * b for a, b in zip(lhs, rhs))


def cosine_similarity(lhs: list[float], rhs: list[float]) -> float:
    if not lhs or not rhs:
        return 0.0
    return max(0.0, min(1.0, _dot(lhs, rhs)))


class EmbeddingService:
    """Load a sentence-transformer when available and fall back to hashing."""

    def __init__(self, model_name: str | None = None, dimension: int = 384):
        self.model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self.dimension = dimension
        self.backend = "hashing"
        self._model = None
        try:  # Optional dependency
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(self.model_name)
            self.backend = "sentence-transformer"
        except Exception:
            self._model = None

    def embed(self, text: str) -> list[float]:
        if self._model is not None:
            try:
                vector = self._model.encode([text], normalize_embeddings=True)
                first = vector[0]
                return [float(value) for value in getattr(first, "tolist", lambda: list(first))()]
            except Exception:
                self._model = None
                self.backend = "hashing"
        return self._hash_embedding(text)

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]

    def similarity(self, left: str | list[float], right: str | list[float]) -> float:
        left_vector = self._coerce(left)
        right_vector = self._coerce(right)
        return cosine_similarity(left_vector, right_vector)

    def _coerce(self, value: str | list[float]) -> list[float]:
        if isinstance(value, str):
            return self.embed(value)
        return value

    def _hash_embedding(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = _tokenize(text)
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimension
            weight = 1.0 + min(2.0, len(token) / 8.0)
            vector[index] += weight

        for left, right in zip(tokens, tokens[1:]):
            bigram = f"{left}_{right}"
            digest = hashlib.blake2b(bigram.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[4:8], "little") % self.dimension
            vector[index] += 0.75

        return _normalize(vector)


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()


def semantic_similarity(left: str | list[float], right: str | list[float]) -> float:
    service = get_embedding_service()
    return service.similarity(left, right)

