"""
Financial Document Classifier — working example integrating all 5 responsible AI controls.

What this demonstrates:
  - ExplainabilityWrapper: every decision comes with a reasoning chain
  - ConfidenceGate: low-confidence outputs are blocked and never act autonomously
  - HITLQueue: blocked outputs queue for analyst review
  - AuditChain: every decision is logged before the analyst sees it
  - DriftMonitor: output distribution tracked for behavioural shift alerts

This is the pattern used in production at Deutsche Bank for AI classification
pipelines: confidence scoring + audit chain + HITL gates + drift monitoring.
The library makes it drop-in for any new pipeline.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from rai_finserv import (
    ConfidenceGate,
    AuditChain,
    HITLQueue,
    DriftMonitor,
    ExplainabilityWrapper,
)
from examples.sample_documents import DOCUMENT_LABELS

load_dotenv()

PIPELINE_ID = "financial_doc_classifier"
DB_PATH = "pipeline_audit.db"
CONFIDENCE_THRESHOLD = 0.85

gate = ConfidenceGate(threshold=CONFIDENCE_THRESHOLD, warn_threshold=0.92)
audit = AuditChain(db_path=DB_PATH)
queue = HITLQueue(db_path=DB_PATH)
monitor = DriftMonitor(db_path=DB_PATH, pipeline_id=PIPELINE_ID)
wrapper = ExplainabilityWrapper(
    pipeline_id=PIPELINE_ID,
    system_context=(
        "You classify financial documents for a compliance routing system at a tier-1 bank. "
        "Documents are routed to different compliance teams based on type. "
        "Misclassification has regulatory consequences — be precise and transparent about uncertainty."
    ),
)


def classify_document(document_text: str, document_name: str = "unknown") -> dict:
    """
    Classify a financial document with all 5 responsible AI controls applied.

    Returns a result dict with decision, confidence, reasoning, audit trail,
    and whether human review is required.
    """
    print(f"\n{'─'*60}")
    print(f"Document: {document_name}")
    print(f"{'─'*60}")

    # Step 1: Classify with structured reasoning (ExplainabilityWrapper)
    print("  [1/4] Classifying with full reasoning chain...")
    decision = wrapper.classify(
        input_text=document_text,
        labels=DOCUMENT_LABELS,
        task_description=(
            "Classify this financial document by type for compliance routing. "
            "Documents are routed to: Regulatory Affairs (REGULATORY_FILING), "
            "Investor Relations (EARNINGS_RELEASE), Trading Desk (MARKET_COMMENTARY), "
            "Model Risk Committee (RISK_REPORT), or General Inbox (OTHER)."
        ),
    )
    print(f"  Decision: {decision.label} | Confidence: {decision.confidence:.0%}")

    # Step 2: Evaluate against confidence threshold (ConfidenceGate)
    print("  [2/4] Evaluating confidence gate...")
    gate_result = gate.evaluate(decision.label, decision.confidence)
    print(f"  Gate: {gate_result.outcome.value}")

    # Step 3: Log AI decision to audit trail BEFORE analyst sees result (AuditChain)
    print("  [3/4] Logging to audit trail...")
    prompt_used = f"Classify into: {', '.join(DOCUMENT_LABELS)}"
    entry_id = audit.log_ai_decision(
        pipeline_id=PIPELINE_ID,
        input_text=document_text,
        prompt=prompt_used,
        output=decision.label,
        confidence=decision.confidence,
        model_id=decision.model_id,
        gate_outcome=gate_result.outcome.value,
        metadata={
            "document_name": document_name,
            "key_evidence": decision.reasoning.key_evidence,
            "confidence_rationale": decision.reasoning.confidence_rationale,
        },
    )
    print(f"  Audit entry: #{entry_id}")

    # Step 4: Route to HITL queue if gate blocked (HITLQueue)
    hitl_item_id = None
    if gate_result.requires_hitl:
        print("  [4/4] Routing to HITL queue (confidence below threshold)...")
        hitl_item_id = queue.enqueue(
            pipeline_id=PIPELINE_ID,
            ai_output=decision.label,
            confidence=decision.confidence,
            reason=gate_result.reason,
            audit_entry_id=entry_id,
            context={
                "document_name": document_name,
                "key_evidence": decision.reasoning.key_evidence,
                "factors_considered": decision.reasoning.factors_considered,
                "factors_against": decision.reasoning.factors_against,
            },
        )
        print(f"  HITL queue item: #{hitl_item_id}")
    else:
        print("  [4/4] Gate passed — no HITL required")

    # Record observation for drift monitoring (DriftMonitor)
    monitor.record(
        label=decision.label,
        confidence=decision.confidence,
        gate_outcome=gate_result.outcome.value,
    )

    result = {
        "document_name": document_name,
        "label": decision.label,
        "confidence": decision.confidence,
        "gate_outcome": gate_result.outcome.value,
        "requires_hitl": gate_result.requires_hitl,
        "audit_entry_id": entry_id,
        "hitl_item_id": hitl_item_id,
        "routing": _get_routing(decision.label) if gate_result.outcome.value == "PASS" else "PENDING HUMAN REVIEW",
        "reasoning": {
            "factors_considered": decision.reasoning.factors_considered,
            "key_evidence": decision.reasoning.key_evidence,
            "factors_against": decision.reasoning.factors_against,
            "confidence_rationale": decision.reasoning.confidence_rationale,
        },
    }

    print(f"\n  {'✓' if not gate_result.requires_hitl else '⚠'} Result: {result['label']} → {result['routing']}")
    return result


def _get_routing(label: str) -> str:
    return {
        "REGULATORY_FILING": "Regulatory Affairs team",
        "EARNINGS_RELEASE": "Investor Relations team",
        "MARKET_COMMENTARY": "Trading Desk review",
        "RISK_REPORT": "Model Risk Committee",
        "OTHER": "General Compliance Inbox",
    }.get(label, "General Compliance Inbox")


def print_drift_report() -> None:
    """Check and print the current drift report."""
    report = monitor.check_drift(window_days=7, baseline_days=30)
    print(f"\n{'='*60}")
    print("DRIFT MONITOR REPORT")
    print(f"{'='*60}")
    print(f"Window ({report.window_days}d): {report.window_count} observations")
    print(f"Baseline ({report.baseline_days}d): {report.baseline_count} observations")
    if report.alert:
        print("\n⚠ DRIFT ALERTS:")
        for alert in report.alerts:
            print(f"  • {alert}")
    else:
        print("\n✓ No significant drift detected")
    print(f"\nWindow label distribution:")
    for label, pct in report.label_distribution_window.items():
        print(f"  {label}: {pct:.1%}")


if __name__ == "__main__":
    from examples.sample_documents import SAMPLE_DOCUMENTS

    print("FINANCIAL DOCUMENT CLASSIFIER")
    print("Responsible AI Controls: ConfidenceGate + AuditChain + HITLQueue + DriftMonitor + ExplainabilityWrapper")
    print("=" * 60)

    results = []
    for name, text in SAMPLE_DOCUMENTS.items():
        result = classify_document(text, document_name=name)
        results.append(result)

    print(f"\n{'='*60}")
    print("PIPELINE SUMMARY")
    print(f"{'='*60}")
    print(f"Documents processed: {len(results)}")
    print(f"Auto-routed:         {sum(1 for r in results if not r['requires_hitl'])}")
    print(f"HITL queue:          {sum(1 for r in results if r['requires_hitl'])}")

    audit_stats = audit.get_stats(PIPELINE_ID)
    print(f"\nAudit trail stats:")
    print(f"  Total decisions logged: {audit_stats['total_decisions']}")
    print(f"  Average confidence:     {audit_stats['avg_confidence']:.2%}" if audit_stats['avg_confidence'] else "  Average confidence: N/A")
    print(f"  Gate blocks:            {audit_stats['blocked_by_gate']}")

    queue_stats = queue.get_stats(PIPELINE_ID)
    print(f"\nHITL queue stats:")
    print(f"  Pending review:  {queue_stats['pending']}")
    print(f"  Confirmed:       {queue_stats['confirmed']}")
    print(f"  Overridden:      {queue_stats['overridden']}")

    print_drift_report()
