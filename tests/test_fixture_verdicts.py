# SPDX-License-Identifier: MIT
"""
tests/test_fixture_verdicts.py — pins the expected verdicts for every seeded
defect in the two demo fixtures.

A regression in any implemented rule causes one of these tests to fail rather
than silently producing a quieter report.

Fixtures covered
----------------
fixtures/tipjar-amazon     (source mode)
fixtures/tipjar-amazon.aab (bundle mode)
fixtures/notes-play        (source mode)

Defects left out (no implemented rule):
  AMZ-IAP-05, AMZ-IAP-07, AMZ-IAP-08  — tier-2, not yet implemented
  GP-16KB-01 in source mode            — bundle-only rule (NotApplicable from source)

Comment-stripping regression tests are included here because they were
discovered while building these fixtures and the fixtures are the evidence.
"""

from __future__ import annotations

import os
import struct
import tempfile
import textwrap
import zipfile
from typing import List

import pytest

from storegreen.runner import Runner, ScanReport
from storegreen.rules.base import Finding, NotApplicable, Passed, Undecided


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fixture(rel: str) -> str:
    return os.path.join(_REPO_ROOT, rel)


def _run(repo: str = None, aab: str = None) -> ScanReport:
    return Runner().scan(repo_root=repo, aab_path=aab)


def _findings(report: ScanReport) -> List[str]:
    return [f.rule for f in report.findings]


def _undecided(report: ScanReport) -> List[str]:
    return [u.rule for u in report.undecided]


def _passed(report: ScanReport) -> List[str]:
    return [p.rule for p in report.passed]


def _na(report: ScanReport) -> List[str]:
    return [n.rule for n in report.not_applicable]


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _make_elf(p_align: int) -> bytes:
    """Minimal 64-bit LE ELF with one PT_LOAD at the given alignment."""
    e_phoff, e_phentsize, e_phnum = 64, 56, 1
    total = e_phoff + e_phentsize
    hdr = bytearray(64)
    hdr[0:4] = b"\x7fELF"
    hdr[4], hdr[5], hdr[6] = 2, 1, 1
    struct.pack_into("<HHI", hdr, 16, 3, 0xb7, 1)
    struct.pack_into("<QQ",  hdr, 24, 0, e_phoff)
    struct.pack_into("<Q",   hdr, 40, 0)
    struct.pack_into("<IHHHH", hdr, 48, 0, 64, e_phentsize, e_phnum, 0)
    phdr = bytearray(56)
    struct.pack_into("<I",  phdr, 0,  1)
    struct.pack_into("<I",  phdr, 4,  5)
    struct.pack_into("<QQ", phdr, 8,  0, 0)
    struct.pack_into("<Q",  phdr, 24, 0)
    struct.pack_into("<QQ", phdr, 32, total, total)
    struct.pack_into("<Q",  phdr, 48, p_align)
    return bytes(hdr) + bytes(phdr)


# ---------------------------------------------------------------------------
# fixtures/tipjar-amazon — source mode
# ---------------------------------------------------------------------------

class TestTipjarAmazonSource:
    """Source-mode verdicts for fixtures/tipjar-amazon."""

    @pytest.fixture(autouse=True)
    def report(self):
        path = _fixture("fixtures/tipjar-amazon")
        if not os.path.isdir(path):
            pytest.skip("fixtures/tipjar-amazon not present")
        self.r = _run(repo=path)

    def test_amz_iap06_fires_as_block(self):
        """AMZ-IAP-06: proguard keeps only com.amazon.device.iap.** (too narrow) → BLOCK."""
        assert "AMZ-IAP-06" in _findings(self.r), \
            "AMZ-IAP-06 must fire — narrow keep rule misses com.amazon.**"
        f = next(f for f in self.r.findings if f.rule == "AMZ-IAP-06")
        assert f.severity == "BLOCK"

    def test_amz_iap01_is_undecided_not_block(self):
        """AMZ-IAP-01: key absent from source tree is Undecided (secret, not BLOCK)."""
        assert "AMZ-IAP-01" not in _findings(self.r), \
            "AMZ-IAP-01 must not BLOCK in source mode — the key is a secret"
        assert "AMZ-IAP-01" in _undecided(self.r), \
            "AMZ-IAP-01 must be Undecided in source mode when key is absent"

    def test_amz_iap03_is_undecided(self):
        """AMZ-IAP-03: receiver absent from source manifests → Undecided (AAR may contribute)."""
        assert "AMZ-IAP-03" not in _findings(self.r), \
            "AMZ-IAP-03 must not fire in source mode — AAR could still contribute"
        assert "AMZ-IAP-03" in _undecided(self.r)

    def test_amz_iap04_is_undecided(self):
        """AMZ-IAP-04: venezia absent from source manifests → Undecided (AAR may contribute)."""
        assert "AMZ-IAP-04" not in _findings(self.r), \
            "AMZ-IAP-04 must not fire in source mode — AAR could still contribute"
        assert "AMZ-IAP-04" in _undecided(self.r)

    def test_no_false_passes_on_seeded_defects(self):
        """None of the seeded rules must come back Passed."""
        seeded = {"AMZ-IAP-01", "AMZ-IAP-03", "AMZ-IAP-04", "AMZ-IAP-06"}
        false_passes = seeded & set(_passed(self.r))
        assert not false_passes, f"Seeded defect rules came back Passed: {false_passes}"

    def test_exactly_one_block_finding(self):
        """Source mode must produce exactly one BLOCK (AMZ-IAP-06)."""
        blocks = [f for f in self.r.findings if f.severity == "BLOCK"]
        assert len(blocks) == 1
        assert blocks[0].rule == "AMZ-IAP-06"


# ---------------------------------------------------------------------------
# fixtures/tipjar-amazon.aab — bundle mode
# ---------------------------------------------------------------------------

class TestTipjarAmazonBundle:
    """Bundle-mode verdicts for fixtures/tipjar-amazon.aab."""

    @pytest.fixture(autouse=True)
    def report(self):
        path = _fixture("fixtures/tipjar-amazon.aab")
        if not os.path.isfile(path):
            pytest.skip("fixtures/tipjar-amazon.aab not present")
        self.r = _run(aab=path)

    def test_amz_iap01_fires_as_block(self):
        """AMZ-IAP-01: no .pem in bundle → BLOCK."""
        assert "AMZ-IAP-01" in _findings(self.r)
        f = next(f for f in self.r.findings if f.rule == "AMZ-IAP-01")
        assert f.severity == "BLOCK"

    def test_amz_iap03_fires_as_block(self):
        """AMZ-IAP-03: ResponseReceiver absent from bundle manifest bytes → BLOCK."""
        assert "AMZ-IAP-03" in _findings(self.r)
        f = next(f for f in self.r.findings if f.rule == "AMZ-IAP-03")
        assert f.severity == "BLOCK"

    def test_amz_iap04_fires_as_block(self):
        """AMZ-IAP-04: com.amazon.venezia absent from bundle manifest bytes → BLOCK."""
        assert "AMZ-IAP-04" in _findings(self.r)
        f = next(f for f in self.r.findings if f.rule == "AMZ-IAP-04")
        assert f.severity == "BLOCK"

    def test_gp_16kb01_fires_as_warn(self):
        """GP-16KB-01: libtipjar.so p_align=0x1000 → WARN."""
        assert "GP-16KB-01" in _findings(self.r)
        f = next(f for f in self.r.findings if f.rule == "GP-16KB-01")
        assert f.severity == "WARN"
        assert "0x1000" in f.evidence.found

    def test_bundle_has_at_least_three_blocks(self):
        """The bundle must yield at least 3 BLOCKs from the three seeded defects."""
        blocks = [f for f in self.r.findings if f.severity == "BLOCK"]
        assert len(blocks) >= 3, \
            f"Expected ≥3 BLOCKs from bundle, got {[f.rule for f in blocks]}"


# ---------------------------------------------------------------------------
# fixtures/notes-play — source mode
# ---------------------------------------------------------------------------

class TestNotesPlaySource:
    """Source-mode verdicts for fixtures/notes-play."""

    @pytest.fixture(autouse=True)
    def report(self):
        path = _fixture("fixtures/notes-play")
        if not os.path.isdir(path):
            pytest.skip("fixtures/notes-play not present")
        self.r = _run(repo=path)

    def test_gp_api01_fires_as_block(self):
        """GP-API-01: targetSdk=35 < 36 for phone → BLOCK."""
        assert "GP-API-01" in _findings(self.r)
        f = next(f for f in self.r.findings if f.rule == "GP-API-01")
        assert f.severity == "BLOCK"
        assert "35" in f.evidence.found

    def test_gp_bill01_fires_as_block(self):
        """GP-BILL-01: billing-ktx:7.1.1 < 8 → BLOCK."""
        assert "GP-BILL-01" in _findings(self.r)
        f = next(f for f in self.r.findings if f.rule == "GP-BILL-01")
        assert f.severity == "BLOCK"
        assert "7.1.1" in f.evidence.found

    def test_x_flavor01_fires_as_risk(self):
        """X-FLAVOR-01: billing-ktx under plain implementation in amazon+play project → RISK."""
        assert "X-FLAVOR-01" in _findings(self.r)
        f = next(f for f in self.r.findings if f.rule == "X-FLAVOR-01")
        assert f.severity == "RISK"

    def test_no_false_passes_on_seeded_defects(self):
        seeded = {"GP-API-01", "GP-BILL-01", "X-FLAVOR-01"}
        false_passes = seeded & set(_passed(self.r))
        assert not false_passes, f"Seeded defect rules came back Passed: {false_passes}"


# ---------------------------------------------------------------------------
# Comment-stripping regression tests
# ---------------------------------------------------------------------------

class TestCommentStrippingAmzIap06:
    """AMZ-IAP-06 must not be fooled by -keep lines inside # comments."""

    def test_keep_only_in_comment_fires(self):
        """A proguard file whose only -keep class com.amazon.** is in a # comment → BLOCK."""
        with tempfile.TemporaryDirectory() as tmp:
            mod = os.path.join(tmp, "app")
            os.makedirs(os.path.join(mod, "src", "main"), exist_ok=True)
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), textwrap.dedent("""\
                <?xml version="1.0" encoding="utf-8"?>
                <manifest xmlns:android="http://schemas.android.com/apk/res/android"
                    package="com.example.app">
                    <application android:label="App" />
                </manifest>
            """))
            _write(os.path.join(mod, "build.gradle"), textwrap.dedent("""\
                plugins { id 'com.android.application' }
                android {
                    defaultConfig {
                        applicationId "com.example.app"
                        targetSdk 36
                        versionCode 1
                    }
                    productFlavors { amazon { } }
                    buildTypes {
                        release {
                            isMinifyEnabled true
                            proguardFiles 'proguard-rules.pro'
                        }
                    }
                }
            """))
            # The required lines appear ONLY inside # comments — must NOT satisfy the rule
            _write(os.path.join(mod, "proguard-rules.pro"), textwrap.dedent("""\
                # -keep class com.amazon.** { *; }
                # -dontwarn com.amazon.**
                # -keepattributes *Annotation*
                -keep class com.example.app.** { *; }
            """))
            report = Runner().scan(repo_root=tmp)
            assert "AMZ-IAP-06" in [f.rule for f in report.findings], \
                "AMZ-IAP-06 must fire when keep rules are only in # comments"

    def test_keep_outside_comment_passes(self):
        """Actual -keep class com.amazon.** (not commented) → passes AMZ-IAP-06."""
        with tempfile.TemporaryDirectory() as tmp:
            mod = os.path.join(tmp, "app")
            os.makedirs(os.path.join(mod, "src", "main"), exist_ok=True)
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), textwrap.dedent("""\
                <?xml version="1.0" encoding="utf-8"?>
                <manifest xmlns:android="http://schemas.android.com/apk/res/android"
                    package="com.example.app">
                    <application android:label="App" />
                </manifest>
            """))
            _write(os.path.join(mod, "build.gradle"), textwrap.dedent("""\
                plugins { id 'com.android.application' }
                android {
                    defaultConfig {
                        applicationId "com.example.app"
                        targetSdk 36
                        versionCode 1
                    }
                    productFlavors { amazon { } }
                    buildTypes {
                        release {
                            isMinifyEnabled true
                            proguardFiles 'proguard-rules.pro'
                        }
                    }
                }
            """))
            _write(os.path.join(mod, "proguard-rules.pro"), textwrap.dedent("""\
                -keep class com.amazon.** { *; }
                -dontwarn com.amazon.**
                -keepattributes *Annotation*
            """))
            report = Runner().scan(repo_root=tmp)
            assert "AMZ-IAP-06" not in [f.rule for f in report.findings], \
                "AMZ-IAP-06 must not fire when real keep rules are present"


class TestCommentStrippingAmzIap04:
    """AMZ-IAP-04 must not be fooled by package strings inside <!-- --> comments."""

    def test_venezia_only_in_xml_comment_is_undecided(self):
        """Manifest with com.amazon.venezia only inside <!-- --> → Undecided, not Passed."""
        with tempfile.TemporaryDirectory() as tmp:
            mod = os.path.join(tmp, "app")
            os.makedirs(os.path.join(mod, "src", "main"), exist_ok=True)
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), textwrap.dedent("""\
                <?xml version="1.0" encoding="utf-8"?>
                <manifest xmlns:android="http://schemas.android.com/apk/res/android"
                    package="com.example.app">
                    <!-- add: <package android:name="com.amazon.venezia" /> -->
                    <application android:label="App" />
                </manifest>
            """))
            _write(os.path.join(mod, "build.gradle"), textwrap.dedent("""\
                plugins { id 'com.android.application' }
                android {
                    defaultConfig {
                        applicationId "com.example.app"
                        targetSdk 36
                        versionCode 1
                    }
                    productFlavors { amazon { } }
                }
            """))
            report = Runner().scan(repo_root=tmp)
            passed_ids = [p.rule for p in report.passed]
            assert "AMZ-IAP-04" not in passed_ids, \
                "AMZ-IAP-04 must not pass when venezia only appears in an XML comment"
            # Must be undecided (honest: AAR could still contribute)
            undecided_ids = [u.rule for u in report.undecided]
            assert "AMZ-IAP-04" in undecided_ids, \
                "AMZ-IAP-04 must be Undecided when venezia is absent from live XML"
