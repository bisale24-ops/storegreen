# SPDX-License-Identifier: MIT
"""
tests/test_runner.py — unit tests for the Runner and end-to-end pipeline.
"""

import os
import tempfile
import textwrap
import zipfile

import pytest

from storegreen.runner import Runner, ScanReport
from storegreen.rules.base import Finding, NotApplicable, Passed, Undecided
from storegreen.rules.smoke import SmokeRule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo(tmp: str, name: str = "app") -> str:
    """Create a minimal Android repo and return its path."""
    module_dir = os.path.join(tmp, name)
    os.makedirs(os.path.join(module_dir, "src", "main"), exist_ok=True)
    with open(os.path.join(module_dir, "build.gradle"), "w") as f:
        f.write(textwrap.dedent("""\
            plugins { id 'com.android.application' }
            android {
                defaultConfig {
                    applicationId "com.example.app"
                    targetSdk 34
                    versionCode 1
                }
            }
        """))
    with open(os.path.join(module_dir, "src", "main", "AndroidManifest.xml"), "w") as f:
        f.write(textwrap.dedent("""\
            <?xml version="1.0" encoding="utf-8"?>
            <manifest xmlns:android="http://schemas.android.com/apk/res/android"
                package="com.example.app">
                <uses-sdk android:targetSdkVersion="34" />
                <application />
            </manifest>
        """))
    return tmp


def _make_aab(tmp: str) -> str:
    path = os.path.join(tmp, "test.aab")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("base/manifest/AndroidManifest.xml", b"\x0a\x00manifest")
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRunnerSourceOnly:

    def test_source_only_returns_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            runner = Runner()
            report = runner.scan(repo_root=repo)
            assert isinstance(report, ScanReport)
            assert report.repo_root == os.path.abspath(repo)
            assert report.aab_path is None

    def test_source_only_smoke_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            runner = Runner()
            report = runner.scan(repo_root=repo)
            passed_ids = [p.rule for p in report.passed]
            assert "SMOKE-01" in passed_ids

    def test_no_block_findings_on_valid_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            runner = Runner()
            report = runner.scan(repo_root=repo)
            assert not report.has_block

    def test_exit_code_0_for_no_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            runner = Runner()
            report = runner.scan(repo_root=repo)
            assert report.has_block is False


class TestRunnerBundleOnly:

    def test_bundle_only_returns_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            aab = _make_aab(tmp)
            runner = Runner()
            report = runner.scan(aab_path=aab)
            assert isinstance(report, ScanReport)
            assert report.repo_root is None
            assert report.aab_path == os.path.abspath(aab)

    def test_bundle_only_smoke_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            aab = _make_aab(tmp)
            runner = Runner()
            report = runner.scan(aab_path=aab)
            passed_ids = [p.rule for p in report.passed]
            assert "SMOKE-01" in passed_ids


class TestRunnerBoth:

    def test_source_and_bundle_both_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            aab = _make_aab(tmp)
            runner = Runner()
            report = runner.scan(repo_root=repo, aab_path=aab)
            # SMOKE-01 should have decided_from="both" since both modes ran
            smoke_passed = [p for p in report.passed if p.rule == "SMOKE-01"]
            assert len(smoke_passed) == 1
            assert smoke_passed[0].decided_from == "both"


class TestRunnerOnly:

    def test_only_filter_limits_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            runner = Runner(only=["SMOKE"])
            report = runner.scan(repo_root=repo)
            # Only SMOKE-01 should appear
            all_rule_ids = (
                [f.rule for f in report.findings]
                + [u.rule for u in report.undecided]
                + [p.rule for p in report.passed]
                + [n.rule for n in report.not_applicable]
            )
            assert all(r.startswith("SMOKE") for r in all_rule_ids)


class TestScanReportSummary:

    def test_summary_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            runner = Runner()
            report = runner.scan(repo_root=repo)
            s = report.summary
            assert "block" in s
            assert "risk" in s
            assert "warn" in s
            assert "undecidable" in s
            assert "passed" in s
            assert s["block"] == 0

    def test_elapsed_seconds_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            runner = Runner()
            report = runner.scan(repo_root=repo)
            assert report.elapsed_seconds >= 0.0
