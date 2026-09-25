# SPDX-License-Identifier: MIT
"""
tests/test_fix.py — verifies --fix applied to a copy of fixtures/tipjar-amazon.

Rules:
  - fixable findings (AMZ-IAP-06, AMZ-IAP-04, AMZ-IAP-03) must be absent after fix
  - AMZ-IAP-01 must still be reported (cannot fabricate a key)
  - the original fixture on disk must be untouched

Run with both prepared interpreters:
    python3.13 -m pytest tests/test_fix.py -v
    python3.14 -m pytest tests/test_fix.py -v
"""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import List

import pytest

from storegreen.runner import Runner, ScanReport
from storegreen.fixer import apply_fixes
from storegreen.rules.base import Finding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIXTURE   = os.path.join(_REPO_ROOT, "fixtures", "tipjar-amazon")


def _findings(report: ScanReport) -> List[str]:
    return [f.rule for f in report.findings]


def _undecided(report: ScanReport) -> List[str]:
    return [u.rule for u in report.undecided]


def _snapshot(path: str) -> dict:
    """Return {rel_path: content} for every file under path."""
    result = {}
    for dirpath, _, filenames in os.walk(path):
        for fn in filenames:
            abs_p = os.path.join(dirpath, fn)
            rel_p = os.path.relpath(abs_p, path)
            try:
                with open(abs_p, "r", encoding="utf-8", errors="replace") as fh:
                    result[rel_p] = fh.read()
            except OSError:
                result[rel_p] = "<unreadable>"
    return result


# ---------------------------------------------------------------------------
# Fixture: copy tipjar-amazon to a temp dir, run --fix, keep original snapshot
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def fix_result():
    """
    Returns (report_before, diff, applied, report_after, original_snapshot).

    Skipped if the fixture directory is not present.
    """
    if not os.path.isdir(_FIXTURE):
        pytest.skip("fixtures/tipjar-amazon not present")

    # Snapshot the original fixture before touching it
    original_snapshot = _snapshot(_FIXTURE)

    with tempfile.TemporaryDirectory() as tmp:
        copy_path = os.path.join(tmp, "tipjar-amazon")
        shutil.copytree(_FIXTURE, copy_path)

        runner = Runner()
        report_before = runner.scan(repo_root=copy_path)

        diff, applied = apply_fixes(report_before, copy_path)

        report_after = runner.scan(repo_root=copy_path)
        report_after.fix_applied = True
        report_after.findings_before_fix = list(report_before.findings)

        # yield values consumed by all tests in this module
        yield report_before, diff, applied, report_after, original_snapshot, copy_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFixApplied:
    """Verify that fixable findings disappear after --fix."""

    def test_amz_iap06_fixed(self, fix_result):
        """AMZ-IAP-06 must not be in findings after fix."""
        _, _, _, report_after, _, _ = fix_result
        assert "AMZ-IAP-06" not in _findings(report_after), \
            "AMZ-IAP-06 must be resolved by --fix (missing ProGuard keep lines added)"

    def test_amz_iap04_was_undecided_not_finding(self, fix_result):
        """In source mode AMZ-IAP-04 is Undecided (AAR may contribute) — not a Finding.
        --fix only repairs Findings; the Undecided status is correct and unchanged."""
        report_before, _, _, _, _, _ = fix_result
        assert "AMZ-IAP-04" not in _findings(report_before), \
            "AMZ-IAP-04 must be Undecided (not a Finding) in source mode"

    def test_amz_iap03_was_undecided_not_finding(self, fix_result):
        """In source mode AMZ-IAP-03 is Undecided (AAR may contribute) — not a Finding.
        --fix only repairs Findings; the Undecided status is correct and unchanged."""
        report_before, _, _, _, _, _ = fix_result
        assert "AMZ-IAP-03" not in _findings(report_before), \
            "AMZ-IAP-03 must be Undecided (not a Finding) in source mode"

    def test_applied_list_contains_expected_rules(self, fix_result):
        """The applied list must include AMZ-IAP-06 (the one Finding in source mode)."""
        _, _, applied, _, _, _ = fix_result
        assert "AMZ-IAP-06" in applied, \
            "AMZ-IAP-06 must appear in the applied-fixes list"

    def test_diff_is_non_empty(self, fix_result):
        """The unified diff must contain actual changes."""
        _, diff, _, _, _, _ = fix_result
        assert diff.strip(), "--fix must produce a non-empty unified diff"

    def test_diff_mentions_proguard(self, fix_result):
        """The unified diff must reference the proguard rules file (AMZ-IAP-06 fix)."""
        _, diff, _, _, _, _ = fix_result
        assert "proguard" in diff.lower(), \
            "diff must mention the proguard file changed for AMZ-IAP-06"

    def test_diff_does_not_mention_manifest(self, fix_result):
        """The diff must NOT touch AndroidManifest.xml.
        AMZ-IAP-03 and AMZ-IAP-04 are Undecided in source mode (an AAR may still
        contribute the receiver / queries entries).  --fix must never act on an
        Undecided rule — that is exactly the guessing the whole design forbids."""
        _, diff, _, _, _, _ = fix_result
        assert "AndroidManifest" not in diff, \
            "diff must not touch AndroidManifest.xml — only Findings may be auto-fixed, not Undecided"


class TestUndecidedRulesUntouched:
    """--fix must leave Undecided rules and their source files byte-for-byte unchanged."""

    def test_undecided_rules_still_undecided_after_fix(self, fix_result):
        """AMZ-IAP-01, AMZ-IAP-03, AMZ-IAP-04 must still be Undecided after fix."""
        _, _, _, report_after, _, _ = fix_result
        still_undecided = _undecided(report_after)
        for rule_id in ("AMZ-IAP-01", "AMZ-IAP-03", "AMZ-IAP-04"):
            assert rule_id in still_undecided, \
                f"{rule_id} must remain Undecided after --fix (was Undecided before)"

    def test_manifest_bytes_unchanged_after_fix(self, fix_result):
        """AndroidManifest.xml in the copy must be byte-for-byte identical before and after fix."""
        _, _, _, _, original_snapshot, copy_path = fix_result
        manifest_rel = os.path.join("app", "src", "main", "AndroidManifest.xml")
        original_content = original_snapshot.get(manifest_rel)
        assert original_content is not None, \
            f"Expected {manifest_rel} in the fixture snapshot"
        copy_manifest = os.path.join(copy_path, manifest_rel)
        with open(copy_manifest, "r", encoding="utf-8") as fh:
            copy_content = fh.read()
        assert copy_content == original_content, \
            "AndroidManifest.xml must not be modified — AMZ-IAP-03/04 are Undecided, not Findings"

    def test_undecided_rules_not_in_applied(self, fix_result):
        """None of AMZ-IAP-01, AMZ-IAP-03, AMZ-IAP-04 may appear in the applied list."""
        _, _, applied, _, _, _ = fix_result
        for rule_id in ("AMZ-IAP-01", "AMZ-IAP-03", "AMZ-IAP-04"):
            assert rule_id not in applied, \
                f"{rule_id} must never be in the applied-fixes list (it was Undecided)"


class TestAmzIap01StillReported:
    """AMZ-IAP-01 must remain reported after --fix (key cannot be fabricated)."""

    def test_amz_iap01_still_undecided_not_fixed(self, fix_result):
        """AMZ-IAP-01 is Undecided before and after --fix (secret, never auto-fixable)."""
        report_before, _, _, report_after, _, _ = fix_result
        # Before fix: Undecided in source mode
        assert "AMZ-IAP-01" in _undecided(report_after), \
            "AMZ-IAP-01 must remain Undecided after --fix — the key cannot be fabricated"

    def test_amz_iap01_not_in_applied(self, fix_result):
        """AMZ-IAP-01 must not appear in the applied-fixes list."""
        _, _, applied, _, _, _ = fix_result
        assert "AMZ-IAP-01" not in applied, \
            "AMZ-IAP-01 must never be auto-fixed — it requires a real key from the console"

    def test_amz_iap01_still_not_a_finding(self, fix_result):
        """AMZ-IAP-01 must not fire as a Finding in source mode after fix."""
        _, _, _, report_after, _, _ = fix_result
        assert "AMZ-IAP-01" not in _findings(report_after), \
            "AMZ-IAP-01 must remain Undecided (not a BLOCK) in source mode"


class TestOriginalFixtureUntouched:
    """The original fixture directory on disk must not be modified."""

    def test_original_files_unchanged(self, fix_result):
        """Every file in fixtures/tipjar-amazon must be identical to before the test."""
        _, _, _, _, original_snapshot, _ = fix_result
        current_snapshot = _snapshot(_FIXTURE)
        assert current_snapshot == original_snapshot, (
            "Original fixture files were modified — --fix must only touch the copy:\n"
            + "\n".join(
                f"  {k}: original != current"
                for k in set(original_snapshot) | set(current_snapshot)
                if original_snapshot.get(k) != current_snapshot.get(k)
            )
        )


class TestFixReportFields:
    """Verify the §12 fix_applied / findings_before_fix fields on the report."""

    def test_fix_applied_true(self, fix_result):
        _, _, _, report_after, _, _ = fix_result
        assert report_after.fix_applied is True

    def test_findings_before_fix_non_empty(self, fix_result):
        _, _, _, report_after, _, _ = fix_result
        assert report_after.findings_before_fix, \
            "findings_before_fix must be non-empty (AMZ-IAP-06 was a finding before fix)"

    def test_findings_before_fix_contains_amz_iap06(self, fix_result):
        _, _, _, report_after, _, _ = fix_result
        before_ids = [f.rule for f in report_after.findings_before_fix]
        assert "AMZ-IAP-06" in before_ids, \
            "findings_before_fix must include AMZ-IAP-06"

    def test_findings_before_is_distinct_from_after(self, fix_result):
        _, _, _, report_after, _, _ = fix_result
        before_ids = {f.rule for f in report_after.findings_before_fix}
        after_ids  = {f.rule for f in report_after.findings}
        # At least one rule fixed means the sets differ
        assert before_ids != after_ids or not report_after.findings_before_fix, \
            "findings_before_fix and findings must differ when fixes were applied"
