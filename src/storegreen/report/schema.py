# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
report/schema.py — serialize a ScanReport to the canonical JSON dict.

The dict produced here is the contract between the tool and its consumers
(CLI --json, HTML report, tests).  It is typed so json_report.py and
html_report.py cannot diverge.

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from storegreen.rules.base import Evidence, Finding, NotApplicable, Passed, Undecided
from storegreen.runner import ScanReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _evidence_dict(e: Optional[Evidence]) -> Optional[Dict[str, Any]]:
    if e is None:
        return None
    return {
        "file": e.file,
        "line": e.line,
        "found": e.found,
        "expected": e.expected,
    }


def _finding_dict(f: Finding) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "rule": f.rule,
        "family": f.family,
        "severity": f.severity,
        "title": f.title,
        "evidence": _evidence_dict(f.evidence),
        "decided_from": f.decided_from,
    }
    if f.fix is not None:
        d["fix"] = {
            "automatic": f.fix.automatic,
            "description": f.fix.description,
        }
    else:
        d["fix"] = None
    return d


def _undecided_dict(u: Undecided) -> Dict[str, Any]:
    return {
        "rule": u.rule,
        "reason": u.reason,
        "evidence": _evidence_dict(u.evidence),
    }


def _passed_dict(p: Passed) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "rule": p.rule,
        "note": p.note,
        "decided_from": p.decided_from,
    }
    if p.evidence is not None:
        d["evidence"] = _evidence_dict(p.evidence)
    return d


def _not_applicable_dict(n: NotApplicable) -> Dict[str, Any]:
    return {"rule": n.rule, "reason": n.reason}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def to_dict(report: ScanReport, version: str = "0.1.0") -> Dict[str, Any]:
    """Convert a ScanReport to the canonical JSON-serializable dict."""
    summary = report.summary
    summary["seconds"] = round(report.elapsed_seconds, 3)

    scanned: Dict[str, Any] = {
        "repo": report.repo_root,
        "aab": report.aab_path,
        "modules": report.modules,
        "form_factors": report.form_factors,
    }

    return {
        "tool": "storegreen",
        "version": version,
        "scanned": scanned,
        "summary": summary,
        "findings": [_finding_dict(f) for f in report.findings],
        "undecided": [_undecided_dict(u) for u in report.undecided],
        "passed": [_passed_dict(p) for p in report.passed],
        "not_applicable": [_not_applicable_dict(n) for n in report.not_applicable],
        "not_implemented": list(report.not_implemented),
    }
