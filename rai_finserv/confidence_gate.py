"""
ConfidenceGate — blocks LLM output below a confidence threshold.

The single most important responsible AI control for high-stakes decisions.
An LLM that is uncertain about its output should not act autonomously —
it should hand off to a human. This gate enforces that policy at the code level.

Regulatory question answered:
  "How do you ensure the model doesn't act on low-quality outputs?"
  — FCA DP5/22 §4.3, SR 11-7 Section 4

Usage:
    gate = ConfidenceGate(threshold=0.85)
    result = gate.evaluate(output_text, confidence_score)
    if result.passed:
        # proceed with output
    else:
        # route to HITL queue
"""

from dataclasses import dataclass
from enum import Enum


class GateOutcome(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    WARN = "WARN"


@dataclass
class GateResult:
    outcome: GateOutcome
    confidence: float
    threshold: float
    output: str
    reason: str
    requires_hitl: bool


class ConfidenceGate:
    """
    Evaluates LLM output confidence against a configured threshold.

    Two-level policy:
    - Below warn_threshold: WARN — flag for monitoring but allow through
    - Below threshold: BLOCK — route to HITL, do not act autonomously

    Args:
        threshold: Confidence below this → BLOCK and route to HITL
        warn_threshold: Confidence below this → WARN (optional; must be > threshold)
    """

    def __init__(self, threshold: float = 0.85, warn_threshold: float | None = None):
        if not 0 < threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        if warn_threshold is not None and warn_threshold <= threshold:
            raise ValueError("warn_threshold must be above threshold")
        self.threshold = threshold
        self.warn_threshold = warn_threshold

    def evaluate(self, output: str, confidence: float) -> GateResult:
        """Evaluate whether output clears the confidence threshold."""
        if not 0 <= confidence <= 1:
            raise ValueError(f"confidence must be between 0 and 1, got {confidence}")

        if confidence < self.threshold:
            return GateResult(
                outcome=GateOutcome.BLOCK,
                confidence=confidence,
                threshold=self.threshold,
                output=output,
                reason=f"Confidence {confidence:.2%} below threshold {self.threshold:.2%} — HITL required",
                requires_hitl=True,
            )

        if self.warn_threshold and confidence < self.warn_threshold:
            return GateResult(
                outcome=GateOutcome.WARN,
                confidence=confidence,
                threshold=self.threshold,
                output=output,
                reason=f"Confidence {confidence:.2%} below warn threshold {self.warn_threshold:.2%} — monitor",
                requires_hitl=False,
            )

        return GateResult(
            outcome=GateOutcome.PASS,
            confidence=confidence,
            threshold=self.threshold,
            output=output,
            reason=f"Confidence {confidence:.2%} clears threshold {self.threshold:.2%}",
            requires_hitl=False,
        )

    def evaluate_batch(self, outputs: list[tuple[str, float]]) -> list[GateResult]:
        """Evaluate a batch of (output, confidence) pairs."""
        return [self.evaluate(output, conf) for output, conf in outputs]
