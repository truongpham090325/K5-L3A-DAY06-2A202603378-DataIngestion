"""OpenAI embedding adapter (a real provider; never silently mocks vectors)."""
from __future__ import annotations

import os
from typing import Protocol

# Known embedding dimensions for supported models; keeps the vector column
# and query/document vectors consistent across the three strategies.
_MODEL_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}


class Embedder(Protocol):
    """Contract implemented by any real embedding provider."""

    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """Embeds documents and queries with an OpenAI embedding model.

    The API key is read from ``OPENAI_API_KEY`` (or passed explicitly). A
    missing key or an unknown model raises an exception, so the pipeline fails
    loudly instead of silently falling back to mock vectors.
    """

    def __init__(
        self,
        model_name: str = "text-embedding-3-small",
        api_key: str | None = None,
        batch_size: int = 256,
    ) -> None:
        self.model_name = model_name
        self.dimensions = _MODEL_DIMENSIONS.get(model_name)
        if self.dimensions is None:
            raise ValueError(
                f"Unknown embedding model {model_name!r}; "
                f"supported: {sorted(_MODEL_DIMENSIONS)}"
            )
        self.batch_size = max(1, int(batch_size))

        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self._api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set; refusing to fall back to mock vectors"
            )

        from openai import OpenAI

        self._client = OpenAI(api_key=self._api_key)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            vectors.extend(self._embed(texts[i : i + self.batch_size]))
        return vectors

    def embed_query(self, question: str) -> list[float]:
        return self._embed([question])[0]

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(model=self.model_name, input=texts)
        # OpenAI returns results in order, but sort by index defensively.
        data = sorted(response.data, key=lambda d: d.index)
        vectors = [list(d.embedding) for d in data]
        for vec in vectors:
            if len(vec) != self.dimensions:
                raise RuntimeError(
                    f"Unexpected embedding dimension {len(vec)} != {self.dimensions}"
                )
        return vectors
