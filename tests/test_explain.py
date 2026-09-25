# SPDX-License-Identifier: MIT
"""
tests/test_explain.py — verifies --explain-rejection against the real CrewSheet
rejection e-mail (prep/fixtures/amazon-rejection-crewsheet.txt) scanned against
fixtures/tipjar-amazon.aab (bundle mode, so AMZ-IAP-01/03/04 all fire as BLOCK).

Run with both prepared interpreters:
    ~/.venvs/py39/bin/python  -m pytest tests/test_explain.py -v
    ~/.venvs/py313/bin/python -m pytest tests/test_explain.py -v
"""

from __future__ import annotations

import os

import pytest

from storegreen.runner import Runner
from storegreen.explainer import explain

_REPO_ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EMAIL      = os.path.join(_REPO_ROOT, "prep", "fixtures", "amazon-rejection-crewsheet.txt")
_AAB        = os.path.join(_REPO_ROOT, "fixtures", "tipjar-amazon.aab")


@pytest.fixture(scope="module")
def explain_result():
    if not os.path.isfile(_EMAIL):
        pytest.skip("prep/fixtures/amazon-rejection-crewsheet.txt not present")
    if not os.path.isfile(_AAB):
        pytest.skip("fixtures/tipjar-amazon.aab not present")
    report = Runner().scan(aab_path=_AAB)
    return explain(_EMAIL, report), report


class TestExplainRejection:

    def test_has_matched_symptoms(self, explain_result):
        """The e-mail must map to at least one symptom group."""
        result, _ = explain_result
        assert result.matched_symptoms, \
            "Expected at least one symptom match from the CrewSheet rejection e-mail"

    def test_iap_symptom_present(self, explain_result):
        """The IAP-displays-error symptom must be among the matched groups."""
        result, _ = explain_result
        labels = [m.symptom_label for m in result.matched_symptoms]
        assert any("IAP" in (l or "") or "iap" in (l or "").lower() for l in labels), \
            f"Expected an IAP-related symptom; got: {labels}"

    def test_violated_rules_are_bundle_findings(self, explain_result):
        """Every rule listed as 'violated here' must actually be a Finding in the report."""
        result, report = explain_result
        finding_ids = {f.rule for f in report.findings}
        for mapping in result.matched_symptoms:
            for rule_id in mapping.violated:
                assert rule_id in finding_ids, \
                    f"{rule_id} listed as violated but not in report.findings"

    def test_amz_iap01_in_violated(self, explain_result):
        """AMZ-IAP-01 fires as BLOCK in bundle mode and must appear as violated."""
        result, report = explain_result
        # Confirm the scan actually found it
        finding_ids = {f.rule for f in report.findings}
        assert "AMZ-IAP-01" in finding_ids, \
            "Precondition: AMZ-IAP-01 must be a finding in bundle mode"
        all_violated = {r for m in result.matched_symptoms for r in m.violated}
        assert "AMZ-IAP-01" in all_violated, \
            "AMZ-IAP-01 is a bundle finding and must appear in violated"

    def test_amz_iap03_in_violated(self, explain_result):
        """AMZ-IAP-03 fires as BLOCK in bundle mode and must appear as violated."""
        result, report = explain_result
        finding_ids = {f.rule for f in report.findings}
        assert "AMZ-IAP-03" in finding_ids, \
            "Precondition: AMZ-IAP-03 must be a finding in bundle mode"
        all_violated = {r for m in result.matched_symptoms for r in m.violated}
        assert "AMZ-IAP-03" in all_violated, \
            "AMZ-IAP-03 is a bundle finding and must appear in violated"

    def test_amz_iap04_in_violated(self, explain_result):
        """AMZ-IAP-04 fires as BLOCK in bundle mode and must appear as violated."""
        result, report = explain_result
        finding_ids = {f.rule for f in report.findings}
        assert "AMZ-IAP-04" in finding_ids, \
            "Precondition: AMZ-IAP-04 must be a finding in bundle mode"
        all_violated = {r for m in result.matched_symptoms for r in m.violated}
        assert "AMZ-IAP-04" in all_violated, \
            "AMZ-IAP-04 is a bundle finding and must appear in violated"

    def test_no_single_cause_claimed(self, explain_result):
        """Violated list must contain multiple rules — we never claim one single cause."""
        result, _ = explain_result
        for mapping in result.matched_symptoms:
            if mapping.violated:
                assert len(mapping.violated) >= 2, (
                    f"Symptom '{mapping.symptom_label}' claims only one cause "
                    f"({mapping.violated[0]}); the e-mail evidence supports several"
                )

    def test_unmapped_sentences_are_strings(self, explain_result):
        """Unmapped sentences must be non-empty strings (the boilerplate lines)."""
        result, _ = explain_result
        # The e-mail has headers, steps-to-reproduce, and sign-off that map to nothing
        assert result.unmapped_sentences, \
            "Expected some boilerplate sentences to be unmapped"
        for s in result.unmapped_sentences:
            assert isinstance(s, str) and s.strip()

    def test_clean_rules_are_not_findings(self, explain_result):
        """Every rule listed as 'clean here' must NOT be in report.findings."""
        result, report = explain_result
        finding_ids = {f.rule for f in report.findings}
        for mapping in result.matched_symptoms:
            for rule_id in mapping.clean:
                assert rule_id not in finding_ids, \
                    f"{rule_id} listed as clean but is in report.findings"

    def test_email_file_recorded(self, explain_result):
        """The email_file field must be set to an absolute path ending in .txt."""
        result, _ = explain_result
        assert result.email_file.endswith(".txt"), \
            "email_file must point to the .txt rejection e-mail"
        assert os.path.isabs(result.email_file), \
            "email_file must be an absolute path"
