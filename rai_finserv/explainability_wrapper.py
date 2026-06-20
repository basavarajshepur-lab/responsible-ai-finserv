"""
ExplainabilityWrapper — forces structured reasoning alongside every LLM decision.

The "black box" objection from compliance, legal, and regulators is always the same:
"How do we know why it decided that?" An LLM that outputs only a label or score
cannot be explained to a regulator. An LLM that is forced to output its reasoning
chain alongside the decision gives auditors, model risk teams, and humans something
to evaluate.

This wrapper intercepts the LLM call and appends structured reasoning requirements
to the prompt. It returns both the decision AND the reasoning, making the decision
explainable and auditable.

Key design:
- Forces reasoning BEFORE the decision (chain-of-thought ordering matters —
  models reason better when required to think first, then conclude)
- Returns structured output via Claude tool use for consistent parsing
- Reasoning fields: factors_considered, key_evidence, factors_against, confidence_rationale

Regulatory question answered:
  "Can you explain why the AI made this specific decision on this specific input?"
  — FCA DP5/22 §4.5 (Explainability), EU AI Act Art. 13, SR 11-7 Section 4

Usage:
    wrapper = ExplainabilityWrapper(pipeline_id="doc_classifier")
    result = wrapper.classify(
        input_text=document_text,
        labels=["REGULATORY_FILING", "EARNINGS_RELEASE", "MARKET_COMMENTARY", "RISK_REPORT"],
        task_description="Classify this financial document by type for compliance routing",
    )
    print(result.label, result.confidence)
    print(result.reasoning.factors_considered)
"""

from dataclasses import dataclass
from anthropic import Anthropic

client = Anthropic()


@dataclass
class ExplainedReasoning:
    factors_considered: list[str]
    key_evidence: str
    factors_against: list[str]
    confidence_rationale: str


@dataclass
class ExplainedDecision:
    label: str
    confidence: float
    reasoning: ExplainedReasoning
    model_id: str
    pipeline_id: str
    raw_input_length: int


class ExplainabilityWrapper:
    """
    Wraps an LLM classification call to force structured reasoning output.

    Args:
        pipeline_id: Identifier for the pipeline (used in logging)
        model_id: Claude model to use
        system_context: Optional domain context to inject into system prompt
    """

    def __init__(
        self,
        pipeline_id: str = "default",
        model_id: str = "claude-haiku-4-5-20251001",
        system_context: str = "",
    ):
        self.pipeline_id = pipeline_id
        self.model_id = model_id
        self.system_context = system_context

    def _build_tool(self, labels: list[str]) -> dict:
        return {
            "name": "record_decision_with_reasoning",
            "description": "Record the classification decision with full reasoning chain",
            "input_schema": {
                "type": "object",
                "properties": {
                    "factors_considered": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of factors from the document that support this classification"
                    },
                    "key_evidence": {
                        "type": "string",
                        "description": "The single most important piece of evidence for this classification"
                    },
                    "factors_against": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Any signals that might suggest a different classification"
                    },
                    "confidence_rationale": {
                        "type": "string",
                        "description": "Why the confidence score is set at this level"
                    },
                    "label": {
                        "type": "string",
                        "enum": labels,
                        "description": "The classification label"
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": "Confidence in this classification (0-1)"
                    }
                },
                "required": ["factors_considered", "key_evidence", "factors_against",
                             "confidence_rationale", "label", "confidence"]
            }
        }

    def classify(
        self,
        input_text: str,
        labels: list[str],
        task_description: str,
    ) -> ExplainedDecision:
        """Classify input_text into one of labels, with full reasoning chain."""
        system = f"""You are an expert classifier for financial services compliance.
{self.system_context}

IMPORTANT: Before deciding, you MUST reason through:
1. What signals in the text point toward each possible label
2. What the strongest single piece of evidence is
3. What signals might argue against your chosen classification
4. Why your confidence is set at the level you choose

This reasoning will be reviewed by compliance and model risk teams.
Be specific — reference actual text from the document."""

        response = client.messages.create(
            model=self.model_id,
            max_tokens=1000,
            temperature=0.1,
            system=system,
            tools=[self._build_tool(labels)],
            tool_choice={"type": "any"},
            messages=[{
                "role": "user",
                "content": f"""Task: {task_description}

Available labels: {', '.join(labels)}

Document to classify:
---
{input_text}
---

Reason through the classification, then record your decision with full reasoning."""
            }],
        )

        for block in response.content:
            if block.type == "tool_use":
                data = block.input
                return ExplainedDecision(
                    label=data["label"],
                    confidence=data["confidence"],
                    reasoning=ExplainedReasoning(
                        factors_considered=data["factors_considered"],
                        key_evidence=data["key_evidence"],
                        factors_against=data["factors_against"],
                        confidence_rationale=data["confidence_rationale"],
                    ),
                    model_id=self.model_id,
                    pipeline_id=self.pipeline_id,
                    raw_input_length=len(input_text),
                )

        raise ValueError("ExplainabilityWrapper: model did not return structured decision")
