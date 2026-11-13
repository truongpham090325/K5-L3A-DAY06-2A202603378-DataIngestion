"""PostgreSQL + pgvector store: persistent vector search with metadata filter.

Uses exact (full-scan) cosine-distance search, which is appropriate for a
small corpus (a few hundred chunks); no ANN index is created, so there is no
approximation noise to account for. Vector literals are passed as ``[...]``
strings cast to ``vector`` in SQL, so no extra Python client is required.
"""
from __future__ import annotations

from typing import Any

import psycopg

from .models import Chunk

# Metadata columns that may be used as SQL filters (never allow arbitrary keys).
_FILTER_COLUMNS = {"document_id", "source", "page", "section"}


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.database_url = database_url
        self.dimensions = dimensions

    def _connect(self):
        return psycopg.connect(self.database_url, connect_timeout=10)

    @staticmethod
    def _vector_literal(vector: list[float]) -> str:
        return "[" + ",".join(repr(float(x)) for x in vector) + "]"

    def create_schema(self) -> None:
        """Create the chunks table with a vector column and metadata fields."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                # (chunk_id, strategy) is the primary key: the same deterministic
                # chunk_id is reused across strategies (A/B/C), so it must be
                # unique per strategy rather than globally.
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS chunks (
                        chunk_id    TEXT NOT NULL,
                        strategy    TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        source      TEXT NOT NULL,
                        page        INTEGER NOT NULL,
                        section     TEXT,
                        text        TEXT NOT NULL,
                        embedding   vector({self.dimensions}) NOT NULL,
                        PRIMARY KEY (chunk_id, strategy)
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS chunks_strategy_idx ON chunks (strategy)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS chunks_section_idx ON chunks (section)"
                )
            conn.commit()

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Validate, then replace this strategy's chunks for the given documents.

        The write is atomic: obsolete chunks are deleted and the fresh set is
        inserted in one transaction. Chunk IDs are deterministic, so re-running
        the same strategy never duplicates rows, and changed documents (with new
        chunk boundaries) have their old chunks removed.
        """
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")
        for vec in vectors:
            if len(vec) != self.dimensions:
                raise ValueError(
                    f"vector dimension {len(vec)} != store dimension {self.dimensions}"
                )
        if not chunks:
            return

        rows = [
            (
                chunk.chunk_id,
                strategy,
                chunk.document_id,
                chunk.source,
                chunk.page,
                chunk.metadata.get("section"),
                chunk.text,
                self._vector_literal(vec),
            )
            for chunk, vec in zip(chunks, vectors)
        ]
        document_ids = sorted({c.document_id for c in chunks})

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM chunks WHERE strategy = %s AND document_id = ANY(%s::text[])",
                    (strategy, document_ids),
                )
                for row in rows:
                    cur.execute(
                        "INSERT INTO chunks "
                        "(chunk_id, strategy, document_id, source, page, section, text, embedding) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)",
                        row,
                    )
            conn.commit()

    def search(
        self,
        strategy: str,
        query_vector: list[float],
        top_k: int = 3,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Rank chunks by cosine similarity, optionally filtering metadata.

        All user-supplied values are parameterized; only known metadata columns
        are allowed. Score is ``1 - cosine_distance`` (1.0 == identical).
        """
        if len(query_vector) != self.dimensions:
            raise ValueError(
                f"query vector dimension {len(query_vector)} != store dimension {self.dimensions}"
            )
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        filters = filters or {}
        unknown = set(filters) - _FILTER_COLUMNS
        if unknown:
            raise ValueError(f"unsupported filter field(s): {sorted(unknown)}")

        where_parts = ["strategy = %s"]
        params: list[Any] = [self._vector_literal(query_vector)]  # score column
        params.append(strategy)
        for key, value in filters.items():
            where_parts.append(f"{key} = %s")
            params.append(value)
        params.append(self._vector_literal(query_vector))  # ORDER BY
        params.append(int(top_k))

        sql = f"""
            SELECT chunk_id, document_id, source, page, section, text,
                   1 - (embedding <=> %s::vector) AS score
            FROM chunks
            WHERE {" AND ".join(where_parts)}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        return [
            {
                "chunk_id": r[0],
                "document_id": r[1],
                "source": r[2],
                "page": r[3],
                "section": r[4],
                "text": r[5],
                "score": float(r[6]),
            }
            for r in rows
        ]
