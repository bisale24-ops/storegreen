# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
rules/amz_iap.py — Amazon In-App Purchasing rules (tier 1).

Implements:
  AMZ-IAP-01  AppstoreAuthenticationKey.pem present in bundle
  AMZ-IAP-03  ResponseReceiver declared in manifest
  AMZ-IAP-04  <queries> contains com.amazon.venezia (targetSdk >= 30)
  AMZ-IAP-06  R8 keep rules for com.amazon.** in release builds

Spec references: rules-catalog.md sections A, 1, 3, 7.
Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import List, Optional

from storegreen.rules.base import (
    BundleContext,
    Evidence,
    Finding,
    FixHint,
    NotApplicable,
    Passed,
    Rule,
    RuleResult,
    SourceContext,
    Undecided,
)
from storegreen.source import project_layout as pl_mod
from storegreen.source import manifest_merger
from storegreen.source import gradle_reader


# ---------------------------------------------------------------------------
# Helpers shared across the Amazon rules
# ---------------------------------------------------------------------------

_AMAZON_FLAVORS = ("amazon", "Amazon", "appstore", "Appstore")

def _has_amazon_flavor(layout: pl_mod.ProjectLayout) -> bool:
    for mod in layout.modules:
        for f in mod.flavors:
            if f.lower() in ("amazon", "appstore"):
                return True
    return False


def _amazon_modules(layout: pl_mod.ProjectLayout):
    """Yield (module, flavor_name) for modules that have an Amazon flavor."""
    for mod in layout.modules:
        for f in mod.flavors:
            if f.lower() in ("amazon", "appstore"):
                yield mod, f


# ---------------------------------------------------------------------------
# AMZ-IAP-01: AppstoreAuthenticationKey.pem present
# ---------------------------------------------------------------------------

class AmzIap01(Rule):
    """AMZ-IAP-01 — AppstoreAuthenticationKey.pem absent from bundle."""

    id = "AMZ-IAP-01"
    family = "amazon-iap"
    severity = "BLOCK"
    tier = 1

    PEM_ENTRY = "base/assets/AppstoreAuthenticationKey.pem"

    def check_source(self, ctx: SourceContext) -> RuleResult:
        layout = ctx.get_layout()
        if layout is None or not _has_amazon_flavor(layout):
            return NotApplicable(rule=self.id, reason="no amazon flavor")

        # Source mode: absence is RISK (secret correctly omitted from repo).
        # Check whether any amazon flavor src set has the key.
        for mod, flavor in _amazon_modules(layout):
            # src/<flavor>/assets/AppstoreAuthenticationKey.pem
            asset_paths = [
                os.path.join(mod.root, "src", flavor, "assets", "AppstoreAuthenticationKey.pem"),
                os.path.join(mod.root, "src", "main", "assets", "AppstoreAuthenticationKey.pem"),
            ]
            for p in asset_paths:
                if os.path.isfile(p):
                    # Key found in source tree — read SHA-256 for auditability
                    try:
                        with open(p, "rb") as fh:
                            digest = hashlib.sha256(fh.read()).hexdigest()
                    except OSError:
                        digest = "unreadable"
                    rel = os.path.relpath(p, ctx.repo_root)
                    return Passed(
                        rule=self.id,
                        note=f"key present in source tree (SHA-256: {digest})",
                        decided_from="source",
                        evidence=Evidence(
                            file=rel,
                            line=None,
                            found=f"SHA-256: {digest}",
                            expected="AppstoreAuthenticationKey.pem present",
                        ),
                    )

        # Key absent in source tree — RISK (it is a secret and should not be committed)
        # Find a build file to anchor the evidence
        for mod, flavor in _amazon_modules(layout):
            rel_build = os.path.relpath(mod.build_gradle, ctx.repo_root)
            return Undecided(
                rule=self.id,
                reason=(
                    "AppstoreAuthenticationKey.pem not found in source tree — "
                    "the key is a secret and does not belong in a public repository; "
                    "verify it is injected at build time before uploading"
                ),
                evidence=Evidence(
                    file=rel_build,
                    line=1,
                    found="key absent from source tree",
                    expected="key injected at build time",
                ),
            )

        return NotApplicable(rule=self.id, reason="no amazon flavor")

    def check_bundle(self, ctx: BundleContext) -> RuleResult:
        from storegreen.bundle.aab_reader import AabReader
        try:
            with AabReader(ctx.aab_path) as reader:
                if reader.has(self.PEM_ENTRY):
                    data = reader.read(self.PEM_ENTRY)
                    digest = hashlib.sha256(data).hexdigest() if data else "unreadable"
                    return Passed(
                        rule=self.id,
                        note=f"key present in bundle (SHA-256: {digest})",
                        decided_from="bundle",
                        evidence=Evidence(
                            file=self.PEM_ENTRY,
                            line=None,
                            found=f"SHA-256: {digest}",
                            expected="AppstoreAuthenticationKey.pem present",
                        ),
                    )
                # Absent in bundle → BLOCK
                return Finding(
                    rule=self.id,
                    family=self.family,
                    severity="BLOCK",
                    title="AppstoreAuthenticationKey.pem missing from bundle",
                    evidence=Evidence(
                        file=self.PEM_ENTRY,
                        line=None,
                        found="entry absent",
                        expected="base/assets/AppstoreAuthenticationKey.pem present",
                    ),
                    decided_from="bundle",
                    fix=FixHint(
                        automatic=False,
                        description=(
                            "Download the public key: Amazon Developer Console → "
                            "app → Upload Your App File → Additional information → "
                            "View public key.  Place it at base/assets/AppstoreAuthenticationKey.pem "
                            "before bundling."
                        ),
                    ),
                )
        except Exception as exc:
            return Undecided(
                rule=self.id,
                reason=f"cannot read bundle: {exc}",
                evidence=Evidence(
                    file=ctx.aab_path, line=None,
                    found=str(exc), expected="readable .aab",
                ),
            )


# ---------------------------------------------------------------------------
# AMZ-IAP-03: ResponseReceiver declared in manifest
# ---------------------------------------------------------------------------

RECEIVER_NAME = "com.amazon.device.iap.ResponseReceiver"
NOTIFY_ACTION = "com.amazon.inapp.purchasing.NOTIFY"
NOTIFY_PERMISSION = "com.amazon.inapp.purchasing.Permission.NOTIFY"

class AmzIap03(Rule):
    """AMZ-IAP-03 — ResponseReceiver absent from manifest."""

    id = "AMZ-IAP-03"
    family = "amazon-iap"
    severity = "BLOCK"
    tier = 1

    def check_source(self, ctx: SourceContext) -> RuleResult:
        layout = ctx.get_layout()
        if layout is None or not _has_amazon_flavor(layout):
            return NotApplicable(rule=self.id, reason="no amazon flavor")

        for mod, flavor in _amazon_modules(layout):
            flavor_paths = mod.flavor_manifests.get(flavor, [])
            merged = manifest_merger.merge(
                module_name=mod.name,
                main_manifest_path=mod.main_manifest,
                flavor_manifest_paths=flavor_paths,
                flavor=flavor,
            )

            # Look for the receiver by android:name
            for elem in merged.elements:
                if elem.tag == "receiver":
                    name = elem.android("name") or ""
                    if RECEIVER_NAME in name:
                        rel = os.path.relpath(elem.source_file, ctx.repo_root)
                        return Passed(
                            rule=self.id,
                            note=(
                                f"ResponseReceiver declared in source manifest — "
                                "structure (exported, permission, intent-filter) "
                                "not verifiable from source; re-run with --aab for full check"
                            ),
                            decided_from="source",
                            evidence=Evidence(
                                file=rel,
                                line=elem.source_line,
                                found=f"receiver {name!r} declared",
                                expected=RECEIVER_NAME,
                            ),
                        )

            # Not found in source — could still come from an AAR library manifest
            main_rel = os.path.relpath(mod.main_manifest, ctx.repo_root) if mod.main_manifest else mod.name
            return Undecided(
                rule=self.id,
                reason=(
                    f"{RECEIVER_NAME} not found in source manifests — "
                    "a dependency AAR may still contribute it; re-run with --aab"
                ),
                evidence=Evidence(
                    file=main_rel,
                    line=1,
                    found="receiver absent from source manifests",
                    expected=RECEIVER_NAME,
                ),
            )

        return NotApplicable(rule=self.id, reason="no amazon flavor")

    def check_bundle(self, ctx: BundleContext) -> RuleResult:
        from storegreen.bundle.aab_reader import AabReader
        from storegreen.bundle.manifest_bytes import from_aab
        try:
            with AabReader(ctx.aab_path) as reader:
                mb = from_aab(reader)
                if mb is None:
                    return Undecided(
                        rule=self.id,
                        reason="manifest entry missing from bundle",
                        evidence=Evidence(
                            file="base/manifest/AndroidManifest.xml",
                            line=None, found="entry absent", expected="manifest present",
                        ),
                    )
                found, snippet = mb.search(RECEIVER_NAME)
                if found:
                    return Passed(
                        rule=self.id,
                        note=(
                            "ResponseReceiver declared in bundle manifest — "
                            "presence only; structure (exported, permission, intent-filter) "
                            "not verifiable from protobuf bytes"
                        ),
                        decided_from="bundle",
                        evidence=Evidence(
                            file=mb.entry_path,
                            line=None,
                            found=snippet or RECEIVER_NAME,
                            expected=RECEIVER_NAME,
                        ),
                    )
                return Finding(
                    rule=self.id,
                    family=self.family,
                    severity="BLOCK",
                    title="com.amazon.device.iap.ResponseReceiver absent from bundle manifest",
                    evidence=Evidence(
                        file=mb.entry_path,
                        line=None,
                        found="receiver not found in manifest bytes",
                        expected=RECEIVER_NAME,
                    ),
                    decided_from="bundle",
                    fix=FixHint(
                        automatic=False,
                        description=(
                            "Add the receiver block to AndroidManifest.xml: "
                            "<receiver android:name=\"com.amazon.device.iap.ResponseReceiver\" "
                            "android:exported=\"true\" "
                            "android:permission=\"com.amazon.inapp.purchasing.Permission.NOTIFY\"> "
                            "<intent-filter><action android:name=\"com.amazon.inapp.purchasing.NOTIFY\"/>"
                            "</intent-filter></receiver>"
                        ),
                    ),
                )
        except Exception as exc:
            return Undecided(
                rule=self.id,
                reason=f"cannot read bundle: {exc}",
                evidence=Evidence(
                    file=ctx.aab_path, line=None,
                    found=str(exc), expected="readable .aab",
                ),
            )


# ---------------------------------------------------------------------------
# AMZ-IAP-04: <queries> contains com.amazon.venezia (targetSdk >= 30)
# ---------------------------------------------------------------------------

VENEZIA = "com.amazon.venezia"
SDK_TEST = "com.amazon.sdktestclient"

class AmzIap04(Rule):
    """AMZ-IAP-04 — <queries> lacks com.amazon.venezia (targetSdk ≥ 30)."""

    id = "AMZ-IAP-04"
    family = "amazon-iap"
    severity = "BLOCK"
    tier = 1

    def check_source(self, ctx: SourceContext) -> RuleResult:
        layout = ctx.get_layout()
        if layout is None or not _has_amazon_flavor(layout):
            return NotApplicable(rule=self.id, reason="no amazon flavor")

        for mod, flavor in _amazon_modules(layout):
            gradle = gradle_reader.read(mod.root, mod.build_gradle, ctx.repo_root)
            target_sdk_val = gradle.target_sdk
            if isinstance(target_sdk_val, gradle_reader.ResolvedValue):
                target_sdk = int(target_sdk_val.value) if target_sdk_val.value.isdigit() else 0
            else:
                target_sdk = 30  # assume ≥ 30 to be safe

            if target_sdk < 30:
                return NotApplicable(
                    rule=self.id,
                    reason=f"targetSdk {target_sdk} < 30; queries restriction does not apply",
                )

            flavor_paths = mod.flavor_manifests.get(flavor, [])
            merged = manifest_merger.merge(
                module_name=mod.name,
                main_manifest_path=mod.main_manifest,
                flavor_manifest_paths=flavor_paths,
                flavor=flavor,
            )

            venezia_found = False
            for elem in merged.elements:
                if elem.tag == "queries":
                    # queries is a top-level element; its children are parsed inline
                    # We look for it via the raw source file text
                    pass

            # Search source manifests directly for the package strings
            search_files = []
            if mod.main_manifest:
                search_files.append(mod.main_manifest)
            search_files.extend(mod.flavor_manifests.get(flavor, []))

            venezia_found = False
            sdk_test_found = False
            for mpath in search_files:
                try:
                    with open(mpath, "r", encoding="utf-8", errors="replace") as fh:
                        text = fh.read()
                    if VENEZIA in text:
                        venezia_found = True
                    if SDK_TEST in text:
                        sdk_test_found = True
                except OSError:
                    pass

            if venezia_found:
                main_rel = os.path.relpath(search_files[0], ctx.repo_root) if search_files else mod.name
                return Passed(
                    rule=self.id,
                    note=f"{VENEZIA} declared in source manifest queries",
                    decided_from="source",
                    evidence=Evidence(
                        file=main_rel,
                        line=1,
                        found=f"{VENEZIA} present",
                        expected=f"{VENEZIA} in <queries>",
                    ),
                )

            # Not found in source manifests — library AAR may contribute; undecidable
            main_rel = os.path.relpath(mod.main_manifest, ctx.repo_root) if mod.main_manifest else mod.name
            return Undecided(
                rule=self.id,
                reason=(
                    f"{VENEZIA} not found in source manifests — "
                    "a dependency AAR may still contribute it; re-run with --aab"
                ),
                evidence=Evidence(
                    file=main_rel,
                    line=1,
                    found="package absent from source manifests",
                    expected=f"{VENEZIA} in <queries> block",
                ),
            )

        return NotApplicable(rule=self.id, reason="no amazon flavor")

    def check_bundle(self, ctx: BundleContext) -> RuleResult:
        from storegreen.bundle.aab_reader import AabReader
        from storegreen.bundle.manifest_bytes import from_aab
        try:
            with AabReader(ctx.aab_path) as reader:
                mb = from_aab(reader)
                if mb is None:
                    return Undecided(
                        rule=self.id,
                        reason="manifest entry missing from bundle",
                        evidence=Evidence(
                            file="base/manifest/AndroidManifest.xml",
                            line=None, found="entry absent", expected="manifest present",
                        ),
                    )
                venezia_found, snip = mb.search(VENEZIA)
                if venezia_found:
                    return Passed(
                        rule=self.id,
                        note=f"{VENEZIA} declared in bundle manifest (presence only)",
                        decided_from="bundle",
                        evidence=Evidence(
                            file=mb.entry_path, line=None,
                            found=snip or VENEZIA,
                            expected=f"{VENEZIA} in <queries>",
                        ),
                    )
                return Finding(
                    rule=self.id,
                    family=self.family,
                    severity="BLOCK",
                    title=f"<queries> lacks {VENEZIA} in bundle manifest",
                    evidence=Evidence(
                        file=mb.entry_path, line=None,
                        found=f"{VENEZIA} absent",
                        expected=f"{VENEZIA} and {SDK_TEST} in <queries>",
                    ),
                    decided_from="bundle",
                    fix=FixHint(
                        automatic=False,
                        description=(
                            "Add to AndroidManifest.xml: <queries>"
                            f"<package android:name=\"{VENEZIA}\"/>"
                            f"<package android:name=\"{SDK_TEST}\"/>"
                            "</queries>"
                        ),
                    ),
                )
        except Exception as exc:
            return Undecided(
                rule=self.id,
                reason=f"cannot read bundle: {exc}",
                evidence=Evidence(
                    file=ctx.aab_path, line=None,
                    found=str(exc), expected="readable .aab",
                ),
            )


# ---------------------------------------------------------------------------
# AMZ-IAP-06: R8 keep rules for com.amazon.**
# ---------------------------------------------------------------------------

_KEEP_AMAZON = re.compile(r'-keep\s+class\s+com\.amazon\.\*\*', re.IGNORECASE)
_DONTWARN_AMAZON = re.compile(r'-dontwarn\s+com\.amazon\.\*\*', re.IGNORECASE)
_KEEPATTRIBUTES = re.compile(r'-keepattributes\s+\*Annotation\*', re.IGNORECASE)


class AmzIap06(Rule):
    """AMZ-IAP-06 — R8 strips Amazon SDK classes."""

    id = "AMZ-IAP-06"
    family = "amazon-iap"
    severity = "BLOCK"
    tier = 1

    def check_source(self, ctx: SourceContext) -> RuleResult:
        layout = ctx.get_layout()
        if layout is None or not _has_amazon_flavor(layout):
            return NotApplicable(rule=self.id, reason="no amazon flavor")

        for mod, flavor in _amazon_modules(layout):
            gradle = gradle_reader.read(mod.root, mod.build_gradle, ctx.repo_root)

            # Only relevant when isMinifyEnabled = true
            minify = gradle.is_minify_enabled
            if minify is None:
                return NotApplicable(
                    rule=self.id,
                    reason="isMinifyEnabled not found in build file; R8 check skipped",
                )
            if isinstance(minify, gradle_reader.ResolvedValue) and minify.value != "true":
                return NotApplicable(
                    rule=self.id,
                    reason="isMinifyEnabled = false; R8 does not run",
                )

            # Find proguard/rules files
            proguard_files = _find_proguard_files(mod, ctx.repo_root)
            if not proguard_files:
                rel_build = os.path.relpath(mod.build_gradle, ctx.repo_root)
                return Finding(
                    rule=self.id,
                    family=self.family,
                    severity="BLOCK",
                    title="isMinifyEnabled=true but no proguard/rules files found",
                    evidence=Evidence(
                        file=rel_build,
                        line=_minify_line(mod.build_gradle),
                        found="isMinifyEnabled = true, no rules files",
                        expected="-keep class com.amazon.** { *; } in a proguard rules file",
                    ),
                    decided_from="source",
                    fix=FixHint(
                        automatic=False,
                        description=(
                            "Add proguard-rules.pro with:\n"
                            "-keep class com.amazon.** { *; }\n"
                            "-dontwarn com.amazon.**\n"
                            "-keepattributes *Annotation*"
                        ),
                    ),
                )

            keep_ok = dontwarn_ok = keepattrib_ok = False
            evidence_file = proguard_files[0]
            for pf in proguard_files:
                try:
                    with open(pf, "r", encoding="utf-8", errors="replace") as fh:
                        text = fh.read()
                    if _KEEP_AMAZON.search(text):
                        keep_ok = True
                        evidence_file = pf
                    if _DONTWARN_AMAZON.search(text):
                        dontwarn_ok = True
                    if _KEEPATTRIBUTES.search(text):
                        keepattrib_ok = True
                except OSError:
                    pass

            if keep_ok and dontwarn_ok and keepattrib_ok:
                rel = os.path.relpath(evidence_file, ctx.repo_root)
                return Passed(
                    rule=self.id,
                    note="R8 keep rules for com.amazon.** found",
                    decided_from="source",
                    evidence=Evidence(
                        file=rel,
                        line=1,
                        found="-keep class com.amazon.** + -dontwarn + -keepattributes present",
                        expected="all three R8 keep rules present",
                    ),
                )

            missing = []
            if not keep_ok:
                missing.append("-keep class com.amazon.** { *; }")
            if not dontwarn_ok:
                missing.append("-dontwarn com.amazon.**")
            if not keepattrib_ok:
                missing.append("-keepattributes *Annotation*")

            rel = os.path.relpath(proguard_files[0], ctx.repo_root)
            return Finding(
                rule=self.id,
                family=self.family,
                severity="BLOCK",
                title=f"R8 keep rules incomplete — missing: {', '.join(missing)}",
                evidence=Evidence(
                    file=rel,
                    line=1,
                    found=f"missing: {'; '.join(missing)}",
                    expected="-keep class com.amazon.** { *; }  -dontwarn com.amazon.**  -keepattributes *Annotation*",
                ),
                decided_from="source",
                fix=FixHint(
                    automatic=False,
                    description=(
                        "Add to your proguard-rules.pro:\n"
                        + "\n".join(missing)
                    ),
                ),
            )

        return NotApplicable(rule=self.id, reason="no amazon flavor")

    def check_bundle(self, ctx: BundleContext) -> RuleResult:
        # R8 rules are a source-tree concern; no bundle check.
        return NotApplicable(rule=self.id, reason="R8 rules are checked from the source tree only")


# ---------------------------------------------------------------------------
# Helpers for AMZ-IAP-06
# ---------------------------------------------------------------------------

def _minify_line(build_gradle: str) -> int:
    try:
        with open(build_gradle, "r", encoding="utf-8", errors="replace") as fh:
            for li, line in enumerate(fh, 1):
                if "isMinifyEnabled" in line:
                    return li
    except OSError:
        pass
    return 1


def _find_proguard_files(mod: pl_mod.ModuleLayout, repo_root: str) -> List[str]:
    """Return absolute paths to all proguard/consumer-rules files for the module."""
    found: List[str] = []
    try:
        with open(mod.build_gradle, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return found

    # proguardFiles getDefaultProguardFile(...), 'proguard-rules.pro'
    # Look for single-quoted or double-quoted file references ending in .pro or .txt
    for m in re.finditer(r'["\']([^"\']+\.(?:pro|txt))["\']', text):
        fname = m.group(1)
        # Skip the Android SDK default file reference
        if fname.startswith("proguard-android"):
            continue
        candidate = os.path.join(mod.root, fname)
        if os.path.isfile(candidate):
            found.append(candidate)

    # Also look for consumer-rules.pro
    consumer = os.path.join(mod.root, "consumer-rules.pro")
    if os.path.isfile(consumer) and consumer not in found:
        found.append(consumer)

    # Fallback: any .pro file in the module root
    if not found:
        try:
            for entry in os.listdir(mod.root):
                if entry.endswith(".pro") and not entry.startswith("proguard-android"):
                    p = os.path.join(mod.root, entry)
                    if os.path.isfile(p):
                        found.append(p)
        except OSError:
            pass

    return found
