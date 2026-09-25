# SPDX-License-Identifier: MIT
"""
tests/test_report.py — unit tests for report/schema.py and report/json_report.py
"""

import json
import os
import tempfile
import textwrap
import zipfile

import pytest

from storegreen.runner import Runner, ScanReport
from storegreen.report.schema import to_dict
from storegreen.report.json_report import to_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo(tmp: str) -> str:
    module_dir = os.path.join(tmp, "app")
    os.makedirs(os.path.join(module_dir, "src", "main"), exist_ok=True)
    with open(os.path.join(module_dir, "build.gradle"), "w") as f:
        f.write(textwrap.dedent("""\
            plugins { id 'com.android.application' }
            android {
                defaultConfig {
                    applicationId "com.example.app"
                    targetSdk 34
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


# ---------------------------------------------------------------------------
# schema.to_dict
# ---------------------------------------------------------------------------

class TestToDict:

    def test_all_top_level_keys_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            runner = Runner()
            report = runner.scan(repo_root=repo)
            d = to_dict(report)
            for key in ("tool", "version", "scanned", "summary", "findings",
                        "undecided", "passed", "not_applicable", "not_implemented"):
                assert key in d, f"Missing key: {key}"

    def test_tool_and_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            runner = Runner()
            report = runner.scan(repo_root=repo)
            d = to_dict(report)
            assert d["tool"] == "storegreen"
            assert d["version"] == "0.1.0"

    def test_lists_always_present_even_when_empty(self):
        """All four lists must be present even when nothing was found."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            runner = Runner()
            report = runner.scan(repo_root=repo)
            d = to_dict(report)
            assert isinstance(d["findings"], list)
            assert isinstance(d["undecided"], list)
            assert isinstance(d["passed"], list)
            assert isinstance(d["not_applicable"], list)
            assert isinstance(d["not_implemented"], list)

    def test_summary_has_seconds(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            runner = Runner()
            report = runner.scan(repo_root=repo)
            d = to_dict(report)
            assert "seconds" in d["summary"]
            assert isinstance(d["summary"]["seconds"], float)

    def test_undecided_evidence_always_has_file(self):
        """Spec: undecided[].evidence always has a file."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            runner = Runner()
            report = runner.scan(repo_root=repo)
            d = to_dict(report)
            for u in d["undecided"]:
                assert u["evidence"] is not None
                assert "file" in u["evidence"]
                assert u["evidence"]["file"]  # not empty

    def test_scanned_has_repo_and_aab(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            runner = Runner()
            report = runner.scan(repo_root=repo)
            d = to_dict(report)
            assert "repo" in d["scanned"]
            assert "aab" in d["scanned"]
            assert d["scanned"]["aab"] is None

    def test_form_factors_is_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            runner = Runner()
            report = runner.scan(repo_root=repo)
            d = to_dict(report)
            assert isinstance(d["scanned"]["form_factors"], list)


# ---------------------------------------------------------------------------
# json_report.to_json
# ---------------------------------------------------------------------------

class TestToJson:

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            runner = Runner()
            report = runner.scan(repo_root=repo)
            json_str = to_json(report)
            parsed = json.loads(json_str)
            assert parsed["tool"] == "storegreen"

    def test_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            runner = Runner()
            report = runner.scan(repo_root=repo)
            json_str = to_json(report)
            # Must not raise
            parsed = json.loads(json_str)
            assert isinstance(parsed, dict)

    def test_no_indent_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            runner = Runner()
            report = runner.scan(repo_root=repo)
            compact = to_json(report, indent=None)
            assert "\n" not in compact or compact.count("\n") < 5
