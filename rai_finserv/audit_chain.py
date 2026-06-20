"""
AuditChain — append-only log of every LLM input/output.

The foundational traceability control. Without a complete audit trail,
you cannot answer "what did the model actually decide, and why?" —
the question regulators and internal audit will always ask.

Key design:
- Append-only: no updates or deletes. Regulatory records must be immutable.
- Prompt hash: detects if the same document was processed with a different prompt
  (catches silent prompt changes that alter model behaviour without anyone noticing)
- Model version logged: captures which model version produced each output
  (essential for comparing behaviour before/after a model upgrade)

Regulatory question answered:
  "Show me every decision the AI made, the input it saw, and what a human did with it."
  — FCA DP5/22 §5.1, SR 11-7 Section 5, GDPR Article 22

Usage:
    audit = AuditChain(db_path="audit.db")
    entry_id = audit.log_ai_decision(
        pipeline_id="doc_classifier",
        input_text=document_text,
        prompt=system_prompt,
        output=classification,
        confidence=0.92,
        model_id="claude-haiku-4-5-20251001",
        metadata={"document_type": "earnings_release"},
    )
    audit.log_human_review(entry_id, reviewer_id="analyst_1", decision="agreed", notes="")
"""

import sqlite3
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass


@dataclass
class AuditEntry:
    entry_id: int
    pipeline_id: str
    timestamp_utc: str
    input_hash: str
    prompt_hash: str
    output: str
    confidence: float
    model_id: str
    gate_outcome: str
    metadata: dict
    human_review_id: str | None
    human_decision: str | None
    human_notes: str | None
    human_timestamp_utc: str | None


class AuditChain:
    """
    Append-only SQLite audit trail for LLM decisions.

    Args:
        db_path: Path to SQLite database file
    """

    def __init__(self, db_path: str | Path = "audit.db"):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_decisions (
                    entry_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                    pipeline_id  TEXT NOT NULL,
                    timestamp_utc TEXT NOT NULL,
                    input_hash   TEXT NOT NULL,
                    prompt_hash  TEXT NOT NULL,
                    output       TEXT NOT NULL,
                    confidence   REAL NOT NULL,
                    model_id     TEXT NOT NULL,
                    gate_outcome TEXT NOT NULL,
                    metadata     TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS human_reviews (
                    review_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_id         INTEGER NOT NULL REFERENCES ai_decisions(entry_id),
                    reviewer_id      TEXT NOT NULL,
                    decision         TEXT NOT NULL,
                    notes            TEXT,
                    timestamp_utc    TEXT NOT NULL,
                    UNIQUE(entry_id)
                )
            """)
            conn.commit()

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def log_ai_decision(
        self,
        pipeline_id: str,
        input_text: str,
        prompt: str,
        output: str,
        confidence: float,
        model_id: str,
        gate_outcome: str = "PASS",
        metadata: dict | None = None,
    ) -> int:
        """Log an AI decision. Returns entry_id for subsequent human review logging."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO ai_decisions
                   (pipeline_id, timestamp_utc, input_hash, prompt_hash, output,
                    confidence, model_id, gate_outcome, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pipeline_id,
                    datetime.now(timezone.utc).isoformat(),
                    self._hash(input_text),
                    self._hash(prompt),
                    output,
                    confidence,
                    model_id,
                    gate_outcome,
                    json.dumps(metadata or {}),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def log_human_review(
        self,
        entry_id: int,
        reviewer_id: str,
        decision: str,
        notes: str = "",
    ) -> None:
        """Log a human reviewer's decision against a prior AI decision."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO human_reviews
                   (entry_id, reviewer_id, decision, notes, timestamp_utc)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    entry_id,
                    reviewer_id,
                    decision,
                    notes,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()

    def get_entry(self, entry_id: int) -> AuditEntry | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT d.*, r.reviewer_id AS human_review_id, r.decision AS human_decision,
                          r.notes AS human_notes, r.timestamp_utc AS human_timestamp_utc
                   FROM ai_decisions d
                   LEFT JOIN human_reviews r ON d.entry_id = r.entry_id
                   WHERE d.entry_id = ?""",
                (entry_id,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_entry(row)

    def get_pipeline_history(self, pipeline_id: str, limit: int = 100) -> list[AuditEntry]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT d.*, r.reviewer_id AS human_review_id, r.decision AS human_decision,
                          r.notes AS human_notes, r.timestamp_utc AS human_timestamp_utc
                   FROM ai_decisions d
                   LEFT JOIN human_reviews r ON d.entry_id = r.entry_id
                   WHERE d.pipeline_id = ?
                   ORDER BY d.entry_id DESC
                   LIMIT ?""",
                (pipeline_id, limit),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def get_stats(self, pipeline_id: str | None = None) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            where = "WHERE d.pipeline_id = ?" if pipeline_id else ""
            params = (pipeline_id,) if pipeline_id else ()
            row = conn.execute(
                f"""SELECT
                    COUNT(*) AS total,
                    AVG(d.confidence) AS avg_confidence,
                    SUM(CASE WHEN d.gate_outcome = 'BLOCK' THEN 1 ELSE 0 END) AS blocked,
                    SUM(CASE WHEN r.entry_id IS NOT NULL THEN 1 ELSE 0 END) AS reviewed,
                    SUM(CASE WHEN r.decision = 'override' THEN 1 ELSE 0 END) AS overridden
                   FROM ai_decisions d
                   LEFT JOIN human_reviews r ON d.entry_id = r.entry_id
                   {where}""",
                params,
            ).fetchone()
        return {
            "total_decisions": row[0],
            "avg_confidence": round(row[1], 3) if row[1] else None,
            "blocked_by_gate": row[2],
            "human_reviewed": row[3],
            "analyst_overrides": row[4],
            "override_rate": round(row[4] / row[3], 3) if row[3] else None,
        }

    def export_csv(self, output_path: str | Path) -> None:
        import csv
        entries = self.get_pipeline_history("", limit=0)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT d.*, r.reviewer_id, r.decision AS human_decision,
                          r.notes, r.timestamp_utc AS review_timestamp
                   FROM ai_decisions d LEFT JOIN human_reviews r ON d.entry_id = r.entry_id
                   ORDER BY d.entry_id"""
            ).fetchall()
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys() if rows else [])
            writer.writeheader()
            writer.writerows([dict(r) for r in rows])

    @staticmethod
    def _row_to_entry(row) -> AuditEntry:
        return AuditEntry(
            entry_id=row["entry_id"],
            pipeline_id=row["pipeline_id"],
            timestamp_utc=row["timestamp_utc"],
            input_hash=row["input_hash"],
            prompt_hash=row["prompt_hash"],
            output=row["output"],
            confidence=row["confidence"],
            model_id=row["model_id"],
            gate_outcome=row["gate_outcome"],
            metadata=json.loads(row["metadata"]),
            human_review_id=row["human_review_id"],
            human_decision=row["human_decision"],
            human_notes=row["human_notes"],
            human_timestamp_utc=row["human_timestamp_utc"],
        )
