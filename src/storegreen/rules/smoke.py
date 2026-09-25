# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
rules/smoke.py — one trivial rule that proves the pipeline works end to end.

SMOKE-01: verify the repo root is a readable directory.
This rule always produces a Passed result when the root exists (which it
must for the runner to get this far), and is the single rule that exercises
the full path from SourceContext through to a RuleResult in the JSON output.

It is tier 1 only for pipeline testing; it will be replaced by the real
rules in Task 3 and kept as a no-op sanity check thereafter.
"""

from __future__ import annotations

import os

from storegreen.rules.base import (
    BundleContext,
    Evidence,
    Finding,
    NotApplicable,
    Passed,
    Rule,
    RuleResult,
    SourceContext,
    Undecided,
)


class SmokeRule(Rule):
    """SMOKE-01 — trivial pipeline smoke test.

    Source mode: passes if the repo root is a readable directory.
    Bundle mode: passes if the .aab file is readable.
    """

    id = "SMOKE-01"
    family = "smoke"
    severity = "BLOCK"  # if this fires as a Finding, the build is definitely broken
    tier = 1

    def check_source(self, ctx: SourceContext) -> RuleResult:
        if os.path.isdir(ctx.repo_root):
            return Passed(
                rule=self.id,
                note=f"repo root is a readable directory: {ctx.repo_root}",
                decided_from="source",
                evidence=Evidence(
                    file=ctx.repo_root,
                    line=None,
                    found="directory exists",
                    expected="readable directory",
                ),
            )
        return Finding(
            rule=self.id,
            family=self.family,
            severity=self.severity,
            title="repo root is not a readable directory",
            evidence=Evidence(
                file=ctx.repo_root,
                line=None,
                found="missing or unreadable",
                expected="readable directory",
            ),
            decided_from="source",
        )

    def check_bundle(self, ctx: BundleContext) -> RuleResult:
        if os.path.isfile(ctx.aab_path):
            return Passed(
                rule=self.id,
                note=f"bundle file is readable: {ctx.aab_path}",
                decided_from="bundle",
                evidence=Evidence(
                    file=ctx.aab_path,
                    line=None,
                    found="file exists",
                    expected="readable .aab file",
                ),
            )
        return Finding(
            rule=self.id,
            family=self.family,
            severity=self.severity,
            title="bundle file is not readable",
            evidence=Evidence(
                file=ctx.aab_path,
                line=None,
                found="missing or unreadable",
                expected="readable .aab file",
            ),
            decided_from="bundle",
        )
