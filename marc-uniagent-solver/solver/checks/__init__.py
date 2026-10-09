"""Deterministic rule checks: pure functions CaseFacts -> list[Finding], one module per case type."""

from solver.checks import business_trip, expense, procurement
from solver.checks.common import FAIL, Finding, UNCLEAR
from solver.schemas import CaseFacts

CHECKS_BY_CASE_TYPE = {
    "business_trip": business_trip.CHECKS,
    "expense": expense.CHECKS,
    "procurement": procurement.CHECKS,
}


def run_checks(facts: CaseFacts) -> list[Finding]:
    findings = []
    for check in CHECKS_BY_CASE_TYPE.get(facts.case_type, ()):
        try:
            findings.extend(check(facts))
        except Exception as error:  # a check bug must not decide a case
            findings.append(Finding(check.__name__, UNCLEAR, f"Prüfung fehlgeschlagen: {error}", [], False))
    return findings


def hard_failures(findings: list[Finding]) -> list[Finding]:
    return [finding for finding in findings if finding.status == FAIL and finding.hard]
