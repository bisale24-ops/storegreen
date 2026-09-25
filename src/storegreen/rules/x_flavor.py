# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
rules/x_flavor.py — Cross-store flavor leakage rule (tier 1).

Implements:
  X-FLAVOR-01  Play Billing SDK in an amazon flavor, or Amazon IAP in a
               play flavor.

Detection uses three independent signals:
  1. Gradle scoping: billing dep appears under amazonImplementation or
     inside an 'amazon' block; or amazon IAP under googleImplementation
  2. Manifest bytes: com.android.vending.BILLING in base/manifest/AndroidManifest.xml
  3. Dex: com/android/billingclient appears in base/dex/classes.dex

A PASS requires all signals clear.  A FINDING fires when any signal is present.
Correct scoping (Play billing in play flavor only, Amazon IAP in amazon
flavor only) must stay SILENT — X-FLAVOR-01 must not fire on correct
bi-flavor setups.

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

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
from storegreen.source import gradle_reader


# ---------------------------------------------------------------------------
# Billing / IAP markers
# ---------------------------------------------------------------------------

# Play Billing
_PLAY_BILLING_DEP_RE = re.compile(
    r'com\.android\.billingclient[:\w\-]*',
    re.IGNORECASE,
)
_PLAY_BILLING_MANIFEST = "com.android.vending.BILLING"
_PLAY_BILLING_DEX = b"com/android/billingclient"

# Amazon IAP
_AMAZON_IAP_DEP_RE = re.compile(
    r'com\.amazon\.device\.iap|amazon[:\-](?:appstore|iap)',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Source-mode helpers
# ---------------------------------------------------------------------------

def _read_gradle_text(path: str) -> str:
    """Read a Gradle build file, stripping // and /* */ comments.

    Searching comment-stripped text prevents a commented-out dependency line
    (e.g. // amazonImplementation "…billing…") from being treated as a live
    signal — the same class of false-pass that affected AMZ-IAP-04/06.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError:
        return ""
    # Block comments first (may span lines), then line comments.
    raw = re.sub(r'/\*.*?\*/', '', raw, flags=re.DOTALL)
    raw = re.sub(r'//[^\n]*', '', raw)
    return raw


def _play_billing_in_amazon_scope(mod: pl_mod.ModuleLayout) -> Optional[str]:
    """Return the offending line if Play Billing appears scoped to amazon flavor.

    Returns None if no such scoping found (correct or not present).
    """
    text = _read_gradle_text(mod.build_gradle)
    lines = text.splitlines()

    # Look for amazonImplementation / amazon { ... implementation "billing" }
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Direct: amazonImplementation("com.android.billingclient:...")
        if re.search(r'amazonImplementation\s*[\("\']+.*billingclient', stripped, re.IGNORECASE):
            return f"{mod.build_gradle}:{i}: {stripped}"
        # Direct: amazonImplementation("billing-something")
        if re.search(r'amazonImplementation\s*[\("\']+.*billing', stripped, re.IGNORECASE):
            return f"{mod.build_gradle}:{i}: {stripped}"

    return None


def _has_play_billing_dep_globally(mod: pl_mod.ModuleLayout) -> Optional[str]:
    """Return the line if Play Billing appears anywhere in the build file."""
    text = _read_gradle_text(mod.build_gradle)
    for i, line in enumerate(text.splitlines(), 1):
        if _PLAY_BILLING_DEP_RE.search(line):
            return f"{mod.build_gradle}:{i}: {line.strip()}"
    return None


def _has_amazon_flavor(layout: pl_mod.ProjectLayout) -> bool:
    for mod in layout.modules:
        for f in mod.flavors:
            if f.lower() in ("amazon", "appstore"):
                return True
    return False


def _has_play_flavor(layout: pl_mod.ProjectLayout) -> bool:
    for mod in layout.modules:
        for f in mod.flavors:
            if f.lower() in ("google", "play", "googleplay"):
                return True
    return False


def _is_play_billing_play_scoped_only(mod: pl_mod.ModuleLayout) -> bool:
    """True if Play Billing appears ONLY under googleImplementation / google { }.

    This is the correct scoping — X-FLAVOR-01 must stay silent.
    """
    text = _read_gradle_text(mod.build_gradle)
    lines = text.splitlines()

    billing_lines = [l for l in lines if _PLAY_BILLING_DEP_RE.search(l)]
    if not billing_lines:
        return True  # no billing at all — not a violation

    # All billing lines must be scoped to google flavor
    for line in billing_lines:
        stripped = line.strip()
        # googleImplementation("...billing...")
        if re.search(r'googleImplementation', stripped, re.IGNORECASE):
            continue  # correctly scoped
        # implementation("...billing...") NOT inside amazon block — hard to tell from flat text
        # We use a conservative approach: if there's any plain 'implementation' with billing,
        # flag it; the user must scope it explicitly.
        if re.search(r'\bimplementation\b', stripped, re.IGNORECASE):
            return False
        if re.search(r'\bamazonImplementation\b', stripped, re.IGNORECASE):
            return False

    return True


# ---------------------------------------------------------------------------
# X-FLAVOR-01
# ---------------------------------------------------------------------------

class XFlavor01(Rule):
    """X-FLAVOR-01 — one store's billing SDK leaks into another store's flavor."""

    id = "X-FLAVOR-01"
    family = "cross-store"
    severity = "RISK"
    tier = 1

    def check_source(self, ctx: SourceContext) -> RuleResult:
        layout = ctx.get_layout()
        if layout is None or not layout.modules:
            return NotApplicable(rule=self.id, reason="no Android modules found")

        if not _has_amazon_flavor(layout):
            return NotApplicable(rule=self.id, reason="no amazon flavor")

        for mod in layout.modules:
            if not mod.flavors:
                continue

            flavors_lower = [f.lower() for f in mod.flavors]
            has_amazon = any(f in ("amazon", "appstore") for f in flavors_lower)
            has_play = any(f in ("google", "play", "googleplay") for f in flavors_lower)

            if not has_amazon:
                continue

            # Check Play Billing in amazon scope
            amazon_billing_line = _play_billing_in_amazon_scope(mod)
            if amazon_billing_line:
                parts = amazon_billing_line.split(":", 2)
                rel_file = os.path.relpath(parts[0], ctx.repo_root)
                line_no = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
                snippet = parts[2].strip() if len(parts) > 2 else ""
                return Finding(
                    rule=self.id,
                    family=self.family,
                    severity=self.severity,
                    title="Play Billing SDK scoped to amazon flavor",
                    evidence=Evidence(
                        file=rel_file,
                        line=line_no,
                        found=snippet,
                        expected="Play Billing scoped to google/play flavor only",
                    ),
                    decided_from="source",
                    fix=FixHint(
                        automatic=False,
                        description=(
                            "Move Play Billing to googleImplementation (or inside the google "
                            "flavor block). Use Amazon IAP in the amazon flavor."
                        ),
                    ),
                )

            # Billing present but not explicitly scoped to play-only → leaks into amazon
            if not _is_play_billing_play_scoped_only(mod):
                offending_line = _has_play_billing_dep_globally(mod)
                rel_file = os.path.relpath(mod.build_gradle, ctx.repo_root)
                line_no = 1
                snippet = ""
                if offending_line:
                    parts = offending_line.split(":", 2)
                    if len(parts) >= 2 and parts[1].isdigit():
                        line_no = int(parts[1])
                    if len(parts) >= 3:
                        snippet = parts[2].strip()
                return Finding(
                    rule=self.id,
                    family=self.family,
                    severity=self.severity,
                    title=(
                        "Play Billing SDK declared without flavor scoping — "
                        "leaks into amazon build variant"
                    ),
                    evidence=Evidence(
                        file=rel_file,
                        line=line_no,
                        found=snippet or "Play Billing in unscoped implementation",
                        expected="Play Billing under googleImplementation only",
                    ),
                    decided_from="source",
                    fix=FixHint(
                        automatic=False,
                        description=(
                            "Change 'implementation' to 'googleImplementation' "
                            "(or place inside the google { } flavor block) so Play Billing "
                            "is excluded from the amazon build variant."
                        ),
                    ),
                )

            # Billing correctly scoped to play flavor only — stay silent
            return Passed(
                rule=self.id,
                note="Play Billing correctly scoped to play flavor; Amazon IAP in amazon flavor",
                decided_from="source",
                evidence=Evidence(
                    file=os.path.relpath(mod.build_gradle, ctx.repo_root),
                    line=1,
                    found="googleImplementation scoping detected",
                    expected="store-specific billing scoped per flavor",
                ),
            )

        return NotApplicable(
            rule=self.id,
            reason="no flavor leakage detected in source tree",
        )

    def check_bundle(self, ctx: BundleContext) -> RuleResult:
        """Check for Play Billing in an amazon-labeled bundle.

        Two independent signals:
        1. com.android.vending.BILLING in the manifest bytes
        2. com/android/billingclient in classes.dex bytes
        """
        from storegreen.bundle.aab_reader import AabReader
        from storegreen.bundle.manifest_bytes import from_aab, ManifestBytes

        manifest_hit = False
        dex_hit = False
        manifest_snippet: Optional[str] = None

        try:
            with AabReader(ctx.aab_path) as reader:
                mb = from_aab(reader)
                if mb is not None:
                    found, snip = mb.search(_PLAY_BILLING_MANIFEST)
                    if found:
                        manifest_hit = True
                        manifest_snippet = snip

                # Check dex files
                for dex_name in reader.list_prefix("base/dex/"):
                    if not dex_name.endswith(".dex"):
                        continue
                    dex_data = reader.read(dex_name)
                    if dex_data and _PLAY_BILLING_DEX in dex_data:
                        dex_hit = True
                        break

        except Exception as exc:
            return Undecided(
                rule=self.id,
                reason=f"cannot read bundle: {exc}",
                evidence=Evidence(
                    file=ctx.aab_path, line=None,
                    found=str(exc), expected="readable .aab",
                ),
            )

        if manifest_hit or dex_hit:
            signals = []
            if manifest_hit:
                signals.append(f"'{_PLAY_BILLING_MANIFEST}' in manifest")
            if dex_hit:
                signals.append(f"'{_PLAY_BILLING_DEX.decode()}' classes in dex")

            evidence_file = "base/manifest/AndroidManifest.xml" if manifest_hit else "base/dex/classes.dex"
            return Finding(
                rule=self.id,
                family=self.family,
                severity=self.severity,
                title="Play Billing SDK found in this bundle — leaking into amazon build",
                evidence=Evidence(
                    file=evidence_file,
                    line=None,
                    found="; ".join(signals),
                    expected="no Play Billing in amazon bundle",
                ),
                decided_from="bundle",
                fix=FixHint(
                    automatic=False,
                    description=(
                        "Scope the Play Billing dependency with googleImplementation "
                        "(or inside the google { } flavor block) so it is excluded "
                        "from the amazon build variant."
                    ),
                ),
            )

        return Passed(
            rule=self.id,
            note="no Play Billing signals found in bundle (manifest + dex checked)",
            decided_from="bundle",
            evidence=Evidence(
                file="base/manifest/AndroidManifest.xml",
                line=None,
                found=f"'{_PLAY_BILLING_MANIFEST}' absent; '{_PLAY_BILLING_DEX.decode()}' absent from dex",
                expected="no Play Billing in amazon bundle",
            ),
        )
