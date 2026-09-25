# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
runner.py — orchestrates a scan and produces the typed report object.

Runs every registered rule in source mode (if --repo given), bundle mode
(if --aab given), or both.  Merges results; sets decided_from="both" when
both modes produced a verdict for the same rule.

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from storegreen.rules.base import (
    BundleContext,
    Finding,
    NotApplicable,
    Passed,
    Rule,
    RuleResult,
    SourceContext,
    Undecided,
)
from storegreen.rules.smoke import SmokeRule
from storegreen.rules.amz_iap import AmzIap01, AmzIap03, AmzIap04, AmzIap06
from storegreen.rules.gp_api import GpApi01
from storegreen.rules.gp_bill import GpBill01
from storegreen.rules.gp_16kb import GpSixteenKb01
from storegreen.rules.x_flavor import XFlavor01
from storegreen.source import project_layout as pl_mod
from storegreen.bundle.aab_reader import AabReader


# ---------------------------------------------------------------------------
# All registered rules (tier 1 first, tier 2 when implemented)
# ---------------------------------------------------------------------------

ALL_RULES: List[Rule] = [
    SmokeRule(),
    # Tier 1: Amazon IAP
    AmzIap01(),
    AmzIap03(),
    AmzIap04(),
    AmzIap06(),
    # Tier 1: Google Play
    GpApi01(),
    GpBill01(),
    GpSixteenKb01(),
    # Tier 1: Cross-store
    XFlavor01(),
]

# ---------------------------------------------------------------------------
# Tier-2 rules that are not implemented yet (listed in every report)
# ---------------------------------------------------------------------------

NOT_IMPLEMENTED_IDS: List[str] = [
    "AMZ-IAP-02",
    "AMZ-IAP-05",
    "AMZ-IAP-07",
    "AMZ-IAP-08",
    "GP-API-02",
    "GP-BILL-02",
    "GP-PERM-01",
    "GP-PERM-02",
    "GP-PRIV-01",
    "GP-DS-01",
    "GP-EXP-01",
    "X-SIGN-01",
    "X-VER-01",
]


# ---------------------------------------------------------------------------
# Report data class
# ---------------------------------------------------------------------------

@dataclass
class ScanReport:
    """The typed report object produced by Runner.scan()."""
    repo_root: Optional[str]
    aab_path: Optional[str]
    modules: List[str]
    form_factors: List[str]
    elapsed_seconds: float

    findings: List[Finding] = field(default_factory=list)
    undecided: List[Undecided] = field(default_factory=list)
    passed: List[Passed] = field(default_factory=list)
    not_applicable: List[NotApplicable] = field(default_factory=list)
    not_implemented: List[str] = field(default_factory=list)  # rule ids

    # --fix fields (§12): populated by cli.py after applying repairs
    fix_applied: bool = False
    findings_before_fix: List[Finding] = field(default_factory=list)

    @property
    def summary(self) -> Dict[str, int]:
        block = sum(1 for f in self.findings if f.severity == "BLOCK")
        risk  = sum(1 for f in self.findings if f.severity == "RISK")
        warn  = sum(1 for f in self.findings if f.severity == "WARN")
        # "decided" = Finding + Passed (rule ran and reached a verdict)
        decided = len(self.findings) + len(self.passed)
        return {
            "block": block,
            "risk": risk,
            "warn": warn,
            "decided": decided,
            "undecidable": len(self.undecided),
            "passed": len(self.passed),
            "not_applicable": len(self.not_applicable),
            "not_implemented": len(self.not_implemented),
        }

    @property
    def has_block(self) -> bool:
        return any(f.severity == "BLOCK" for f in self.findings)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class Runner:
    def __init__(
        self,
        rules: Optional[List[Rule]] = None,
        only: Optional[List[str]] = None,
    ) -> None:
        """
        Parameters
        ----------
        rules : list of Rule instances to run (defaults to ALL_RULES)
        only  : if given, only run rules whose id or family starts with one
                of these strings
        """
        self._rules = rules if rules is not None else ALL_RULES
        self._only = [o.upper() for o in only] if only else None

    def _is_selected(self, rule: Rule) -> bool:
        if self._only is None:
            return True
        for prefix in self._only:
            if rule.id.upper().startswith(prefix) or rule.family.upper().startswith(prefix.replace("-", "_")):
                return True
        return False

    def scan(
        self,
        repo_root: Optional[str] = None,
        aab_path: Optional[str] = None,
    ) -> ScanReport:
        """Run the selected rules and return a ScanReport."""
        t0 = time.monotonic()

        # ------------------------------------------------------------------
        # Build contexts
        # ------------------------------------------------------------------
        source_ctx: Optional[SourceContext] = None
        bundle_ctx: Optional[BundleContext] = None

        modules: List[str] = []
        form_factors: List[str] = []

        if repo_root:
            repo_root = os.path.abspath(repo_root)
            layout = pl_mod.discover(repo_root)
            modules = [m.name for m in layout.modules]
            source_ctx = SourceContext(
                repo_root=repo_root,
                modules=modules,
                _layout=layout,
            )

        if aab_path:
            aab_path = os.path.abspath(aab_path)
            bundle_ctx = BundleContext(aab_path=aab_path)

        report = ScanReport(
            repo_root=repo_root,
            aab_path=aab_path,
            modules=modules,
            form_factors=form_factors or ["phone"],
            elapsed_seconds=0.0,
        )

        # ------------------------------------------------------------------
        # Run rules
        # ------------------------------------------------------------------
        # Collect per-rule results from both modes, then reconcile
        source_results: Dict[str, RuleResult] = {}
        bundle_results: Dict[str, RuleResult] = {}

        for rule in self._rules:
            if not self._is_selected(rule):
                continue

            if source_ctx is not None:
                try:
                    source_results[rule.id] = rule.check_source(source_ctx)
                except Exception as exc:  # noqa: BLE001
                    source_results[rule.id] = Undecided(
                        rule=rule.id,
                        reason=f"internal error in check_source: {exc}",
                        evidence=__import__("storegreen.rules.base", fromlist=["Evidence"]).Evidence(
                            file=repo_root or "?", line=None, found=str(exc), expected="no exception"
                        ),
                    )

            if bundle_ctx is not None:
                try:
                    bundle_results[rule.id] = rule.check_bundle(bundle_ctx)
                except Exception as exc:  # noqa: BLE001
                    bundle_results[rule.id] = Undecided(
                        rule=rule.id,
                        reason=f"internal error in check_bundle: {exc}",
                        evidence=__import__("storegreen.rules.base", fromlist=["Evidence"]).Evidence(
                            file=aab_path or "?", line=None, found=str(exc), expected="no exception"
                        ),
                    )

        # ------------------------------------------------------------------
        # Merge: for each rule, reconcile source + bundle result
        # ------------------------------------------------------------------
        all_rule_ids = {r.id for r in self._rules if self._is_selected(r)}

        for rule_id in all_rule_ids:
            src = source_results.get(rule_id)
            bnd = bundle_results.get(rule_id)

            if src is None and bnd is None:
                continue

            # When only one mode ran, use it directly
            if src is not None and bnd is None:
                _add_result(report, src)
                continue
            if bnd is not None and src is None:
                _add_result(report, bnd)
                continue

            # Both ran: prefer Finding > Undecided > Passed > NotApplicable
            _add_merged(report, src, bnd)  # type: ignore

        # Populate not_implemented with tier-2 rule ids
        report.not_implemented = list(NOT_IMPLEMENTED_IDS)

        report.elapsed_seconds = time.monotonic() - t0
        return report


def _add_result(report: ScanReport, result: RuleResult) -> None:
    if isinstance(result, Finding):
        report.findings.append(result)
    elif isinstance(result, Undecided):
        report.undecided.append(result)
    elif isinstance(result, Passed):
        report.passed.append(result)
    elif isinstance(result, NotApplicable):
        report.not_applicable.append(result)


def _add_merged(report: ScanReport, src: RuleResult, bnd: RuleResult) -> None:
    """Reconcile source + bundle results for the same rule."""
    # If both are Findings, merge evidence and mark decided_from="both"
    if isinstance(src, Finding) and isinstance(bnd, Finding):
        # Use the more severe one; if equal, prefer source evidence
        merged = Finding(
            rule=src.rule,
            family=src.family,
            severity=src.severity,
            title=src.title,
            evidence=src.evidence,
            decided_from="both",
            fix=src.fix,
        )
        report.findings.append(merged)
        return

    # Finding beats everything
    if isinstance(src, Finding):
        src_copy = Finding(
            rule=src.rule, family=src.family, severity=src.severity,
            title=src.title, evidence=src.evidence, decided_from="both", fix=src.fix
        )
        report.findings.append(src_copy)
        return
    if isinstance(bnd, Finding):
        bnd_copy = Finding(
            rule=bnd.rule, family=bnd.family, severity=bnd.severity,
            title=bnd.title, evidence=bnd.evidence, decided_from="both", fix=bnd.fix
        )
        report.findings.append(bnd_copy)
        return

    # Undecided beats Passed/NotApplicable
    if isinstance(src, Undecided) or isinstance(bnd, Undecided):
        u = src if isinstance(src, Undecided) else bnd
        report.undecided.append(u)  # type: ignore
        return

    # Both Passed — merge notes
    if isinstance(src, Passed) and isinstance(bnd, Passed):
        report.passed.append(Passed(
            rule=src.rule,
            note=f"{src.note}; {bnd.note}",
            decided_from="both",
            evidence=src.evidence or bnd.evidence,
        ))
        return

    # Passed beats NotApplicable
    if isinstance(src, Passed):
        report.passed.append(src)
        return
    if isinstance(bnd, Passed):
        report.passed.append(bnd)
        return

    # Both NotApplicable
    if isinstance(src, NotApplicable):
        report.not_applicable.append(src)
    elif isinstance(bnd, NotApplicable):
        report.not_applicable.append(bnd)
