"""jarvis/memory.py — Long-term semantic vector memory & RAG store using SQLite."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import sqlite3
import time
import contextlib
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/memory.db")


class SemanticVectorizer:
    """
    Lightweight, high-performance in-memory semantic vectorizer.
    Combines word-level TF-IDF and character 3-gram embeddings to measure cosine similarity
    without requiring heavy 500MB+ dependencies.
    """
    @staticmethod
    def tokenize(text: str) -> list[str]:
        return [w.lower() for w in re.findall(r"\b\w+\b", text)]

    @classmethod
    def get_vector(cls, text: str) -> dict[str, float]:
        tokens = cls.tokenize(text)
        if not tokens:
            return {}

        # 1. Word unigrams
        tf = Counter(tokens)

        # 2. Character 3-grams for semantic fuzzy and morphological matching
        cleaned = re.sub(r"[^\w\s]", "", text.lower())
        char_ngrams = [cleaned[i : i + 3] for i in range(len(cleaned) - 2)]
        tf.update(char_ngrams)

        # Compute Euclidean norm
        norm = math.sqrt(sum(val * val for val in tf.values()))
        if norm == 0:
            return {}
        return {k: v / norm for k, v in tf.items()}

    @classmethod
    def cosine_similarity(cls, vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
        if not vec_a or not vec_b:
            return 0.0
        # Dot product of normalized vectors
        intersection = set(vec_a.keys()) & set(vec_b.keys())
        return sum(vec_a[k] * vec_b[k] for k in intersection)


class MemoryStore:
    """Thread-safe SQLite persistent long-term memory store."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextlib.contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL DEFAULT 'general',
                    content TEXT NOT NULL,
                    keywords TEXT DEFAULT '',
                    embedding TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    accessed_at REAL NOT NULL
                )
            """)
            conn.commit()

    def store_memory(self, content: str, category: str = "general") -> str:
        """Store a new fact, preference, or note into long-term memory."""
        cleaned = content.strip()
        if not cleaned:
            return "Cannot store empty memory."

        vector = SemanticVectorizer.get_vector(cleaned)
        vector_json = json.dumps(vector)
        keywords = " ".join(SemanticVectorizer.tokenize(cleaned))
        now = time.time()

        with self._get_connection() as conn:
            # Check for near-identical existing memory to update instead of duplicating
            cursor = conn.cursor()
            cursor.execute("SELECT id, content, embedding FROM memories")
            for row in cursor.fetchall():
                try:
                    existing_vec = json.loads(row["embedding"]) if row["embedding"] else {}
                    sim = SemanticVectorizer.cosine_similarity(vector, existing_vec)
                    if sim > 0.88:
                        conn.execute(
                            "UPDATE memories SET content = ?, embedding = ?, keywords = ?, accessed_at = ? WHERE id = ?",
                            (cleaned, vector_json, keywords, now, row["id"])
                        )
                        conn.commit()
                        logger.info("Updated existing memory (id=%d): '%s'", row["id"], cleaned)
                        return f"Updated existing memory: {cleaned}"
                except Exception:
                    pass

            cursor.execute(
                "INSERT INTO memories (category, content, keywords, embedding, created_at, accessed_at) VALUES (?, ?, ?, ?, ?, ?)",
                (category, cleaned, keywords, vector_json, now, now)
            )
            conn.commit()
            logger.info("Stored new memory: '%s'", cleaned)
            return f"Remembered: {cleaned}"

    def query_memories(self, query: str, top_k: int = 3, threshold: float = 0.20) -> list[str]:
        """Retrieve the most relevant long-term memory snippets matching a query."""
        if not query or not query.strip():
            return []

        query_vec = SemanticVectorizer.get_vector(query)
        if not query_vec:
            return []

        scored_memories: list[tuple[float, int, str]] = []

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, content, embedding, category FROM memories")
            rows = cursor.fetchall()

            for row in rows:
                try:
                    emb = json.loads(row["embedding"]) if row["embedding"] else {}
                    sim = SemanticVectorizer.cosine_similarity(query_vec, emb)
                    if sim >= threshold:
                        scored_memories.append((sim, row["id"], row["content"]))
                except Exception:
                    pass

            # Update access timestamp for matched memories
            if scored_memories:
                scored_memories.sort(key=lambda x: x[0], reverse=True)
                top_matches = scored_memories[:top_k]
                matched_ids = [m[1] for m in top_matches]
                placeholders = ",".join("?" for _ in matched_ids)
                conn.execute(
                    f"UPDATE memories SET accessed_at = ? WHERE id IN ({placeholders})",
                    [time.time()] + matched_ids
                )
                conn.commit()
                return [m[2] for m in top_matches]

        return []

    def list_memories(self) -> list[dict[str, Any]]:
        """Return all memories sorted by most recently accessed."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, category, content, created_at, accessed_at FROM memories ORDER BY accessed_at DESC")
            return [
                {
                    "id": row["id"],
                    "category": row["category"],
                    "content": row["content"],
                    "created_at": row["created_at"],
                    "accessed_at": row["accessed_at"],
                }
                for row in cursor.fetchall()
            ]

    def delete_memory(self, memory_id: int) -> bool:
        """Delete a memory by its unique database ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.commit()
            return cursor.rowcount > 0

    def forget_by_query(self, query: str) -> str:
        """Find and remove memories matching a query."""
        matches = self.query_memories(query, top_k=2, threshold=0.35)
        if not matches:
            return f"I couldn't find any memory matching '{query}'."

        with self._get_connection() as conn:
            for content in matches:
                conn.execute("DELETE FROM memories WHERE content = ?", (content,))
            conn.commit()
        return f"Forgot {len(matches)} memory item(s): {', '.join(matches)}."

    def clear_all(self) -> None:
        """Purge all stored memories."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM memories")
            conn.commit()


# Singleton memory instance
_default_memory_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    global _default_memory_store
    if _default_memory_store is None:
        _default_memory_store = MemoryStore()
    return _default_memory_store
