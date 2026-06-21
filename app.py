"""
Responsible AI FinServ — Streamlit Demo

Live demonstration of all 5 controls on a financial document classifier.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
from dotenv import load_dotenv
from rai_finserv import ConfidenceGate, AuditChain, HITLQueue, DriftMonitor, ExplainabilityWrapper
from examples.sample_documents import SAMPLE_DOCUMENTS, DOCUMENT_LABELS
from examples.classifier_pipeline import classify_document, print_drift_report, DB_PATH, PIPELINE_ID

load_dotenv()

st.set_page_config(page_title="Responsible AI FinServ", page_icon="🏦", layout="wide")
st.title("Responsible AI FinServ")
st.markdown(
    "**Production-grade AI controls library** — ConfidenceGate · AuditChain · HITLQueue · DriftMonitor · ExplainabilityWrapper"
)
st.divider()

audit = AuditChain(db_path=DB_PATH)
queue = HITLQueue(db_path=DB_PATH)
monitor = DriftMonitor(db_path=DB_PATH, pipeline_id=PIPELINE_ID)

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Classify Document", "HITL Review Queue", "Audit Trail", "Drift Monitor", "PM Guide"]
)

# ── Tab 1: Classify ───────────────────────────────────────────────────────────
with tab1:
    st.header("Financial Document Classifier")
    st.caption("All 5 responsible AI controls active on every classification.")

    col1, col2 = st.columns([1, 1])
    with col1:
        input_mode = st.radio("Input", ["Use sample document", "Paste your own"])

    doc_text = ""
    doc_name = ""

    if input_mode == "Use sample document":
        selected = st.selectbox("Select sample", list(SAMPLE_DOCUMENTS.keys()))
        doc_text = SAMPLE_DOCUMENTS[selected]
        doc_name = selected
        st.text_area("Preview", doc_text[:400] + "...", height=180, disabled=True)
    else:
        doc_name = st.text_input("Document name", "custom_document")
        doc_text = st.text_area("Paste document text", height=250)

    threshold = st.slider("Confidence gate threshold", 0.5, 1.0, 0.85, 0.05)

    if st.button("Classify with All 5 Controls", type="primary"):
        if not doc_text.strip():
            st.error("Please provide a document.")
        else:
            with st.spinner("Classifying with structured reasoning..."):
                try:
                    from rai_finserv import ConfidenceGate as CG
                    import examples.classifier_pipeline as cp
                    cp.gate = CG(threshold=threshold)
                    result = classify_document(doc_text, doc_name)
                    st.session_state.last_result = result
                except Exception as e:
                    st.error(f"Error: {e}")
                    st.info("Check that ANTHROPIC_API_KEY is set in .env")

    if "last_result" in st.session_state:
        r = st.session_state.last_result
        st.divider()

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Label", r["label"])
        m2.metric("Confidence", f"{r['confidence']:.0%}")
        m3.metric("Gate", r["gate_outcome"])
        m4.metric("HITL Required", "Yes" if r["requires_hitl"] else "No")

        if r["requires_hitl"]:
            st.warning(f"Routed to HITL queue (item #{r['hitl_item_id']}) — confidence below threshold")
        else:
            st.success(f"Auto-routed to: {r['routing']}")

        with st.expander("Reasoning Chain (ExplainabilityWrapper)", expanded=True):
            st.markdown("**Factors supporting this classification:**")
            for f in r["reasoning"]["factors_considered"]:
                st.markdown(f"- {f}")
            st.markdown(f"**Key evidence:** {r['reasoning']['key_evidence']}")
            if r["reasoning"]["factors_against"]:
                st.markdown("**Factors against / uncertainty:**")
                for f in r["reasoning"]["factors_against"]:
                    st.markdown(f"- {f}")
            st.markdown(f"**Confidence rationale:** {r['reasoning']['confidence_rationale']}")

        st.caption(f"Audit trail entry: #{r['audit_entry_id']}")

# ── Tab 2: HITL Queue ─────────────────────────────────────────────────────────
with tab2:
    st.header("HITL Review Queue")
    st.caption("Items the ConfidenceGate blocked — require analyst decision before routing.")

    pending = queue.get_pending(PIPELINE_ID)
    stats = queue.get_stats(PIPELINE_ID)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pending", stats["pending"])
    c2.metric("Confirmed", stats["confirmed"])
    c3.metric("Overridden", stats["overridden"])
    c4.metric("Escalated", stats["escalated"])

    if not pending:
        st.info("No items pending review.")
    else:
        for item in pending:
            with st.expander(
                f"#{item.item_id} — AI said: {item.ai_output} ({item.confidence:.0%}) | {item.context.get('document_name', '')}",
                expanded=True,
            ):
                st.markdown(f"**Reason blocked:** {item.reason}")
                if item.context.get("key_evidence"):
                    st.markdown(f"**Key evidence:** {item.context['key_evidence']}")
                if item.context.get("factors_against"):
                    st.markdown("**Uncertainty factors:**")
                    for f in item.context.get("factors_against", []):
                        st.markdown(f"- {f}")

                col1, col2 = st.columns([2, 1])
                with col1:
                    decision = st.selectbox(
                        "Your decision",
                        ["confirmed", "overridden", "escalated"],
                        key=f"dec_{item.item_id}",
                    )
                    override_label = None
                    if decision == "overridden":
                        override_label = st.selectbox(
                            "Override to", DOCUMENT_LABELS, key=f"ovr_{item.item_id}"
                        )
                    notes = st.text_input("Notes (required for override)", key=f"notes_{item.item_id}")
                with col2:
                    reviewer_id = st.text_input("Your analyst ID", value="analyst_1", key=f"rid_{item.item_id}")
                    if st.button("Submit Review", key=f"submit_{item.item_id}"):
                        if decision == "overridden" and not notes.strip():
                            st.error("Notes are required when overriding.")
                        else:
                            queue.review(item.item_id, reviewer_id, decision, notes)
                            audit.log_human_review(item.audit_entry_id, reviewer_id, decision, notes)
                            st.success("Review logged.")
                            st.rerun()

# ── Tab 3: Audit Trail ────────────────────────────────────────────────────────
with tab3:
    st.header("Audit Trail (AuditChain)")
    st.caption("Append-only log of every AI decision and human review. Exportable for regulatory submission.")

    stats = audit.get_stats(PIPELINE_ID)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Decisions", stats["total_decisions"])
    c2.metric("Avg Confidence", f"{stats['avg_confidence']:.0%}" if stats["avg_confidence"] else "N/A")
    c3.metric("Gate Blocks", stats["blocked_by_gate"])
    c4.metric("Override Rate", f"{stats['override_rate']:.0%}" if stats["override_rate"] else "N/A")

    history = audit.get_pipeline_history(PIPELINE_ID, limit=50)
    if not history:
        st.info("No audit entries yet. Classify some documents first.")
    else:
        import pandas as pd
        rows = [
            {
                "entry_id": e.entry_id,
                "timestamp": e.timestamp_utc[:19],
                "output": e.output,
                "confidence": f"{e.confidence:.0%}",
                "gate": e.gate_outcome,
                "human_decision": e.human_decision or "—",
                "reviewer": e.human_review_id or "—",
            }
            for e in history
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        if st.button("Export CSV"):
            audit.export_csv("audit_export.csv")
            st.success("Exported to audit_export.csv")

# ── Tab 4: Drift Monitor ──────────────────────────────────────────────────────
with tab4:
    st.header("Drift Monitor")
    st.caption("Output distribution and confidence tracked over time. Alerts on behavioural shift.")

    window = st.slider("Window (days)", 1, 14, 7)
    baseline = st.slider("Baseline (days)", 7, 60, 30)

    report = monitor.check_drift(window_days=window, baseline_days=baseline)

    if report.alert:
        st.error(f"⚠ DRIFT DETECTED — {len(report.alerts)} alert(s)")
        for a in report.alerts:
            st.markdown(f"- {a}")
    else:
        st.success("✓ No significant drift detected")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Window observations", report.window_count)
        st.markdown("**Window label distribution:**")
        for label, pct in report.label_distribution_window.items():
            st.markdown(f"- {label}: {pct:.1%}")
    with col2:
        st.metric("Baseline observations", report.baseline_count)
        st.markdown("**Baseline label distribution:**")
        for label, pct in report.label_distribution_baseline.items():
            st.markdown(f"- {label}: {pct:.1%}")

    if report.avg_confidence_window and report.avg_confidence_baseline:
        m1, m2 = st.columns(2)
        m1.metric("Window avg confidence", f"{report.avg_confidence_window:.0%}")
        m2.metric("Baseline avg confidence", f"{report.avg_confidence_baseline:.0%}",
                  delta=f"{report.avg_confidence_window - report.avg_confidence_baseline:+.1%}")

# ── Tab 5: PM Guide ───────────────────────────────────────────────────────────
with tab5:
    st.header("PM Guide to Responsible AI")
    guide_path = Path(__file__).parent / "docs" / "pm-guide-responsible-ai.md"
    if guide_path.exists():
        st.markdown(guide_path.read_text(encoding="utf-8"))
    else:
        st.info("Guide not found. Check docs/pm-guide-responsible-ai.md")
