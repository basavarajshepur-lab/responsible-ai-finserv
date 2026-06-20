"""
responsible-ai-finserv — Production responsible AI controls for financial services.

Five controls, composable, drop-in ready:

    from rai_finserv import ConfidenceGate, AuditChain, HITLQueue, DriftMonitor, ExplainabilityWrapper
"""

from .confidence_gate import ConfidenceGate, GateResult, GateOutcome
from .audit_chain import AuditChain, AuditEntry
from .hitl_queue import HITLQueue, QueueItem, QueueStatus
from .drift_monitor import DriftMonitor, DriftReport
from .explainability_wrapper import ExplainabilityWrapper, ExplainedDecision, ExplainedReasoning

__version__ = "1.0.0"
__all__ = [
    "ConfidenceGate", "GateResult", "GateOutcome",
    "AuditChain", "AuditEntry",
    "HITLQueue", "QueueItem", "QueueStatus",
    "DriftMonitor", "DriftReport",
    "ExplainabilityWrapper", "ExplainedDecision", "ExplainedReasoning",
]
