"""Sample financial documents for the classifier demo."""

SAMPLE_DOCUMENTS = {
    "Regulatory Filing — Capital Requirements": """
PILLAR 3 DISCLOSURE — Q3 2024
Deutsche Bank AG | Capital and Risk Management

In accordance with Regulation (EU) No 575/2013 (CRR) and the EBA Guidelines on
disclosure requirements under Part Eight of Regulation (EU) No 575/2013, we present
our Q3 2024 Pillar 3 disclosures.

Common Equity Tier 1 (CET1) ratio: 13.8% (Q2 2024: 13.6%)
Total Capital Ratio: 17.2%
Leverage Ratio: 4.4%
Risk-Weighted Assets: €342.1bn

Minimum Capital Requirements:
Our CET1 requirement including buffers stands at 10.7%, comprising:
- Pillar 1 minimum: 4.5%
- Capital Conservation Buffer: 2.5%
- G-SIB surcharge: 2.0%
- Combined buffer: 1.7%

Internal capital adequacy assessment (ICAAP) confirms capital adequacy
under base and stress scenarios as approved by the Management Board.
""",

    "Earnings Release — Q3 Results": """
BARCLAYS PLC — Q3 2024 RESULTS

Group Income: £6.3bn (+8% YoY)
Group Pre-tax Profit: £1.9bn (+22% YoY)
Return on Tangible Equity: 12.1%

Barclays UK
- Net Interest Income: £1.8bn
- NIM: 3.12% (Q3 2023: 2.94%)
- Mortgage balances: £152bn
- Credit card balances: £11.2bn (arrears rate: 1.6%)

Barclays Investment Bank
- Total income: £2.9bn
- Equities income: £0.8bn (+15% YoY driven by derivatives and prime services)
- FICC income: £0.9bn
- Banking fees: £0.6bn

Full year 2024 guidance reiterated: RoTE >12%, CIR <63%.

"Strong performance across both retail and investment banking businesses,
with NIM expansion benefiting from higher-for-longer rate environment."
— C.S. Venkatakrishnan, Group Chief Executive
""",

    "Market Commentary — FX Strategy": """
FX WEEKLY — STERLING OUTLOOK
Macro Strategy | HSBC Global Research | 18 November 2024

GBPUSD: Target 1.27 (3-month), 1.31 (12-month)

Sterling underperformed significantly this week following the Autumn Budget.
The OBR's upward revision to the medium-term deficit has reawakened fiscal
sustainability concerns among overseas investors. With UK 10-year Gilt yields
now trading at their widest spread vs Bunds since the LDI crisis (Oct 2022),
the risk of a disorderly Gilt sell-off constraining BoE flexibility has increased.

Key risks to our view:
UPSIDE: Faster BoE rate cuts → lower carry bleed on short GBP positions
DOWNSIDE: Labour supply shock from minimum wage + NI increases → stagflation risk

Positioning: We move to short GBPUSD at 1.2950, stop 1.3100, target 1.2700.
This is a tactical position sized at 2% of notional, within policy limits.

Note: This commentary is for informational purposes and does not constitute
investment advice. Please refer to HSBC's full disclosure statement.
""",

    "Risk Report — Model Risk": """
MODEL RISK COMMITTEE — QUARTERLY REPORT
Q3 2024 | Model Risk Management

EXECUTIVE SUMMARY
Total approved models in inventory: 847 (Q2: 831)
Models requiring re-validation: 23 (Q2: 31)
Overdue validations: 4 (RED — escalated to CRO)

HIGH RISK FINDINGS THIS QUARTER

1. Credit Scoring Model — CS_RETAIL_v4.1
   Issue: PSI breach on income feature (PSI=0.28, threshold=0.20)
   Action: Model placed on enhanced monitoring. Recalibration in progress.
   Owner: Credit Risk Analytics | ETA: Q4 2024

2. Market Risk VaR Model — MR_IB_v2.3
   Issue: Back-testing exceptions exceed SR 11-7 red zone threshold (12 exceptions, limit 10)
   Action: Model suspended for regulatory capital calculation pending re-validation.
   Escalated: CRO, CFO | Status: Critical

3. AML Transaction Monitoring — FCRM_v6.0
   Issue: False positive rate increased from 94% to 97% following Q3 rules update
   Action: Rules tuning in progress. FCA notified per SYSC 6.3.

GOVERNANCE
Model Risk Appetite: Within tolerance (4 high-risk findings, appetite 5)
Next MRC: 15 January 2025
""",

    "Ambiguous — Internal Memo": """
TO: Data Science Team
FROM: Risk Technology Group
RE: Model Deployment Update

Following last week's discussion, we wanted to confirm the deployment schedule
for the three models discussed. The credit team has signed off on the revised
performance metrics and we're good to proceed.

The compliance team has asked for an additional two weeks to review the governance
documents before we go live. Given the timing, we'll target mid-December.

Please ensure the monitoring dashboards are ready before deployment.
Regards, Risk Technology
""",
}

DOCUMENT_LABELS = [
    "REGULATORY_FILING",
    "EARNINGS_RELEASE",
    "MARKET_COMMENTARY",
    "RISK_REPORT",
    "OTHER",
]
