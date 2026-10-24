"""Phase 2: Caching layer for OCR, LLM, and Evidence Indexing.

Manages three SQLite caches:
1. ocr_cache.sqlite - file hash + engine -> extracted text & json
2. llm_cache.sqlite - prompt hash + params -> response + token counts
3. evidence_index.sqlite - normalized queryable records, activities, audit, valid_evidence_ids
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Optional


class CacheManager:
    def __init__(self, repo_root: str | Path | None = None):
        if repo_root is None:
            self.repo_root = Path(__file__).resolve().parent.parent
        else:
            self.repo_root = Path(repo_root)

        self.cache_dir = self.repo_root / "cache"
        self.cache_dir.mkdir(exist_ok=True)

        self.ocr_db_path = self.cache_dir / "ocr_cache.sqlite"
        self.llm_db_path = self.cache_dir / "llm_cache.sqlite"
        self.evidence_db_path = self.cache_dir / "evidence_index.sqlite"

        self._init_ocr_db()
        self._init_llm_db()
        self._init_evidence_db()

    def _init_ocr_db(self) -> None:
        with sqlite3.connect(self.ocr_db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ocr_cache (
                    key TEXT PRIMARY KEY,
                    file_path TEXT,
                    engine TEXT,
                    extracted_text TEXT,
                    structured_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def _init_llm_db(self) -> None:
        with sqlite3.connect(self.llm_db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS llm_cache (
                    key TEXT PRIMARY KEY,
                    prompt_hash TEXT,
                    model_name TEXT,
                    response_text TEXT,
                    structured_json TEXT,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT,
                    model_provider TEXT,
                    model_name TEXT,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    cache_hit INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def _init_evidence_db(self) -> None:
        with sqlite3.connect(self.evidence_db_path) as conn:
            # valid_evidence_ids covers all 94 files, 4011 activities, and 306 audit entries
            conn.execute("""
                CREATE TABLE IF NOT EXISTS valid_evidence_ids (
                    evidence_id TEXT PRIMARY KEY,
                    source_type TEXT
                )
            """)
            # Queryable normalized evidence records
            conn.execute("""
                CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    system_id TEXT,
                    resource_id TEXT,
                    data_category TEXT,
                    user_id TEXT,
                    identifiers_json TEXT,
                    state TEXT,
                    observed_at TEXT,
                    evidence_id TEXT,
                    details_json TEXT
                )
            """)
            # System activities
            conn.execute("""
                CREATE TABLE IF NOT EXISTS activities (
                    activity_id TEXT PRIMARY KEY,
                    event_time TEXT,
                    event_type TEXT,
                    source_system TEXT,
                    target_system TEXT,
                    resource_id TEXT,
                    reported_result TEXT,
                    details TEXT
                )
            """)
            # User audit log
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit (
                    audit_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    event_time TEXT,
                    field_name TEXT,
                    old_value TEXT,
                    new_value TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_records_user ON records(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_records_resource ON records(resource_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_records_system ON records(system_id)")

    def get_ocr(self, file_hash: str, engine: str) -> Optional[dict[str, Any]]:
        key = hashlib.sha256(f"{file_hash}:{engine}".encode()).hexdigest()
        with sqlite3.connect(self.ocr_db_path) as conn:
            row = conn.execute("SELECT extracted_text, structured_json FROM ocr_cache WHERE key = ?", (key,)).fetchone()
            if row:
                return {
                    "extracted_text": row[0],
                    "structured": json.loads(row[1]) if row[1] else None,
                }
        return None

    def put_ocr(self, file_hash: str, engine: str, file_path: str, text: str, structured: Any = None) -> None:
        key = hashlib.sha256(f"{file_hash}:{engine}".encode()).hexdigest()
        with sqlite3.connect(self.ocr_db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ocr_cache (key, file_path, engine, extracted_text, structured_json) VALUES (?, ?, ?, ?, ?)",
                (key, file_path, engine, text, json.dumps(structured) if structured else None),
            )

    def get_llm(self, prompt: str, model: str, temperature: float = 0.0) -> Optional[dict[str, Any]]:
        key = hashlib.sha256(f"{prompt}:{model}:{temperature}".encode()).hexdigest()
        with sqlite3.connect(self.llm_db_path) as conn:
            row = conn.execute(
                "SELECT response_text, structured_json, input_tokens, output_tokens FROM llm_cache WHERE key = ?",
                (key,),
            ).fetchone()
            if row:
                return {
                    "response_text": row[0],
                    "structured": json.loads(row[1]) if row[1] else None,
                    "input_tokens": row[2],
                    "output_tokens": row[3],
                }
        return None

    def put_llm(
        self,
        prompt: str,
        model: str,
        response_text: str,
        structured: Any = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        temperature: float = 0.0,
    ) -> None:
        key = hashlib.sha256(f"{prompt}:{model}:{temperature}".encode()).hexdigest()
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
        with sqlite3.connect(self.llm_db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO llm_cache 
                (key, prompt_hash, model_name, response_text, structured_json, input_tokens, output_tokens) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    prompt_hash,
                    model,
                    response_text,
                    json.dumps(structured) if structured else None,
                    input_tokens,
                    output_tokens,
                ),
            )
