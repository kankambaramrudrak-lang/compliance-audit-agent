"""Deterministic demo data for the local compliance audit prototype."""

from __future__ import annotations

from datetime import date, timedelta


ORGANIZATION = "Acme Technologies"
ORGANIZATION_ID = "acme-technologies"
BANK_ID = "compliance-audit"

CONTROLS = [
    {
        "id": "IAM-04",
        "name": "Privileged access review",
        "domain": "Identity & access",
        "requirement": "Privileged accounts must be reviewed quarterly, with reviewer approval and evidence of remediation.",
        "evidence": "Q3 access review.xlsx lists 18 privileged accounts. The IT director approved it on 2026-09-12; two stale accounts were disabled, with tickets IAM-882 and IAM-883 attached.",
        "outcome": "Compliant",
        "explanation": "The quarterly review is approved, covers all privileged accounts, and includes evidence that identified stale access was removed.",
        "owner": "Priya Shah",
        "days": 12,
    },
    {
        "id": "IR-02",
        "name": "Incident response exercises",
        "domain": "Security operations",
        "requirement": "The incident response plan must be exercised at least annually and resulting actions tracked to closure.",
        "evidence": "A tabletop exercise was held on 2026-08-20. The report lists three follow-up actions; two remain open and have no target dates.",
        "outcome": "Non-compliant",
        "explanation": "An exercise occurred, but two resulting actions remain open without target dates, so the evidence does not demonstrate follow-through to closure.",
        "owner": "Jordan Lee",
        "days": 21,
        "previous_finding": True,
    },
    {
        "id": "TPRM-07",
        "name": "Critical vendor assurance",
        "domain": "Third-party risk",
        "requirement": "Current security assurance must be obtained for every critical vendor and reviewed annually.",
        "evidence": "The vendor register identifies CloudNorth as critical. A SOC 2 report is referenced, but the report itself and review sign-off were not provided.",
        "outcome": "Insufficient Evidence",
        "explanation": "The register identifies a critical vendor, but the current assurance report and evidence of review are missing.",
        "owner": "Elena Ruiz",
        "days": 30,
    },
    {
        "id": "CRYPTO-03",
        "name": "Encryption of stored data",
        "domain": "Data protection",
        "requirement": "Production databases containing sensitive data must use approved encryption at rest.",
        "evidence": "Cloud configuration export dated 2026-09-15 shows AES-256 encryption enabled for all six production databases. The security baseline is attached.",
        "outcome": "Compliant",
        "explanation": "The configuration export covers all production databases and shows the approved encryption setting enabled.",
        "owner": "Morgan Chen",
        "days": 14,
    },
    {
        "id": "BCP-05",
        "name": "Business continuity test",
        "domain": "Resilience",
        "requirement": "Recovery procedures must be tested annually and actual recovery times recorded against objectives.",
        "evidence": "A recovery test was marked complete in the continuity tracker, but no test report or recovery-time results were attached.",
        "outcome": "Insufficient Evidence",
        "explanation": "The tracker records a completed test, but without a report or recorded recovery times it cannot show that recovery objectives were met.",
        "owner": "Sam Patel",
        "days": 30,
    },
]


def prior_audit_record(today: date | None = None) -> dict:
    """Return the fixed first-audit finding/action used in the memory demo."""
    today = today or date.today()
    audit_date = today - timedelta(days=180)
    return {
        "audit_id": "AUD-2026-014",
        "date": audit_date.isoformat(),
        "control_id": "IR-02",
        "control_name": "Incident response exercises",
        "requirement": CONTROLS[1]["requirement"],
        "status": "Non-compliant",
        "finding": "The annual incident response exercise produced three actions; two remained open without target dates.",
        "action": "Assign owners and target dates to the two open incident response exercise actions, then track both through closure.",
        "owner": "Jordan Lee",
        "deadline": (today - timedelta(days=120)).isoformat(),
        "action_status": "In progress",
    }

