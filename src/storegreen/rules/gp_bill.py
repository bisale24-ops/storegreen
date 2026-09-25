# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
rules/gp_bill.py — Google Play Billing Library version rule (tier 1).

Implements:
  GP-BILL-01  Play Billing Library < 8 in a new app or update
              (deadline 31.08.2026, extension to 01.11.2026)

Detection: com.android.billingclient:billing* version in dependencies /
version catalog.  If the value is computed or unresolvable, return Undecided
with the line it gave up on.

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

import os
import re
from typing import Optional, Tuple

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
# Helpers
# ---------------------------------------------------------------------------

_BILLING_PREFIXES = (
    "com.android.billingclient:billing",
    "com.android.billingclient:billing-ktx",
)

# Minimum version required since 31.08.2026 (extension to 01.11.2026)
_REQUIRED_MAJOR = 8


def _parse_version_tuple(version: str) -> Optional[Tuple[int, ...]]:
    """Parse a version string like '7.1.1' or '8.0.0' into a tuple of ints.

    Returns None if the string cannot be parsed.
    """
    # Strip suffixes like -alpha01, -SNAPSHOT, etc.
    clean = re.sub(r'[-+].*$', '', version.strip())
    parts = clean.split(".")
    try:
        return tuple(int(p) for p in parts if p)
    except ValueError:
        return None


def _billing_dep_key(deps: dict) -> Optional[str]:
    """Return the first key in deps that looks like a Play Billing dependency."""
    for key in deps:
        lower = key.lower()
        for prefix in _BILLING_PREFIXES:
            if lower.startswith(prefix.lower()) or lower == "billing" or lower.startswith("billing"):
                return key
        # catalog alias forms: 'billing', 'android-billing', etc.
        if "billingclient" in lower or (lower in ("billing", "billing-ktx")):
            return key
    return None


# ---------------------------------------------------------------------------
# GP-BILL-01
# ---------------------------------------------------------------------------

class GpBill01(Rule):
    """GP-BILL-01 — Play Billing Library < 8."""

    id = "GP-BILL-01"
    family = "google-play-billing"
    severity = "BLOCK"
    tier = 1

    def check_source(self, ctx: SourceContext) -> RuleResult:
        layout = ctx.get_layout()
        if layout is None or not layout.modules:
            return NotApplicable(rule=self.id, reason="no Android modules found")

        billing_found = False

        for mod in layout.modules:
            gradle = gradle_reader.read(mod.root, mod.build_gradle, ctx.repo_root)
            rel_build = os.path.relpath(mod.build_gradle, ctx.repo_root)

            # Search dependencies for billing entries
            for dep_key, dep_val in gradle.dependencies.items():
                lower_key = dep_key.lower()
                is_billing = (
                    "billingclient" in lower_key
                    or lower_key.startswith("com.android.billingclient:")
                    or (lower_key in ("billing", "billing-ktx", "android-billing"))
                    or lower_key.endswith(":billing")
                    or lower_key.endswith(":billing-ktx")
                )
                if not is_billing:
                    continue

                billing_found = True

                if isinstance(dep_val, Undecided):
                    return Undecided(
                        rule=self.id,
                        reason=dep_val.reason,
                        evidence=dep_val.evidence,
                    )

                # ResolvedValue
                version_str = dep_val.value
                vtuple = _parse_version_tuple(version_str)
                if vtuple is None:
                    return Undecided(
                        rule=self.id,
                        reason=f"could not parse billing version: {version_str!r}",
                        evidence=Evidence(
                            file=os.path.relpath(dep_val.source_file, ctx.repo_root),
                            line=dep_val.source_line,
                            found=version_str,
                            expected="a parseable version string like 8.0.0",
                        ),
                    )

                major = vtuple[0]
                if major >= _REQUIRED_MAJOR:
                    return Passed(
                        rule=self.id,
                        note=f"Play Billing Library {version_str} ≥ {_REQUIRED_MAJOR}",
                        decided_from="source",
                        evidence=Evidence(
                            file=os.path.relpath(dep_val.source_file, ctx.repo_root),
                            line=dep_val.source_line,
                            found=f"billing version = {version_str}",
                            expected=f"≥ {_REQUIRED_MAJOR}.0.0",
                        ),
                    )

                return Finding(
                    rule=self.id,
                    family=self.family,
                    severity="BLOCK",
                    title=(
                        f"Play Billing Library {version_str} < {_REQUIRED_MAJOR} "
                        "(required since 31.08.2026, extension to 01.11.2026)"
                    ),
                    evidence=Evidence(
                        file=os.path.relpath(dep_val.source_file, ctx.repo_root),
                        line=dep_val.source_line,
                        found=f"billing version = {version_str}",
                        expected=f"≥ {_REQUIRED_MAJOR}.0.0",
                    ),
                    decided_from="source",
                    fix=FixHint(
                        automatic=False,
                        description=(
                            f"Migrate to Play Billing Library {_REQUIRED_MAJOR}+. "
                            "Note the v8 API removals before upgrading."
                        ),
                    ),
                )

        if not billing_found:
            return NotApplicable(
                rule=self.id,
                reason="no Play Billing Library dependency found",
            )

        # Should be unreachable
        return NotApplicable(rule=self.id, reason="no billing dependency resolved")

    def check_bundle(self, ctx: BundleContext) -> RuleResult:
        # Billing version is a source-tree concern.
        return NotApplicable(
            rule=self.id,
            reason="Play Billing version is read from the source tree; re-run with --repo",
        )
