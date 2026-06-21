# responsible-ai-finserv

**Production responsible AI controls for financial services.** Five composable Python components that answer the five questions every CCO, CRO, and regulator will ask about your AI system.

![Python](https://img.shields.io/badge/Python-3.11+-blue) ![License](https://img.shields.io/badge/License-MIT-green) ![Status](https://img.shields.io/badge/Status-Production--Ready-brightgreen) ![Claude](https://img.shields.io/badge/Powered%20by-Claude%20AI-orange)

---

## The Real Barrier to AI in Financial Services

Getting AI past a CCO isn't a technology problem. The technology works.

The problem is answering five questions:

1. *"How do you know when to trust it?"*
2. *"Show me everything it decided."*
3. *"Who reviews it when it's wrong?"*
4. *"How do you know it's still working?"*
5. *"Why did it decide that?"*

This library is the engineering answer to all five. It's the pattern extracted from building AI classification pipelines at Deutsche Bank CDO across 450+ production models, where every deployment had to pass the same governance questions.

---

## Five Controls, One Import

```python
from rai_finserv import (
    ConfidenceGate,        # blocks outputs below threshold — routes to human review
    AuditChain,            # append-only log: every decision, input, output, model version
    HITLQueue,             # human review workflow for blocked outputs
    DriftMonitor,          # tracks output distribution — alerts on behavioural shift
    ExplainabilityWrapper, # forces structured reasoning alongside every decision
)
```

Each control is independent. Use one, use all five, compose them in any order.

---

## Quick Start

```bash
git clone https://github.com/basavarajshepur-lab/responsible-ai-finserv
cd responsible-ai-finserv
pip install -r requirements.txt
cp .env.example .env
# Add your ANTHROPIC_API_KEY
streamlit run app.py    if this doesn't work then run python -m streamlit run app.py   # interactive demo
python -m examples.classifier_pipeline         # CLI: classify 5 sample documents
```

---

## The Controls

### ConfidenceGate — *"How do you know when to trust it?"*

```python
gate = ConfidenceGate(threshold=0.85, warn_threshold=0.92)
result = gate.evaluate(output="REGULATORY_FILING", confidence=0.71)
# result.outcome → BLOCK
# result.requires_hitl → True
# result.reason → "Confidence 71% below threshold 85% — HITL required"
```

Two-level policy: outputs below `warn_threshold` are flagged for monitoring; below `threshold`, they are blocked and routed to human review. No autonomous action on uncertain outputs.

**Regulatory question:** *"What stops it from acting on a wrong answer?"* (FCA DP5/22 §4.3, SR 11-7 Section 4)

---

### AuditChain — *"Show me everything it decided."*

```python
audit = AuditChain(db_path="audit.db")

entry_id = audit.log_ai_decision(
    pipeline_id="doc_classifier",
    input_text=document_text,
    prompt=system_prompt,       # hashed — detects silent prompt changes
    output="REGULATORY_FILING",
    confidence=0.91,
    model_id="claude-haiku-4-5-20251001",  # model version logged
    gate_outcome="PASS",
)

audit.log_human_review(entry_id, reviewer_id="analyst_1", decision="confirmed")

stats = audit.get_stats("doc_classifier")
# {'total_decisions': 47, 'avg_confidence': 0.884, 'blocked_by_gate': 6,
#  'human_reviewed': 6, 'analyst_overrides': 1, 'override_rate': 0.167}
```

Append-only SQLite. Every AI decision is logged before the analyst sees it — preventing post-hoc rationalisation. Prompt hash detects silent prompt changes. Model version tracked for before/after comparisons on upgrades. CSV export for regulatory submission.

**Regulatory question:** *"Show me the decision log for the 14th of October."* (FCA DP5/22 §5.1, GDPR Art. 22)

---

### HITLQueue — *"Who reviews it when it's wrong?"*

```python
queue = HITLQueue(db_path="audit.db")

# When gate blocks an output:
item_id = queue.enqueue(
    pipeline_id="doc_classifier",
    ai_output="REGULATORY_FILING",
    confidence=0.71,
    reason="Below 0.85 threshold",
    audit_entry_id=entry_id,
    context={"document_name": "Q3_disclosure.pdf", "key_evidence": "..."},
)

# When analyst reviews:
queue.review(item_id, reviewer_id="analyst_1", decision="confirmed", notes="")
# decisions: "confirmed" | "overridden" | "escalated"

pending = queue.get_pending("doc_classifier")
stats = queue.get_stats("doc_classifier")
```

Persistent SQLite queue. AI recommendation shown to reviewer before they enter their own decision. Override requires a documented reason. Override rate is your model quality signal — if analysts override >20%, the model needs work.

**Regulatory question:** *"Who has oversight of AI decisions?"* (FCA DP5/22 §5.2)

---

### DriftMonitor — *"How do you know it's still working?"*

```python
monitor = DriftMonitor(
    db_path="audit.db",
    pipeline_id="doc_classifier",
    confidence_alert_threshold=0.05,   # alert if avg confidence drops >5%
    label_drift_threshold=0.10,        # alert if any label share changes >10%
    block_rate_alert_threshold=0.05,   # alert if gate block rate increases >5%
)

monitor.record(label="REGULATORY_FILING", confidence=0.91, gate_outcome="PASS")

report = monitor.check_drift(window_days=7, baseline_days=30)
# report.alert → True/False
# report.alerts → ["Label 'RISK_REPORT' share changed by 18.2% (baseline 12% → window 30.2%)"]
# report.avg_confidence_window → 0.81
# report.avg_confidence_baseline → 0.89
```

Three signals tracked: label distribution shift, confidence score drop, gate block rate increase. Weekly-vs-30-day comparison by default. If any threshold is breached, model risk team is notified.

**Regulatory question:** *"How quickly would you detect if the model started misbehaving?"* (SR 11-7 Section 4, SS1/23 §3.4)

---

### ExplainabilityWrapper — *"Why did it decide that?"*

```python
wrapper = ExplainabilityWrapper(
    pipeline_id="doc_classifier",
    system_context="You classify financial documents for compliance routing.",
)

decision = wrapper.classify(
    input_text=document_text,
    labels=["REGULATORY_FILING", "EARNINGS_RELEASE", "MARKET_COMMENTARY", "RISK_REPORT", "OTHER"],
    task_description="Classify for compliance routing at a tier-1 bank.",
)

print(decision.label)           # "REGULATORY_FILING"
print(decision.confidence)      # 0.94
print(decision.reasoning.factors_considered)
# ["Document references CRR Regulation (EU) No 575/2013",
#  "CET1 ratio and Total Capital Ratio explicitly stated",
#  "References EBA Guidelines disclosure requirements",
#  "Pillar 3 disclosure format and section headers present"]
print(decision.reasoning.key_evidence)
# "Title 'PILLAR 3 DISCLOSURE — Q3 2024' and direct reference to
#  EBA Guidelines on Part Eight of CRR confirms regulatory filing classification"
print(decision.reasoning.factors_against)
# ["Contains some financial performance data that could suggest earnings release"]
```

Forces structured reasoning via Claude tool use: factors considered, key evidence, factors against, confidence rationale. Reasoning is logged in AuditChain alongside the decision. "The AI decided" is replaced by "The AI decided X because Y, with Z as the key evidence."

**Regulatory question:** *"Can you explain this specific decision to the data subject?"* (FCA DP5/22 §4.5, EU AI Act Art. 13)

---

## End-to-End Example

```python
from rai_finserv import ConfidenceGate, AuditChain, HITLQueue, DriftMonitor, ExplainabilityWrapper

gate    = ConfidenceGate(threshold=0.85)
audit   = AuditChain(db_path="audit.db")
queue   = HITLQueue(db_path="audit.db")
monitor = DriftMonitor(db_path="audit.db", pipeline_id="doc_classifier")
wrapper = ExplainabilityWrapper(pipeline_id="doc_classifier")

# 1. Classify with reasoning
decision = wrapper.classify(document_text, labels, task_description)

# 2. Gate check
gate_result = gate.evaluate(decision.label, decision.confidence)

# 3. Log AI decision BEFORE analyst sees it (audit integrity)
entry_id = audit.log_ai_decision(
    pipeline_id="doc_classifier",
    input_text=document_text,
    prompt="Classify into: " + ", ".join(labels),
    output=decision.label,
    confidence=decision.confidence,
    model_id=decision.model_id,
    gate_outcome=gate_result.outcome.value,
)

# 4. Route to HITL if blocked
if gate_result.requires_hitl:
    queue.enqueue("doc_classifier", decision.label, decision.confidence,
                  gate_result.reason, audit_entry_id=entry_id)

# 5. Track for drift
monitor.record(decision.label, decision.confidence, gate_result.outcome.value)
```

---

## Project Structure

```
responsible-ai-finserv/
├── rai_finserv/
│   ├── confidence_gate.py         # ConfidenceGate control
│   ├── audit_chain.py             # AuditChain — append-only SQLite log
│   ├── hitl_queue.py              # HITLQueue — human review workflow
│   ├── drift_monitor.py           # DriftMonitor — distribution tracking
│   └── explainability_wrapper.py  # ExplainabilityWrapper — structured reasoning
├── examples/
│   ├── classifier_pipeline.py     # Working example: all 5 controls on doc classifier
│   └── sample_documents.py        # 5 realistic financial documents
├── app.py                         # Streamlit demo (5 tabs)
└── docs/
    └── pm-guide-responsible-ai.md # PM-level guide: how to get AI past your CCO
```

---

## The Architecture Principle

```
            ┌──────────────────────────────────────────┐
            │          Every LLM call goes through:    │
            │                                          │
            │  ExplainabilityWrapper                   │
            │      ↓ decision + reasoning              │
            │  ConfidenceGate                          │
            │      ↓ PASS          ↓ BLOCK             │
            │  AuditChain ←─── HITLQueue               │
            │      ↓         (human reviews)           │
            │  DriftMonitor  AuditChain                │
            │  (tracks all)  (logs review)             │
            └──────────────────────────────────────────┘
```

The AuditChain sees every decision — automated and human alike. This is what makes the system auditable: a complete, immutable record of what the AI decided and what humans decided to do with it.

---

## Background

Built by [Basavaraj Shepur](https://linkedin.com/in/basavarajshepur) — Senior AI Product Manager with 19 years in financial services. Former Senior Product Owner at Deutsche Bank CDO, where AI classification pipelines handling 450+ production models were deployed with exactly these governance controls. Every control in this library was designed in response to a real governance challenge: a CCO objection, a model risk committee question, or an FCA examiner's request.

Read the full framework: [docs/pm-guide-responsible-ai.md](docs/pm-guide-responsible-ai.md)

---

## License

MIT
