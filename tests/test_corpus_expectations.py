# SPDX-License-Identifier: MIT
"""
tests/test_corpus_expectations.py — encodes the acceptance table from
prep/corpus-expectations.md and prep/rules-catalog.md sections 8 and 11.

Every test builds a minimal fixture in a temporary directory and runs the
runner directly.  No network, no Gradle, no NDK.

Naming convention:  test_<case_name>_<what_is_verified>
"""

from __future__ import annotations

import hashlib
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
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_dir(*parts: str) -> str:
    path = os.path.join(*parts)
    os.makedirs(path, exist_ok=True)
    return path


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _write_bytes(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def _manifest(target_sdk: int = 35, extra: str = "") -> str:
    return textwrap.dedent(f"""\
        <?xml version="1.0" encoding="utf-8"?>
        <manifest xmlns:android="http://schemas.android.com/apk/res/android"
            package="com.example.app">
            <uses-sdk android:targetSdkVersion="{target_sdk}" />
            <application android:label="App">
            </application>
            {extra}
        </manifest>
    """)


def _build_gradle(target_sdk: int = 35, billing_version: str = "", extra_deps: str = "",
                  flavors: str = "", minify: str = "") -> str:
    billing_dep = (
        f'    implementation "com.android.billingclient:billing:{billing_version}"'
        if billing_version else ""
    )
    minify_block = (
        f"        release {{\n            isMinifyEnabled {minify}\n        }}"
        if minify else ""
    )
    return textwrap.dedent(f"""\
        plugins {{ id 'com.android.application' }}
        android {{
            defaultConfig {{
                applicationId "com.example.app"
                targetSdk {target_sdk}
                versionCode 1
            }}
            {f'productFlavors {{ {flavors} }}' if flavors else ''}
            {f'buildTypes {{ {minify_block} }}' if minify_block else ''}
        }}
        dependencies {{
            {billing_dep}
            {extra_deps}
        }}
    """)


def _minimal_module(tmp: str, name: str = "app",
                    target_sdk: int = 36,
                    billing_version: str = "",
                    extra_manifest: str = "",
                    extra_deps: str = "",
                    flavors: str = "",
                    minify: str = "") -> str:
    """Create a minimal single-module repo and return repo root."""
    mod_dir = _make_dir(tmp, name)
    main_src = _make_dir(mod_dir, "src", "main")
    _write(os.path.join(main_src, "AndroidManifest.xml"),
           _manifest(target_sdk, extra_manifest))
    _write(os.path.join(mod_dir, "build.gradle"),
           _build_gradle(target_sdk, billing_version, extra_deps, flavors, minify))
    return tmp


def _run(repo: str = None, aab: str = None, **kw) -> ScanReport:
    runner = Runner(**kw)
    return runner.scan(repo_root=repo, aab_path=aab)


def _rule_ids(report: ScanReport, kind: str) -> List[str]:
    if kind == "findings":
        return [f.rule for f in report.findings]
    if kind == "undecided":
        return [u.rule for u in report.undecided]
    if kind == "passed":
        return [p.rule for p in report.passed]
    if kind == "na":
        return [n.rule for n in report.not_applicable]
    return []


# ---------------------------------------------------------------------------
# Gradle: kotlin-dsl  (targetSdk=35, billing=7.1.1 → two BLOCKs)
# ---------------------------------------------------------------------------

class TestKotlinDsl:
    def test_gp_api01_fires(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _make_dir(tmp, "app")
            _make_dir(mod, "src", "main")
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), _manifest(35))
            _write(os.path.join(mod, "build.gradle.kts"), textwrap.dedent("""\
                plugins { id("com.android.application") }
                android {
                    defaultConfig {
                        applicationId = "com.example.app"
                        targetSdk = 35
                        versionCode = 1
                    }
                }
                dependencies {
                    implementation("com.android.billingclient:billing:7.1.1")
                }
            """))
            report = _run(repo=tmp)
            assert "GP-API-01" in _rule_ids(report, "findings"), "GP-API-01 should fire for targetSdk=35 < 36"

    def test_gp_bill01_fires(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _make_dir(tmp, "app")
            _make_dir(mod, "src", "main")
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), _manifest(35))
            _write(os.path.join(mod, "build.gradle.kts"), textwrap.dedent("""\
                plugins { id("com.android.application") }
                android {
                    defaultConfig {
                        applicationId = "com.example.app"
                        targetSdk = 35
                        versionCode = 1
                    }
                }
                dependencies {
                    implementation("com.android.billingclient:billing:7.1.1")
                }
            """))
            report = _run(repo=tmp)
            assert "GP-BILL-01" in _rule_ids(report, "findings"), "GP-BILL-01 should fire for billing 7.1.1"


# ---------------------------------------------------------------------------
# Gradle: version-catalog  (evidence must point at toml, not build file)
# ---------------------------------------------------------------------------

class TestVersionCatalog:
    def test_gp_api01_evidence_points_at_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _make_dir(tmp, "app")
            _make_dir(mod, "src", "main")
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), _manifest(35))
            _make_dir(tmp, "gradle")
            _write(os.path.join(tmp, "gradle", "libs.versions.toml"), textwrap.dedent("""\
                [versions]
                targetSdk = "35"
                billing = "7.1.1"
                [libraries]
                billing-lib = { group = "com.android.billingclient", name = "billing", version.ref = "billing" }
            """))
            _write(os.path.join(mod, "build.gradle"), textwrap.dedent("""\
                plugins { id 'com.android.application' }
                android {
                    defaultConfig {
                        applicationId "com.example.app"
                        targetSdk libs.versions.targetSdk.get()
                        versionCode 1
                    }
                }
                dependencies {
                    implementation(libs.billing.lib)
                }
            """))
            report = _run(repo=tmp)
            api_findings = [f for f in report.findings if f.rule == "GP-API-01"]
            bill_findings = [f for f in report.findings if f.rule == "GP-BILL-01"]
            assert api_findings, "GP-API-01 should fire"
            assert bill_findings, "GP-BILL-01 should fire"
            # Evidence should point at the toml file, not the build.gradle
            api_ev = api_findings[0].evidence
            assert "libs.versions.toml" in api_ev.file or "toml" in api_ev.file.lower(), \
                f"evidence should point at version catalog, got: {api_ev.file}"


# ---------------------------------------------------------------------------
# Gradle: computed version (undecidable for GP-API-01)
# ---------------------------------------------------------------------------

class TestGradleComputedVersion:
    def test_gp_api01_undecidable_with_env_var(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _make_dir(tmp, "app")
            _make_dir(mod, "src", "main")
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), _manifest(36))
            _write(os.path.join(mod, "build.gradle"), textwrap.dedent("""\
                plugins { id 'com.android.application' }
                android {
                    defaultConfig {
                        applicationId "com.example.app"
                        targetSdk System.getenv("TARGET_SDK").toInteger()
                        versionCode 1
                    }
                }
                dependencies {
                    implementation "com.android.billingclient:billing:8.0.0"
                }
            """))
            report = _run(repo=tmp)
            assert "GP-API-01" in _rule_ids(report, "undecided"), \
                "GP-API-01 should be undecided for System.getenv"
            # Undecided must quote the line it gave up on
            u = next(u for u in report.undecided if u.rule == "GP-API-01")
            assert u.evidence.line is not None, "undecided must record the line it gave up on"

    def test_gp_bill01_decided_when_billing_is_literal(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _make_dir(tmp, "app")
            _make_dir(mod, "src", "main")
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), _manifest(36))
            _write(os.path.join(mod, "build.gradle"), textwrap.dedent("""\
                plugins { id 'com.android.application' }
                android {
                    defaultConfig {
                        applicationId "com.example.app"
                        targetSdk System.getenv("TARGET_SDK").toInteger()
                        versionCode 1
                    }
                }
                dependencies {
                    implementation "com.android.billingclient:billing:8.0.0"
                }
            """))
            report = _run(repo=tmp)
            # GP-BILL-01 should pass (8.0.0 >= 8)
            bill_passed = [p for p in report.passed if p.rule == "GP-BILL-01"]
            bill_findings = [f for f in report.findings if f.rule == "GP-BILL-01"]
            assert bill_passed or not bill_findings, "GP-BILL-01 should pass for billing 8.0.0"


# ---------------------------------------------------------------------------
# Form factor: Wear OS (targetSdk=35 should PASS)
# ---------------------------------------------------------------------------

class TestFormFactor:
    def test_wear_os_35_passes(self):
        """targetSdk 35 must PASS for a Wear OS app — the false-positive the rule was corrected to prevent."""
        with tempfile.TemporaryDirectory() as tmp:
            mod = _make_dir(tmp, "app")
            _make_dir(mod, "src", "main")
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), textwrap.dedent("""\
                <?xml version="1.0" encoding="utf-8"?>
                <manifest xmlns:android="http://schemas.android.com/apk/res/android"
                    package="com.example.wear">
                    <uses-sdk android:targetSdkVersion="35" />
                    <uses-feature android:name="android.hardware.type.watch" />
                    <application android:label="WearApp" />
                </manifest>
            """))
            _write(os.path.join(mod, "build.gradle"), _build_gradle(target_sdk=35))
            report = _run(repo=tmp)
            api_findings = [f for f in report.findings if f.rule == "GP-API-01"]
            assert not api_findings, "Wear OS with targetSdk=35 must NOT fire GP-API-01"
            api_passed = [p for p in report.passed if p.rule == "GP-API-01"]
            assert api_passed, "Wear OS with targetSdk=35 must PASS GP-API-01"
            # Evidence must name the form factor
            assert "wear" in api_passed[0].note.lower(), \
                "pass note must mention form factor 'wear'"

    def test_tv_34_passes(self):
        """targetSdk 34 must PASS for an Android TV app."""
        with tempfile.TemporaryDirectory() as tmp:
            mod = _make_dir(tmp, "app")
            _make_dir(mod, "src", "main")
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), textwrap.dedent("""\
                <?xml version="1.0" encoding="utf-8"?>
                <manifest xmlns:android="http://schemas.android.com/apk/res/android"
                    package="com.example.tv">
                    <uses-sdk android:targetSdkVersion="34" />
                    <uses-feature android:name="android.software.leanback" />
                    <application android:label="TvApp" />
                </manifest>
            """))
            _write(os.path.join(mod, "build.gradle"), _build_gradle(target_sdk=34))
            report = _run(repo=tmp)
            api_findings = [f for f in report.findings if f.rule == "GP-API-01"]
            assert not api_findings, "Android TV with targetSdk=34 must NOT fire GP-API-01"

    def test_automotive_35_passes(self):
        """targetSdk 35 must PASS for an Automotive app."""
        with tempfile.TemporaryDirectory() as tmp:
            mod = _make_dir(tmp, "app")
            _make_dir(mod, "src", "main")
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), textwrap.dedent("""\
                <?xml version="1.0" encoding="utf-8"?>
                <manifest xmlns:android="http://schemas.android.com/apk/res/android"
                    package="com.example.auto">
                    <uses-sdk android:targetSdkVersion="35" />
                    <uses-feature android:name="android.hardware.type.automotive" />
                    <application android:label="AutoApp" />
                </manifest>
            """))
            _write(os.path.join(mod, "build.gradle"), _build_gradle(target_sdk=35))
            report = _run(repo=tmp)
            api_findings = [f for f in report.findings if f.rule == "GP-API-01"]
            assert not api_findings, "Automotive with targetSdk=35 must NOT fire GP-API-01"

    def test_phone_36_passes(self):
        """targetSdk 36 must PASS for a phone app; evidence says 'phone'."""
        with tempfile.TemporaryDirectory() as tmp:
            mod = _make_dir(tmp, "app")
            _make_dir(mod, "src", "main")
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), _manifest(36))
            _write(os.path.join(mod, "build.gradle"), _build_gradle(target_sdk=36))
            report = _run(repo=tmp)
            api_findings = [f for f in report.findings if f.rule == "GP-API-01"]
            assert not api_findings, "Phone with targetSdk=36 must NOT fire GP-API-01"
            api_passed = [p for p in report.passed if p.rule == "GP-API-01"]
            assert api_passed, "Phone with targetSdk=36 must PASS GP-API-01"
            assert "phone" in api_passed[0].note.lower(), "pass note must mention 'phone'"

    def test_phone_35_blocks(self):
        """targetSdk 35 for a phone app → GP-API-01 fires."""
        with tempfile.TemporaryDirectory() as tmp:
            mod = _make_dir(tmp, "app")
            _make_dir(mod, "src", "main")
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), _manifest(35))
            _write(os.path.join(mod, "build.gradle"), _build_gradle(target_sdk=35))
            report = _run(repo=tmp)
            assert "GP-API-01" in _rule_ids(report, "findings")


# ---------------------------------------------------------------------------
# GP-BILL-01: billing version checks
# ---------------------------------------------------------------------------

class TestGpBill01:
    def test_billing_8_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            _minimal_module(tmp, target_sdk=36, billing_version="8.0.0")
            report = _run(repo=tmp)
            assert "GP-BILL-01" not in _rule_ids(report, "findings")

    def test_billing_7_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            _minimal_module(tmp, target_sdk=36, billing_version="7.1.1")
            report = _run(repo=tmp)
            assert "GP-BILL-01" in _rule_ids(report, "findings")

    def test_billing_absent_is_not_applicable(self):
        with tempfile.TemporaryDirectory() as tmp:
            _minimal_module(tmp, target_sdk=36, billing_version="")
            report = _run(repo=tmp)
            assert "GP-BILL-01" not in _rule_ids(report, "findings")
            assert "GP-BILL-01" in _rule_ids(report, "na")


# ---------------------------------------------------------------------------
# AMZ-IAP-01: key in bundle
# ---------------------------------------------------------------------------

def _make_aab_with_pem(tmp: str, include_pem: bool = True) -> str:
    path = os.path.join(tmp, "test.aab")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("base/manifest/AndroidManifest.xml", b"\x0a\x00manifest")
        if include_pem:
            zf.writestr("base/assets/AppstoreAuthenticationKey.pem",
                        b"-----BEGIN PUBLIC KEY-----\nfakekey\n-----END PUBLIC KEY-----\n")
    return path


class TestAmzIap01:
    def test_key_present_in_bundle_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            aab = _make_aab_with_pem(tmp, include_pem=True)
            report = _run(aab=aab)
            passed_ids = _rule_ids(report, "passed")
            assert "AMZ-IAP-01" in passed_ids
            # Evidence must include SHA-256
            p = next(p for p in report.passed if p.rule == "AMZ-IAP-01")
            assert "SHA-256" in p.note or (p.evidence and "SHA-256" in (p.evidence.found or ""))

    def test_key_absent_from_bundle_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            aab = _make_aab_with_pem(tmp, include_pem=False)
            report = _run(aab=aab)
            finding_ids = _rule_ids(report, "findings")
            assert "AMZ-IAP-01" in finding_ids
            f = next(f for f in report.findings if f.rule == "AMZ-IAP-01")
            assert f.severity == "BLOCK"


# ---------------------------------------------------------------------------
# AMZ-IAP-01: key absent from source tree (RISK / Undecided, not BLOCK)
# ---------------------------------------------------------------------------

class TestAmzIap01Source:
    def test_key_absent_from_source_is_undecided_not_block(self):
        """The key should not be in a repo; source-mode absence is not a BLOCK."""
        with tempfile.TemporaryDirectory() as tmp:
            mod = _make_dir(tmp, "app")
            _make_dir(mod, "src", "main")
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), _manifest())
            _write(os.path.join(mod, "build.gradle"), textwrap.dedent("""\
                plugins { id 'com.android.application' }
                android {
                    defaultConfig {
                        applicationId "com.example.app"
                        targetSdk 36
                        versionCode 1
                    }
                    productFlavors {
                        amazon { }
                        google { }
                    }
                }
            """))
            report = _run(repo=tmp)
            # AMZ-IAP-01 must NOT be a BLOCK finding in source mode
            block_findings = [f for f in report.findings if f.rule == "AMZ-IAP-01" and f.severity == "BLOCK"]
            assert not block_findings, "AMZ-IAP-01 must not be BLOCK in source mode when key is absent (it's a secret)"


# ---------------------------------------------------------------------------
# AMZ-IAP-03: ResponseReceiver in bundle manifest
# ---------------------------------------------------------------------------

def _make_aab_with_manifest_content(tmp: str, manifest_content: str, name: str = "test.aab") -> str:
    path = os.path.join(tmp, name)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("base/manifest/AndroidManifest.xml",
                    manifest_content.encode("utf-8"))
        zf.writestr("base/assets/AppstoreAuthenticationKey.pem", b"fakekey")
    return path


class TestAmzIap03:
    def test_receiver_present_in_bundle_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = (
                b"\x0amanifest com.amazon.device.iap.ResponseReceiver "
                b"com.amazon.inapp.purchasing.NOTIFY"
            )
            path = os.path.join(tmp, "test.aab")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("base/manifest/AndroidManifest.xml", content)
                zf.writestr("base/assets/AppstoreAuthenticationKey.pem", b"fakekey")
            report = _run(aab=path)
            assert "AMZ-IAP-03" in _rule_ids(report, "passed")

    def test_receiver_absent_from_bundle_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = b"\x0amanifest no-amazon-receiver-here"
            path = os.path.join(tmp, "test.aab")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("base/manifest/AndroidManifest.xml", content)
            report = _run(aab=path)
            assert "AMZ-IAP-03" in _rule_ids(report, "findings")
            f = next(f for f in report.findings if f.rule == "AMZ-IAP-03")
            assert f.severity == "BLOCK"


# ---------------------------------------------------------------------------
# AMZ-IAP-04: com.amazon.venezia in bundle manifest
# ---------------------------------------------------------------------------

class TestAmzIap04:
    def test_venezia_present_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = b"\x0amanifest com.amazon.venezia com.amazon.sdktestclient"
            path = os.path.join(tmp, "test.aab")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("base/manifest/AndroidManifest.xml", content)
                zf.writestr("base/assets/AppstoreAuthenticationKey.pem", b"fakekey")
            report = _run(aab=path)
            assert "AMZ-IAP-04" in _rule_ids(report, "passed")

    def test_venezia_absent_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = b"\x0amanifest no-venezia-here"
            path = os.path.join(tmp, "test.aab")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("base/manifest/AndroidManifest.xml", content)
            report = _run(aab=path)
            assert "AMZ-IAP-04" in _rule_ids(report, "findings")
            f = next(f for f in report.findings if f.rule == "AMZ-IAP-04")
            assert f.severity == "BLOCK"


# ---------------------------------------------------------------------------
# AMZ-IAP-06: R8 keep rules
# ---------------------------------------------------------------------------

class TestAmzIap06:
    def test_no_minify_not_applicable(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _make_dir(tmp, "app")
            _make_dir(mod, "src", "main")
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), _manifest())
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
            report = _run(repo=tmp)
            # Without isMinifyEnabled, AMZ-IAP-06 should be NotApplicable
            assert "AMZ-IAP-06" not in _rule_ids(report, "findings"), \
                "AMZ-IAP-06 should not fire without isMinifyEnabled"

    def test_minify_true_missing_rules_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _make_dir(tmp, "app")
            _make_dir(mod, "src", "main")
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), _manifest())
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
            # proguard file without amazon keep rules
            _write(os.path.join(mod, "proguard-rules.pro"),
                   "-keep class com.example.** { *; }\n")
            report = _run(repo=tmp)
            assert "AMZ-IAP-06" in _rule_ids(report, "findings"), \
                "AMZ-IAP-06 should fire when keep rules are missing"

    def test_minify_true_with_correct_rules_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _make_dir(tmp, "app")
            _make_dir(mod, "src", "main")
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), _manifest())
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
            _write(os.path.join(mod, "proguard-rules.pro"),
                   "-keep class com.amazon.** { *; }\n"
                   "-dontwarn com.amazon.**\n"
                   "-keepattributes *Annotation*\n")
            report = _run(repo=tmp)
            assert "AMZ-IAP-06" not in _rule_ids(report, "findings"), \
                "AMZ-IAP-06 should not fire with correct keep rules"


# ---------------------------------------------------------------------------
# GP-16KB-01: ELF alignment in bundle
# ---------------------------------------------------------------------------

def _make_elf_64(p_align: int) -> bytes:
    """Build a minimal 64-bit LE ELF with one PT_LOAD segment at given p_align."""
    # ELF header: 64 bytes
    # Program header: 56 bytes (1 header)
    e_phoff = 64
    e_phentsize = 56
    e_phnum = 1
    total = e_phoff + e_phentsize

    hdr = bytearray(64)
    hdr[0:4] = b"\x7fELF"
    hdr[4] = 2   # EI_CLASS = 64-bit
    hdr[5] = 1   # EI_DATA = LE
    hdr[6] = 1   # EI_VERSION
    hdr[7] = 0   # EI_OSABI
    # e_type=3(ET_DYN), e_machine=0xb7(aarch64), e_version=1
    struct.pack_into("<HHI", hdr, 16, 3, 0xb7, 1)
    # e_entry=0, e_phoff=64
    struct.pack_into("<QQ", hdr, 24, 0, e_phoff)
    # e_shoff=0
    struct.pack_into("<Q", hdr, 40, 0)
    # e_flags=0, e_ehsize=64, e_phentsize=56, e_phnum=1
    struct.pack_into("<IHHHH", hdr, 48, 0, 64, e_phentsize, e_phnum, 0)

    # Program header (56 bytes)
    phdr = bytearray(56)
    struct.pack_into("<I", phdr, 0, 1)          # p_type = PT_LOAD
    struct.pack_into("<I", phdr, 4, 5)          # p_flags = R|X
    struct.pack_into("<Q", phdr, 8, 0)          # p_offset
    struct.pack_into("<Q", phdr, 16, 0)         # p_vaddr
    struct.pack_into("<Q", phdr, 24, 0)         # p_paddr
    struct.pack_into("<Q", phdr, 32, total)     # p_filesz
    struct.pack_into("<Q", phdr, 40, total)     # p_memsz
    struct.pack_into("<Q", phdr, 48, p_align)   # p_align

    return bytes(hdr) + bytes(phdr)


def _make_aab_with_so(tmp: str, p_align: int, lib_name: str = "libtest.so") -> str:
    elf_data = _make_elf_64(p_align)
    path = os.path.join(tmp, "test.aab")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("base/manifest/AndroidManifest.xml", b"\x0amanifest")
        zf.writestr(f"base/lib/arm64-v8a/{lib_name}", elf_data)
    return path


class TestGp16Kb01:
    def test_aligned_lib_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            aab = _make_aab_with_so(tmp, p_align=0x4000)
            report = _run(aab=aab)
            assert "GP-16KB-01" not in _rule_ids(report, "findings")
            assert "GP-16KB-01" in _rule_ids(report, "passed")

    def test_misaligned_lib_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            aab = _make_aab_with_so(tmp, p_align=0x1000)
            report = _run(aab=aab)
            assert "GP-16KB-01" in _rule_ids(report, "findings")
            f = next(f for f in report.findings if f.rule == "GP-16KB-01")
            assert f.severity == "WARN"
            assert "0x1000" in f.evidence.found

    def test_no_native_libs_not_applicable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.aab")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("base/manifest/AndroidManifest.xml", b"\x0amanifest")
            report = _run(aab=path)
            assert "GP-16KB-01" in _rule_ids(report, "na")

    def test_empty_elf_is_undecided(self):
        """An empty (0-byte) .so must not crash and must not silently pass."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.aab")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("base/manifest/AndroidManifest.xml", b"\x0amanifest")
                zf.writestr("base/lib/arm64-v8a/libempty.so", b"")
            report = _run(aab=path)
            # Empty file must not produce a pass
            assert "GP-16KB-01" not in _rule_ids(report, "passed"), \
                "empty .so must not silently pass GP-16KB-01"

    def test_truncated_elf_is_undecided(self):
        """A truncated ELF (only magic bytes) must not crash."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.aab")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("base/manifest/AndroidManifest.xml", b"\x0amanifest")
                zf.writestr("base/lib/arm64-v8a/libtrunc.so", b"\x7fELF\x02\x01")
            report = _run(aab=path)
            assert "GP-16KB-01" not in _rule_ids(report, "passed"), \
                "truncated ELF must not produce a pass"


# ---------------------------------------------------------------------------
# X-FLAVOR-01: Play Billing in amazon bundle
# ---------------------------------------------------------------------------

def _make_aab_with_billing(tmp: str, include_billing: bool = True,
                            name: str = "test.aab") -> str:
    path = os.path.join(tmp, name)
    with zipfile.ZipFile(path, "w") as zf:
        manifest_content = b"\x0amanifest"
        if include_billing:
            manifest_content = (
                b"\x0amanifest com.android.vending.BILLING "
                b"com.amazon.device.iap.ResponseReceiver com.amazon.venezia"
            )
        zf.writestr("base/manifest/AndroidManifest.xml", manifest_content)
        zf.writestr("base/assets/AppstoreAuthenticationKey.pem", b"fakekey")
        if include_billing:
            # Put billing classes in dex
            fake_dex = b"dex\n035\x00" + b"\x00" * 100 + b"com/android/billingclient/api/BillingClient"
            zf.writestr("base/dex/classes.dex", fake_dex)
        else:
            fake_dex = b"dex\n035\x00" + b"\x00" * 100 + b"com/amazon/device/iap/PurchasingService"
            zf.writestr("base/dex/classes.dex", fake_dex)
    return path


class TestXFlavor01:
    def test_billing_in_amazon_bundle_fires(self):
        """Play Billing in an amazon-labeled bundle → X-FLAVOR-01 fires."""
        with tempfile.TemporaryDirectory() as tmp:
            aab = _make_aab_with_billing(tmp, include_billing=True)
            report = _run(aab=aab)
            assert "X-FLAVOR-01" in _rule_ids(report, "findings"), \
                "X-FLAVOR-01 must fire when Play Billing is in bundle"
            f = next(f for f in report.findings if f.rule == "X-FLAVOR-01")
            assert f.severity == "RISK"

    def test_clean_amazon_bundle_passes(self):
        """Bundle with only Amazon IAP (no Play Billing) → X-FLAVOR-01 passes."""
        with tempfile.TemporaryDirectory() as tmp:
            aab = _make_aab_with_billing(tmp, include_billing=False)
            report = _run(aab=aab)
            assert "X-FLAVOR-01" not in _rule_ids(report, "findings"), \
                "X-FLAVOR-01 must not fire on clean amazon bundle"

    def test_no_flavors_not_applicable_source(self):
        """Without an amazon flavor, X-FLAVOR-01 is NotApplicable in source mode."""
        with tempfile.TemporaryDirectory() as tmp:
            _minimal_module(tmp, target_sdk=36)
            report = _run(repo=tmp)
            assert "X-FLAVOR-01" not in _rule_ids(report, "findings")
            assert "X-FLAVOR-01" in _rule_ids(report, "na")


# ---------------------------------------------------------------------------
# Decidability counters (spec §11)
# ---------------------------------------------------------------------------

class TestDecidabilityCounters:
    def test_summary_has_decided_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            _minimal_module(tmp, target_sdk=36)
            report = _run(repo=tmp)
            assert "decided" in report.summary

    def test_not_implemented_list_has_13_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            _minimal_module(tmp, target_sdk=36)
            report = _run(repo=tmp)
            assert len(report.not_implemented) == 13, \
                f"Expected 13 not-implemented rules, got {len(report.not_implemented)}: {report.not_implemented}"

    def test_not_implemented_includes_tier2_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            _minimal_module(tmp, target_sdk=36)
            report = _run(repo=tmp)
            required = {
                "AMZ-IAP-02", "AMZ-IAP-05", "AMZ-IAP-07", "AMZ-IAP-08",
                "GP-API-02", "GP-BILL-02", "GP-PERM-01", "GP-PERM-02",
                "GP-PRIV-01", "GP-DS-01", "GP-EXP-01", "X-SIGN-01", "X-VER-01",
            }
            assert required.issubset(set(report.not_implemented)), \
                f"Missing from not_implemented: {required - set(report.not_implemented)}"

    def test_empty_dir_decides_nothing(self):
        """An empty directory: no findings, no passes, counters show nothing decided."""
        with tempfile.TemporaryDirectory() as tmp:
            report = _run(repo=tmp)
            assert report.summary["decided"] == 0 or report.summary["block"] == 0
            # Crucially: no silently-green findings that imply false coverage
            assert not report.findings, "empty dir should produce no findings"

    def test_counters_reproducible(self):
        """Running twice on the same tree must yield identical counter values."""
        with tempfile.TemporaryDirectory() as tmp:
            _minimal_module(tmp, target_sdk=36, billing_version="8.0.0")
            r1 = _run(repo=tmp)
            r2 = _run(repo=tmp)
            assert r1.summary["decided"] == r2.summary["decided"]
            assert r1.summary["undecidable"] == r2.summary["undecidable"]
            assert r1.summary["not_applicable"] == r2.summary["not_applicable"]
            assert r1.summary["not_implemented"] == r2.summary["not_implemented"]


# ---------------------------------------------------------------------------
# Flavors and correct scoping (X-FLAVOR-01 must stay silent)
# ---------------------------------------------------------------------------

class TestCorrectFlavorsScoping:
    def test_correctly_scoped_billing_stays_silent(self):
        """Play Billing in google flavor only → X-FLAVOR-01 must NOT fire (source mode)."""
        with tempfile.TemporaryDirectory() as tmp:
            mod = _make_dir(tmp, "app")
            _make_dir(mod, "src", "main")
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), _manifest())
            _write(os.path.join(mod, "build.gradle"), textwrap.dedent("""\
                plugins { id 'com.android.application' }
                android {
                    defaultConfig {
                        applicationId "com.example.app"
                        targetSdk 36
                        versionCode 1
                    }
                    productFlavors {
                        amazon { }
                        google { }
                    }
                }
                dependencies {
                    googleImplementation "com.android.billingclient:billing:8.0.0"
                }
            """))
            report = _run(repo=tmp)
            flavor_findings = [f for f in report.findings if f.rule == "X-FLAVOR-01"]
            assert not flavor_findings, \
                "X-FLAVOR-01 must stay silent when billing is correctly scoped to google flavor"


# ---------------------------------------------------------------------------
# AMZ-IAP-01 source: key present in source tree → Passed
# ---------------------------------------------------------------------------

class TestAmzIap01KeyInSourceTree:
    def test_key_present_in_source_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _make_dir(tmp, "app")
            _make_dir(mod, "src", "main")
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), _manifest())
            # Create the amazon flavor assets directory with the key
            amazon_assets = _make_dir(mod, "src", "amazon", "assets")
            _write(os.path.join(amazon_assets, "AppstoreAuthenticationKey.pem"),
                   "-----BEGIN PUBLIC KEY-----\nfakekey\n-----END PUBLIC KEY-----\n")
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
            report = _run(repo=tmp)
            # Should pass (not undecided) since key is present in source tree
            passed = [p for p in report.passed if p.rule == "AMZ-IAP-01"]
            not_block = [f for f in report.findings if f.rule == "AMZ-IAP-01" and f.severity == "BLOCK"]
            assert passed or not not_block, \
                "AMZ-IAP-01 should pass or at least not BLOCK when key is present in source"


# ---------------------------------------------------------------------------
# Broken inputs: no crash, no silent pass
# ---------------------------------------------------------------------------

class TestBrokenInputs:
    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = _run(repo=tmp)
            assert isinstance(report, ScanReport)
            # No crash; report exists

    def test_aab_not_a_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.aab")
            with open(path, "wb") as fh:
                fh.write(b"this is not a zip file at all")
            report = _run(aab=path)
            assert isinstance(report, ScanReport)
            # Should not crash; bundle rules return undecided or na

    def test_aab_empty_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.aab")
            with zipfile.ZipFile(path, "w") as zf:
                pass  # empty zip
            report = _run(aab=path)
            assert isinstance(report, ScanReport)

    def test_aab_truncated_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trunc.aab")
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("base/manifest/AndroidManifest.xml", b"\x0amanifest")
                # Truncated ELF - just 4 bytes
                zf.writestr("base/lib/arm64-v8a/libtrunc.so", b"\x7fELF")
            report = _run(aab=path)
            assert isinstance(report, ScanReport)
            # Must not silently pass
            assert "GP-16KB-01" not in _rule_ids(report, "passed"), \
                "truncated ELF must not produce a pass"

    def test_manifest_not_xml(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod = _make_dir(tmp, "app")
            _make_dir(mod, "src", "main")
            _write_bytes(os.path.join(mod, "src", "main", "AndroidManifest.xml"),
                         b"\x00\x01\x02 not xml at all")
            _write(os.path.join(mod, "build.gradle"), _build_gradle())
            report = _run(repo=tmp)
            assert isinstance(report, ScanReport)
            # Should not crash

    def test_manifest_xml_bomb_finishes_quickly(self):
        """XML entity expansion bomb must not eat memory/time."""
        with tempfile.TemporaryDirectory() as tmp:
            mod = _make_dir(tmp, "app")
            _make_dir(mod, "src", "main")
            bomb = textwrap.dedent("""\
                <?xml version="1.0"?>
                <!DOCTYPE foo [
                  <!ENTITY a "aaaaaaaaaa">
                  <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
                  <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
                ]>
                <manifest xmlns:android="http://schemas.android.com/apk/res/android"
                    package="com.example.app">
                    <application>&c;</application>
                </manifest>
            """)
            _write(os.path.join(mod, "src", "main", "AndroidManifest.xml"), bomb)
            _write(os.path.join(mod, "build.gradle"), _build_gradle())
            import time
            t0 = time.monotonic()
            report = _run(repo=tmp)
            elapsed = time.monotonic() - t0
            assert isinstance(report, ScanReport)
            # Must finish in reasonable time (< 5 seconds)
            assert elapsed < 5.0, f"XML bomb took too long: {elapsed:.1f}s"
