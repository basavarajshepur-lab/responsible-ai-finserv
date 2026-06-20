"""
HITLQueue — Human-in-the-Loop review queue for blocked or flagged outputs.

When the ConfidenceGate blocks an output, it goes here.
Analysts review, override or confirm, and their decision is logged back to AuditChain.

The queue is persistent (SQLite) so items survive restarts and can be
reviewed asynchronously. In production this would feed a task management
system or Slack notification — the pattern stays the same.

Regulatory question answered:
  "Who reviewed the AI's decision, when, and what did they decide?"
  — FCA DP5/22 §5.2, SR 11-7 Section 3

Usage:
    queue = HITLQueue(db_path="audit.db")
    item_id = queue.enqueue(
        pipeline_id="doc_classifier",
        audit_entry_id=42,
        ai_output="REGULATORY_FILING",
        confidence=0.71,
        reason="Below 0.85 threshold",
        context={"document": "earnings_release_Q3.pdf"},
    )
    queue.review(item_id, reviewer_id="analyst_1", decision="confirmed", notes="")
"""

import sqlite3
import json
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class QueueStatus(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    CONFIRMED = "confirmed"
    OVERRIDDEN = "overridden"
    ESCALATED = "escalated"


@dataclass
class QueueItem:
    item_id: int
    pipeline_id: str
    audit_entry_id: int
    ai_output: str
    confidence: float
    reason: str
    context: dict
    status: QueueStatus
    created_utc: str
    reviewer_id: str | None
    reviewer_decision: str | None
    reviewer_notes: str | None
    reviewed_utc: str | None


class HITLQueue:
    """
    Persistent human review queue for LLM outputs that did not clear the ConfidenceGate.

    Args:
        db_path: Path to SQLite database (can share with AuditChain)
    """

    def __init__(self, db_path: str | Path = "audit.db"):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hitl_queue (
                    item_id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    pipeline_id     TEXT NOT NULL,
                    audit_entry_id  INTEGER,
                    ai_output       TEXT NOT NULL,
                    confidence      REAL NOT NULL,
                    reason          TEXT NOT NULL,
                    context         TEXT NOT NULL,
                    status          TEXT NOT NULL DEFAULT 'pending',
                    created_utc     TEXT NOT NULL,
                    reviewer_id     TEXT,
                    reviewer_decision TEXT,
                    reviewer_notes  TEXT,
                    reviewed_utc    TEXT
                )
            """)
            conn.commit()

    def enqueue(
        self,
        pipeline_id: str,
        ai_output: str,
        confidence: float,
        reason: str,
        audit_entry_id: int | None = None,
        context: dict | None = None,
    ) -> int:
        """Add an item to the HITL review queue. Returns item_id."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO hitl_queue
                   (pipeline_id, audit_entry_id, ai_output, confidence, reason, context, created_utc)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    pipeline_id,
                    audit_entry_id,
                    ai_output,
                    confidence,
                    reason,
                    json.dumps(context or {}),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def review(
        self,
        item_id: int,
        reviewer_id: str,
        decision: str,
        notes: str = "",
    ) -> None:
        """Record a reviewer's decision on a queue item."""
        if decision not in ("confirmed", "overridden", "escalated"):
            raise ValueError("decision must be 'confirmed', 'overridden', or 'escalated'")
        status_map = {
            "confirmed": QueueStatus.CONFIRMED,
            "overridden": QueueStatus.OVERRIDDEN,
            "escalated": QueueStatus.ESCALATED,
        }
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """UPDATE hitl_queue
                   SET status = ?, reviewer_id = ?, reviewer_decision = ?,
                       reviewer_notes = ?, reviewed_utc = ?
                   WHERE item_id = ?""",
                (
                    status_map[decision].value,
                    reviewer_id,
                    decision,
                    notes,
                    datetime.now(timezone.utc).isoformat(),
                    item_id,
                ),
            )
            conn.commit()

    def get_pending(self, pipeline_id: str | None = None) -> list[QueueItem]:
        """Get all pending items, optionally filtered by pipeline."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if pipeline_id:
                rows = conn.execute(
                    "SELECT * FROM hitl_queue WHERE status = 'pending' AND pipeline_id = ? ORDER BY item_id",
                    (pipeline_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM hitl_queue WHERE status = 'pending' ORDER BY item_id"
                ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def get_item(self, item_id: int) -> QueueItem | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM hitl_queue WHERE item_id = ?", (item_id,)
            ).fetchone()
        return self._row_to_item(row) if row else None

    def get_stats(self, pipeline_id: str | None = None) -> dict:
        where = "WHERE pipeline_id = ?" if pipeline_id else ""
        params = (pipeline_id,) if pipeline_id else ()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                f"""SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
                    SUM(CASE WHEN status = 'confirmed' THEN 1 ELSE 0 END) AS confirmed,
                    SUM(CASE WHEN status = 'overridden' THEN 1 ELSE 0 END) AS overridden,
                    SUM(CASE WHEN status = 'escalated' THEN 1 ELSE 0 END) AS escalated
                   FROM hitl_queue {where}""",
                params,
            ).fetchone()
        return {
            "total": row[0], "pending": row[1],
            "confirmed": row[2], "overridden": row[3], "escalated": row[4],
        }

    @staticmethod
    def _row_to_item(row) -> QueueItem:
        return QueueItem(
            item_id=row["item_id"],
            pipeline_id=row["pipeline_id"],
            audit_entry_id=row["audit_entry_id"],
            ai_output=row["ai_output"],
            confidence=row["confidence"],
            reason=row["reason"],
            context=json.loads(row["context"]),
            status=QueueStatus(row["status"]),
            created_utc=row["created_utc"],
            reviewer_id=row["reviewer_id"],
            reviewer_decision=row["reviewer_decision"],
            reviewer_notes=row["reviewer_notes"],
            reviewed_utc=row["reviewed_utc"],
        )
