# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
rules/gp_api.py — Google Play API level rule (tier 1).

Implements:
  GP-API-01  targetSdk below required level for the detected form factor

Form-factor table (spec §8, re-verified 25.09.2026):
  Phone/tablet (default) → required 36
  Wear OS                → required 35  (uses-feature android.hardware.type.watch)
  Android Automotive     → required 35  (uses-feature android.hardware.type.automotive)
  Android TV             → required 34  (uses-feature android.software.leanback OR
                                          LEANBACK_LAUNCHER intent-filter)
  Android XR             → required 34  (XR feature in manifest)

A module can be more than one form factor; take the LOWEST applicable requirement.
If form factor cannot be determined, assume phone and say so in evidence.

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

import os
import re
from typing import List, Optional, Tuple


def _strip_xml_comments(text: str) -> str:
    """Remove <!-- … --> XML comment blocks before searching raw manifest text."""
    return re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)

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
# Form-factor detection
# ---------------------------------------------------------------------------

# (feature_string, form_factor_name, required_target_sdk)
_FORM_FACTOR_TABLE: List[Tuple[str, str, int]] = [
    ("android.hardware.type.watch",      "wear",       35),
    ("android.hardware.type.automotive", "automotive", 35),
    ("android.software.leanback",        "tv",         34),
    ("LEANBACK_LAUNCHER",                "tv",         34),
    # XR: any XR-related feature or SDK marker
    ("android.software.xr",              "xr",         34),
    ("com.google.android.feature.ANDROID_XR", "xr",   34),
]

_PHONE_REQUIRED = 36


def _detect_form_factors(merged: manifest_merger.MergedManifest) -> List[Tuple[str, int]]:
    """Return list of (form_factor_name, required_sdk) detected in the manifest.

    Returns [("phone", 36)] if none detected (the default assumption).
    """
    detected: List[Tuple[str, int]] = []
    seen_names = set()

    for elem in merged.elements:
        # uses-feature elements
        if elem.tag == "uses-feature":
            name_val = (elem.android("name") or "").strip()
            for feature, ff_name, required in _FORM_FACTOR_TABLE:
                if feature in name_val and ff_name not in seen_names:
                    detected.append((ff_name, required))
                    seen_names.add(ff_name)
        # intent-filter with LEANBACK_LAUNCHER
        if elem.tag == "intent-filter":
            # Check child text or attributes for action name
            pass

    # Also scan raw manifest files for LEANBACK_LAUNCHER (may be inside activity).
    # Strip XML comments first so a commented-out feature declaration is not treated
    # as a signal — the same class of bug that bit AMZ-IAP-04 and AMZ-IAP-06.
    for source_file in merged.source_files:
        try:
            with open(source_file, "r", encoding="utf-8", errors="replace") as fh:
                text = _strip_xml_comments(fh.read())
            if "LEANBACK_LAUNCHER" in text and "tv" not in seen_names:
                detected.append(("tv", 34))
                seen_names.add("tv")
            if "android.software.leanback" in text and "tv" not in seen_names:
                detected.append(("tv", 34))
                seen_names.add("tv")
            if "android.hardware.type.watch" in text and "wear" not in seen_names:
                detected.append(("wear", 35))
                seen_names.add("wear")
            if "android.hardware.type.automotive" in text and "automotive" not in seen_names:
                detected.append(("automotive", 35))
                seen_names.add("automotive")
        except OSError:
            pass

    if not detected:
        detected.append(("phone", _PHONE_REQUIRED))
    return detected


# ---------------------------------------------------------------------------
# GP-API-01
# ---------------------------------------------------------------------------

class GpApi01(Rule):
    """GP-API-01 — targetSdk below required level for form factor."""

    id = "GP-API-01"
    family = "google-play-api"
    severity = "BLOCK"
    tier = 1

    def check_source(self, ctx: SourceContext) -> RuleResult:
        layout = ctx.get_layout()
        if layout is None or not layout.modules:
            return Undecided(
                rule=self.id,
                reason="no Android modules found in source tree",
                evidence=Evidence(
                    file=ctx.repo_root, line=1,
                    found="no modules", expected="at least one Android module",
                ),
            )

        for mod in layout.modules:
            gradle = gradle_reader.read(mod.root, mod.build_gradle, ctx.repo_root)
            target_sdk_resolved = gradle.target_sdk

            # Undecided if we cannot resolve targetSdk
            if target_sdk_resolved is None:
                if mod.main_manifest:
                    # Try manifest fallback
                    merged = manifest_merger.merge(
                        module_name=mod.name,
                        main_manifest_path=mod.main_manifest,
                    )
                    if merged.target_sdk is not None:
                        target_sdk_int = merged.target_sdk
                        source_file = mod.main_manifest
                        source_line = 1
                    else:
                        rel = os.path.relpath(mod.build_gradle, ctx.repo_root)
                        return Undecided(
                            rule=self.id,
                            reason="targetSdk not found in build file or manifest",
                            evidence=Evidence(
                                file=rel, line=1,
                                found="targetSdk absent",
                                expected="targetSdk integer value",
                            ),
                        )
                else:
                    rel = os.path.relpath(mod.build_gradle, ctx.repo_root)
                    return Undecided(
                        rule=self.id,
                        reason="targetSdk not found in build file",
                        evidence=Evidence(
                            file=rel, line=1,
                            found="targetSdk absent",
                            expected="targetSdk integer value",
                        ),
                    )
            elif isinstance(target_sdk_resolved, Undecided):
                return Undecided(
                    rule=self.id,
                    reason=target_sdk_resolved.reason,
                    evidence=target_sdk_resolved.evidence,
                )
            else:
                # ResolvedValue
                if not target_sdk_resolved.value.isdigit():
                    return Undecided(
                        rule=self.id,
                        reason=f"targetSdk value {target_sdk_resolved.value!r} is not a plain integer",
                        evidence=Evidence(
                            file=os.path.relpath(target_sdk_resolved.source_file, ctx.repo_root),
                            line=target_sdk_resolved.source_line,
                            found=target_sdk_resolved.value,
                            expected="integer targetSdk",
                        ),
                    )
                target_sdk_int = int(target_sdk_resolved.value)
                source_file = target_sdk_resolved.source_file
                source_line = target_sdk_resolved.source_line

            # Detect form factor from manifest
            form_factors: List[Tuple[str, int]] = [("phone", _PHONE_REQUIRED)]
            if mod.main_manifest:
                merged = manifest_merger.merge(
                    module_name=mod.name,
                    main_manifest_path=mod.main_manifest,
                )
                form_factors = _detect_form_factors(merged)

            # Take the lowest required SDK across all detected form factors
            deciding_ff, required_sdk = min(form_factors, key=lambda x: x[1])
            ff_names = [f for f, _ in form_factors]

            rel_source = os.path.relpath(source_file, ctx.repo_root)

            if target_sdk_int >= required_sdk:
                return Passed(
                    rule=self.id,
                    note=(
                        f"targetSdk {target_sdk_int} ≥ {required_sdk} "
                        f"(required for form factor: {deciding_ff})"
                    ),
                    decided_from="source",
                    evidence=Evidence(
                        file=rel_source,
                        line=source_line,
                        found=f"targetSdk = {target_sdk_int}",
                        expected=f"≥ {required_sdk} for {deciding_ff}",
                    ),
                )

            return Finding(
                rule=self.id,
                family=self.family,
                severity="BLOCK",
                title=(
                    f"targetSdk {target_sdk_int} is below the required level "
                    f"{required_sdk} for {deciding_ff} (deadline 31.08.2026, "
                    "extension to 01.11.2026)"
                ),
                evidence=Evidence(
                    file=rel_source,
                    line=source_line,
                    found=f"targetSdk = {target_sdk_int}",
                    expected=(
                        f"≥ {required_sdk} for {deciding_ff}; "
                        f"detected form factors: {', '.join(ff_names)}"
                    ),
                ),
                decided_from="source",
                fix=FixHint(
                    automatic=False,
                    description=(
                        f"Raise targetSdk to {required_sdk} in build.gradle, "
                        "then run behaviour-change checks."
                    ),
                ),
            )

        return NotApplicable(rule=self.id, reason="no Android modules found")

    def check_bundle(self, ctx: BundleContext) -> RuleResult:
        # targetSdk is a source-tree concern; bundle mode defers to source.
        return NotApplicable(
            rule=self.id,
            reason="targetSdk is read from the source tree; re-run with --repo",
        )
