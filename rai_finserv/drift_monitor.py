"""
DriftMonitor — tracks LLM output distribution over time and alerts on behavioural shift.

Model drift in LLM pipelines is subtle and dangerous. When a model is updated,
when input data distribution changes, or when a prompt is subtly modified,
the output distribution can shift without any error being raised. The system
appears to work but is producing different outputs from the same inputs.

What DriftMonitor tracks:
  - Label/category distribution: if a classifier always returned 70% "LOW RISK"
    last month and is now returning 50%, that's a signal
  - Confidence score distribution: a drop in average confidence indicates
    the model is less certain about the same type of inputs
  - Block rate: if the ConfidenceGate is blocking more outputs than usual,
    input data may have drifted outside the model's training distribution

Regulatory question answered:
  "How do you know the model is still performing as expected in production?"
  — SR 11-7 Section 4 (Ongoing Monitoring), SS1/23 §3.4

Usage:
    monitor = DriftMonitor(db_path="audit.db", pipeline_id="doc_classifier")
    monitor.record(label="REGULATORY_FILING", confidence=0.91, gate_outcome="PASS")
    report = monitor.check_drift(window_days=7, baseline_days=30)
    if report.alert:
        # notify model risk team
"""

import sqlite3
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path


@dataclass
class DriftReport:
    pipeline_id: str
    generated_at: str
    window_days: int
    baseline_days: int
    window_count: int
    baseline_count: int
    alert: bool
    alerts: list[str]
    label_distribution_window: dict[str, float]
    label_distribution_baseline: dict[str, float]
    avg_confidence_window: float | None
    avg_confidence_baseline: float | None
    block_rate_window: float | None
    block_rate_baseline: float | None
    label_drift_scores: dict[str, float] = field(default_factory=dict)


class DriftMonitor:
    """
    Tracks output distribution and confidence over time to detect model drift.

    Args:
        db_path: Path to SQLite database (can share with AuditChain / HITLQueue)
        pipeline_id: Identifier for the pipeline being monitored
        confidence_alert_threshold: Alert if average confidence drops by more than this
        label_drift_threshold: Alert if any label's share changes by more than this
        block_rate_alert_threshold: Alert if block rate increases by more than this
    """

    def __init__(
        self,
        db_path: str | Path = "audit.db",
        pipeline_id: str = "default",
        confidence_alert_threshold: float = 0.05,
        label_drift_threshold: float = 0.10,
        block_rate_alert_threshold: float = 0.05,
    ):
        self.db_path = Path(db_path)
        self.pipeline_id = pipeline_id
        self.confidence_alert_threshold = confidence_alert_threshold
        self.label_drift_threshold = label_drift_threshold
        self.block_rate_alert_threshold = block_rate_alert_threshold
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS drift_observations (
                    obs_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    pipeline_id  TEXT NOT NULL,
                    timestamp_utc TEXT NOT NULL,
                    label        TEXT NOT NULL,
                    confidence   REAL NOT NULL,
                    gate_outcome TEXT NOT NULL
                )
            """)
            conn.commit()

    def record(self, label: str, confidence: float, gate_outcome: str = "PASS") -> None:
        """Record a single model output observation."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO drift_observations (pipeline_id, timestamp_utc, label, confidence, gate_outcome)
                   VALUES (?, ?, ?, ?, ?)""",
                (self.pipeline_id, datetime.now(timezone.utc).isoformat(), label, confidence, gate_outcome),
            )
            conn.commit()

    def _fetch_window(self, days: int, offset_days: int = 0) -> list[sqlite3.Row]:
        end = datetime.now(timezone.utc) - timedelta(days=offset_days)
        start = end - timedelta(days=days)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                """SELECT label, confidence, gate_outcome FROM drift_observations
                   WHERE pipeline_id = ? AND timestamp_utc BETWEEN ? AND ?""",
                (self.pipeline_id, start.isoformat(), end.isoformat()),
            ).fetchall()

    @staticmethod
    def _label_distribution(rows: list) -> dict[str, float]:
        if not rows:
            return {}
        counts = Counter(r["label"] for r in rows)
        total = sum(counts.values())
        return {label: round(count / total, 4) for label, count in counts.items()}

    @staticmethod
    def _avg_confidence(rows: list) -> float | None:
        if not rows:
            return None
        return round(sum(r["confidence"] for r in rows) / len(rows), 4)

    @staticmethod
    def _block_rate(rows: list) -> float | None:
        if not rows:
            return None
        blocked = sum(1 for r in rows if r["gate_outcome"] == "BLOCK")
        return round(blocked / len(rows), 4)

    def check_drift(self, window_days: int = 7, baseline_days: int = 30) -> DriftReport:
        """Compare recent window against historical baseline. Returns DriftReport."""
        window_rows = self._fetch_window(days=window_days)
        baseline_rows = self._fetch_window(days=baseline_days, offset_days=window_days)

        window_dist = self._label_distribution(window_rows)
        baseline_dist = self._label_distribution(baseline_rows)
        window_conf = self._avg_confidence(window_rows)
        baseline_conf = self._avg_confidence(baseline_rows)
        window_block = self._block_rate(window_rows)
        baseline_block = self._block_rate(baseline_rows)

        alerts = []
        label_drift_scores = {}

        # Label distribution drift
        all_labels = set(window_dist) | set(baseline_dist)
        for label in all_labels:
            w = window_dist.get(label, 0)
            b = baseline_dist.get(label, 0)
            drift = abs(w - b)
            label_drift_scores[label] = round(drift, 4)
            if drift > self.label_drift_threshold:
                alerts.append(
                    f"Label '{label}' share changed by {drift:.1%} "
                    f"(baseline {b:.1%} → window {w:.1%})"
                )

        # Confidence drift
        if window_conf is not None and baseline_conf is not None:
            conf_drop = baseline_conf - window_conf
            if conf_drop > self.confidence_alert_threshold:
                alerts.append(
                    f"Average confidence dropped {conf_drop:.1%} "
                    f"(baseline {baseline_conf:.2%} → window {window_conf:.2%})"
                )

        # Block rate drift
        if window_block is not None and baseline_block is not None:
            block_increase = window_block - baseline_block
            if block_increase > self.block_rate_alert_threshold:
                alerts.append(
                    f"Gate block rate increased {block_increase:.1%} "
                    f"(baseline {baseline_block:.1%} → window {window_block:.1%})"
                )

        return DriftReport(
            pipeline_id=self.pipeline_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            window_days=window_days,
            baseline_days=baseline_days,
            window_count=len(window_rows),
            baseline_count=len(baseline_rows),
            alert=len(alerts) > 0,
            alerts=alerts,
            label_distribution_window=window_dist,
            label_distribution_baseline=baseline_dist,
            avg_confidence_window=window_conf,
            avg_confidence_baseline=baseline_conf,
            block_rate_window=window_block,
            block_rate_baseline=baseline_block,
            label_drift_scores=label_drift_scores,
        )
