# PM Guide to Responsible AI in Financial Services

## How to Get an AI System Past Your CCO, CRO, and Regulator

*A practical framework from an AI PM who's done it inside a tier-1 bank.*

---

Getting AI into production at a regulated financial institution isn't primarily a technology problem. The technology works. The problem is: **Can you convince a Chief Compliance Officer, a Chief Risk Officer, and potentially an FCA examiner that the system is safe to operate?**

The answer is five controls. If you can answer "yes" to the five questions below — with documentation, code, and audit trails — you can get most AI use cases through governance.

---

## The Five Questions Regulators Always Ask

### 1. "How do you know when to trust it?"

**The control: ConfidenceGate**

Every LLM output has a confidence level. Most deployments ignore this and act on the output regardless. This is the mistake.

A ConfidenceGate defines a numerical threshold below which the AI is not trusted to act autonomously. Below that threshold, the output goes to a human. Above it, the system proceeds.

What it answers:
- FCA DP5/22 §4.3: "How do you manage model uncertainty?"
- SR 11-7 Section 4: "What are the model's operating conditions?"
- Your CCO's question: "What stops it from acting on a wrong answer?"

**In practice at Deutsche Bank:** Every AI classification in the CDO data platform had a confidence threshold. Outputs below 85% triggered a HITL review flag before any downstream pipeline consumed the result. This single control resolved 60% of governance objections.

---

### 2. "Show me everything it decided."

**The control: AuditChain**

Every AI decision must be logged — the input, the output, the confidence, the model version, and critically, the prompt hash. If someone changes the prompt after deployment, the hash changes. You'll see it.

The log must be append-only. Regulators treat AI decision logs like financial records. You cannot modify or delete them after the fact.

What it answers:
- FCA DP5/22 §5.1: "What records do you keep of AI decisions?"
- GDPR Article 22: "Can you explain this automated decision to the data subject?"
- Your FCA examiner's question: "Show me the decision log for the 14th of October."

**In practice:** An append-only SQLite database is sufficient for a pilot. PostgreSQL with Row-Level Security for production at scale. The schema is the same — what matters is append-only + model version + prompt hash.

---

### 3. "Who reviews it when it's wrong?"

**The control: HITLQueue**

Human-in-the-Loop is not an afterthought. It's the primary governance mechanism for high-stakes AI decisions. The ConfidenceGate identifies what needs human review; the HITLQueue manages the workflow.

Key design decisions:
- The AI recommendation is shown to the reviewer **before** they enter their own decision (not after). This prevents post-hoc rationalisation.
- Overrides require a documented reason.
- The reviewer's decision is logged against the AI's original decision, enabling quality tracking over time.

What it answers:
- FCA DP5/22 §5.2: "Who has oversight of AI decisions?"
- SR 11-7 Section 3: "What are the human controls on model outputs?"
- Your board's question: "Humans are still in charge, right?"

**In practice:** Override rate is your model quality metric. If analysts are overriding >20% of AI recommendations, the model needs retraining. If they're overriding <5%, consider whether HITL is adding value or just friction.

---

### 4. "How do you know it's still working?"

**The control: DriftMonitor**

LLMs drift. The model doesn't change — but the inputs do. When input data changes (new document formats, new terminology, new market conditions), the model's output distribution shifts without any error being raised.

A DriftMonitor compares the recent output distribution to a historical baseline. If the proportion of "HIGH RISK" classifications suddenly increases from 12% to 28%, that's a signal — either the inputs have changed or the model has drifted.

What it answers:
- SR 11-7 Section 4 (Ongoing Monitoring): "How do you track model performance in production?"
- SS1/23 §3.4: "What monitoring framework do you have?"
- Your model risk team's question: "How quickly would you detect if the model started misbehaving?"

**Three metrics to track always:**
1. Label/output distribution (week vs. 30-day baseline)
2. Average confidence score (drop → model is less certain → inputs may have drifted)
3. Gate block rate (increase → more outputs failing the confidence threshold → something has changed)

---

### 5. "Why did it decide that?"

**The control: ExplainabilityWrapper**

"The AI decided" is not an acceptable answer in regulated financial services. You need to be able to say "The AI classified this document as a regulatory filing because of X, Y, and Z, and here is the specific text from the document that drove that classification."

The ExplainabilityWrapper forces the model to output its reasoning chain alongside every decision. Not as a nice-to-have — as a requirement. The decision is not accepted without the reasoning.

What it answers:
- FCA DP5/22 §4.5: "Can you explain individual AI decisions?"
- EU AI Act Article 13: "What information can users access about AI decisions?"
- Your legal team's question: "If a customer challenges this decision, what do we tell them?"

**Chain-of-thought ordering matters:** Force the model to reason *before* it decides, not after. "Decide, then explain" produces rationalisation. "Reason, then conclude" produces genuine explainability.

---

## The Framework in One Diagram

```
Input → ExplainabilityWrapper → Decision + Reasoning
                                      │
                               ConfidenceGate
                              /              \
                        PASS (high conf)    BLOCK (low conf)
                              │                    │
                        AuditChain ←──────── HITLQueue
                              │              (human reviews)
                              │                    │
                         DriftMonitor         AuditChain
                         (tracks all)         (logs review)
```

Every input goes through every control. The AuditChain sees everything — automated decisions and human reviews alike.

---

## What This Doesn't Solve

Responsible AI controls are necessary but not sufficient. They do not replace:

- **Model risk management validation** (SR 11-7 / SS1/23) for high-materiality models
- **Fairness assessment** — controls don't detect if your model has disparate impact on protected groups
- **Data governance** — if your training data is biased, the controls surface the problem but don't fix it
- **Legal review** — for consumer-facing AI decisions with regulatory consequences (credit, insurance)

Think of these five controls as the engineering foundation. Model validation, fairness testing, and legal review sit on top.

---

## Getting AI Past Governance: A Checklist

Before your next AI governance submission, make sure you can answer:

- [ ] Can you show confidence scores for every decision?
- [ ] Is there a defined threshold below which humans review before action is taken?
- [ ] Is every AI decision logged with the input, output, confidence, and model version?
- [ ] Is the log append-only?
- [ ] Is there a named human who reviews low-confidence outputs?
- [ ] Is the reviewer's decision logged against the AI's original recommendation?
- [ ] Are you tracking output distribution over time?
- [ ] Do you have a defined alert threshold for distribution shift?
- [ ] Can you explain any individual AI decision in plain language?
- [ ] Is the reasoning chain logged alongside the decision?

If you can check all ten boxes, you have a defensible responsible AI posture for a tier-1 bank.

---

*Built from the Deutsche Bank CDO responsible AI framework (2023-2025), where this pattern was deployed across AI/data classification pipelines handling 450+ production models.*
