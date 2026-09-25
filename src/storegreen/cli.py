# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
cli.py — command-line entry point for StoreGreen.

Implements the interface pinned in prep/interface.md exactly:
  exit 0 — nothing blocks
  exit 1 — at least one BLOCK finding
  exit 2 — cannot run (bad path)

Nothing writes to stdout in --json mode except the JSON.
Nothing writes to stderr on a successful run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from storegreen import __version__
from storegreen.runner import Runner
from storegreen.report.json_report import to_json
from storegreen.report.html_report import to_html
from storegreen.fixer import apply_fixes
from storegreen.explainer import explain, ExplainResult


# ---------------------------------------------------------------------------
# ANSI colours (suppressed by --no-colour or non-tty)
# ---------------------------------------------------------------------------

def _use_colour(force_off: bool) -> bool:
    if force_off:
        return False
    return sys.stdout.isatty()


class _C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[31m"
    YELLOW = "\033[33m"
    BLUE   = "\033[34m"
    GREEN  = "\033[32m"
    GREY   = "\033[90m"


def _colour(text: str, code: str, use: bool) -> str:
    return f"{code}{text}{_C.RESET}" if use else text


# ---------------------------------------------------------------------------
# Text renderer
# ---------------------------------------------------------------------------

_SEV_CODE = {"BLOCK": _C.RED + _C.BOLD, "RISK": _C.YELLOW, "WARN": _C.BLUE}


def _render_text(report, use_colour: bool) -> str:
    from storegreen.report.schema import to_dict
    d = to_dict(report)
    lines: List[str] = []
    summary = d["summary"]

    # Header
    modules = ", ".join(d["scanned"]["modules"]) or "—"
    ffs = ", ".join(d["scanned"]["form_factors"]) or "phone"
    lines.append(
        _colour(f"StoreGreen v{__version__}", _C.BOLD, use_colour)
        + f"  modules: {modules}  form_factor: {ffs}  {summary['seconds']}s"
    )

    # Summary line
    block = summary["block"]
    risk  = summary["risk"]
    warn  = summary["warn"]
    unk   = summary["undecidable"]
    pas   = summary["passed"]
    decided = summary.get("decided", pas)
    na    = summary.get("not_applicable", 0)
    ni    = summary.get("not_implemented", 0)
    total_rules = 21  # spec §11: 21 rules total

    verdict = (
        _colour("✓ no BLOCKs", _C.GREEN, use_colour)
        if block == 0
        else _colour(f"✗ {block} BLOCK", _C.RED + _C.BOLD, use_colour)
    )
    lines.append(
        f"{verdict}  "
        + _colour(f"{risk} RISK", _C.YELLOW, use_colour) + "  "
        + _colour(f"{warn} WARN", _C.BLUE, use_colour) + "  "
        + _colour(f"{unk} undecidable", _C.GREY, use_colour) + "  "
        + _colour(f"{pas} passed", _C.GREEN, use_colour)
    )
    # Decidability counters (spec §11)
    lines.append(
        _colour(
            f"{total_rules} rules  ·  8 implemented  ·  "
            f"{decided} decided  ·  {unk} undecidable  ·  "
            f"{na} not applicable  ·  {ni} not implemented",
            _C.GREY, use_colour,
        )
    )
    lines.append("")

    # Findings
    for f in d["findings"]:
        sev_str = _colour(f["severity"], _SEV_CODE.get(f["severity"], ""), use_colour)
        lines.append(f"  {sev_str}  {_colour(f['rule'], _C.BOLD, use_colour)}  {f['title']}")
        ev = f.get("evidence") or {}
        file_ = ev.get("file", "")
        line_ = ev.get("line")
        loc = f"{file_}:{line_}" if line_ else file_
        lines.append(f"         at: {loc}")
        lines.append(f"      found: {ev.get('found', '')}")
        lines.append(f"   expected: {ev.get('expected', '')}")
        if f.get("fix"):
            auto = "automatic" if f["fix"].get("automatic") else "manual"
            lines.append(f"        fix: [{auto}] {f['fix'].get('description', '')}")
        lines.append(f"       from: {f.get('decided_from', '?')}")
        lines.append("")

    # Undecided
    if d["undecided"]:
        lines.append(_colour(f"── UNDECIDED ({len(d['undecided'])}) ──", _C.GREY, use_colour))
        for u in d["undecided"]:
            ev = u.get("evidence") or {}
            file_ = ev.get("file", "")
            line_ = ev.get("line")
            loc = f"{file_}:{line_}" if line_ else file_
            lines.append(f"  {_colour(u['rule'], _C.BOLD, use_colour)} · {u['reason']}")
            lines.append(f"    gave up at {loc}")
        lines.append("")

    # Passed (brief)
    if d["passed"]:
        pas_list = ", ".join(p["rule"] for p in d["passed"])
        lines.append(_colour(f"── PASSED ({len(d['passed'])}) ──", _C.GREEN, use_colour))
        lines.append(f"  {pas_list}")
        lines.append("")

    # Not applicable
    if d["not_applicable"]:
        na_list = ", ".join(n["rule"] for n in d["not_applicable"])
        lines.append(_colour(f"── NOT APPLICABLE ({len(d['not_applicable'])}) ──", _C.GREY, use_colour))
        lines.append(f"  {na_list}")
        lines.append("")

    # Not implemented
    if d["not_implemented"]:
        ni_list = ", ".join(d["not_implemented"])
        lines.append(_colour(f"── NOT IMPLEMENTED ({len(d['not_implemented'])}) ──", _C.GREY, use_colour))
        lines.append(f"  {ni_list}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# --explain-rejection renderer
# ---------------------------------------------------------------------------

def _render_explain(result: ExplainResult, use_colour: bool) -> str:
    lines: List[str] = []
    lines.append(
        _colour("── explain-rejection ──", _C.BOLD, use_colour)
        + f"  source: {result.email_file}"
    )
    lines.append("")

    if result.matched_symptoms:
        for mapping in result.matched_symptoms:
            lines.append(
                _colour(f"SYMPTOM  {mapping.symptom_label}", _C.BOLD, use_colour)
            )
            lines.append(
                _colour("  quote:    ", _C.GREY, use_colour)
                + mapping.sentence[:120]
            )
            if mapping.violated:
                rules_str = "  ".join(
                    _colour(r, _C.RED + _C.BOLD, use_colour) for r in mapping.violated
                )
                lines.append(
                    _colour("  violated here:  ", _C.RED + _C.BOLD, use_colour) + rules_str
                )
            if mapping.undecided:
                rules_str = "  ".join(
                    _colour(r, _C.GREY, use_colour) for r in mapping.undecided
                )
                lines.append(
                    _colour("  undecided here: ", _C.GREY, use_colour) + rules_str
                    + _colour("  (re-run with --aab for full check)", _C.GREY, use_colour)
                )
            if mapping.clean:
                rules_str = "  ".join(
                    _colour(r, _C.GREEN, use_colour) for r in mapping.clean
                )
                lines.append(
                    _colour("  clean here:     ", _C.GREEN, use_colour) + rules_str
                )
            lines.append("")

    if result.unmapped_sentences:
        lines.append(_colour(
            f"── {len(result.unmapped_sentences)} sentence(s) map to no rule ──",
            _C.GREY, use_colour,
        ))
        for s in result.unmapped_sentences:
            lines.append(_colour(f"  {s[:100]}", _C.GREY, use_colour))
        lines.append("")

    if not result.matched_symptoms:
        lines.append(_colour(
            "No sentences in the e-mail mapped to any known symptom.",
            _C.GREY, use_colour,
        ))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="storegreen",
        description="Store rejection preflight for Android apps.",
    )
    p.add_argument("--repo", metavar="PATH", default=".",
                   help="source tree to scan (default: .)")
    p.add_argument("--aab", metavar="FILE", default=None,
                   help="built AAB to scan instead of, or in addition to, the tree")
    p.add_argument("--only", metavar="RULE", action="append", default=None,
                   help="run one rule or family; repeatable (e.g. AMZ-IAP, GP-API)")
    p.add_argument("--fix", action="store_true",
                   help="apply deterministic repairs then re-scan and report both")
    p.add_argument("--explain-rejection", metavar="F", dest="explain_rejection",
                   help="read a store rejection e-mail and map it to rule ids")
    p.add_argument("--last-version", metavar="N", dest="last_version", type=int,
                   help="versionCode already uploaded, for X-VER-01")
    p.add_argument("--json", action="store_true", dest="json_output",
                   help="machine-readable JSON to stdout, nothing else on stdout")
    p.add_argument("--html", metavar="PATH", default=None,
                   help="write one offline HTML report to PATH")
    p.add_argument("--quiet", action="store_true",
                   help="exit code only")
    p.add_argument("--no-colour", action="store_true", dest="no_colour",
                   help="plain text, no ANSI colours")
    p.add_argument("--version", action="version", version=f"storegreen {__version__}")
    return p


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # ------------------------------------------------------------------
    # Validate paths  (exit 2 if unreadable)
    # ------------------------------------------------------------------
    repo_root: Optional[str] = None
    aab_path: Optional[str] = None

    # Only validate --repo if it was explicitly given OR if --aab was not given
    repo_given = "--repo" in (argv or sys.argv[1:]) or args.repo != "."
    if args.aab and not repo_given:
        # bundle-only mode: don't require a repo
        repo_root = None
    else:
        repo_root = os.path.abspath(args.repo)
        if not os.path.isdir(repo_root):
            msg = f"storegreen: error: path is not a directory: {repo_root}"
            if not args.json_output:
                print(msg, file=sys.stderr)
            return 2

    if args.aab:
        aab_path = os.path.abspath(args.aab)
        if not os.path.isfile(aab_path):
            msg = f"storegreen: error: AAB file not found: {aab_path}"
            if not args.json_output:
                print(msg, file=sys.stderr)
            return 2

    # ------------------------------------------------------------------
    # Run (initial scan)
    # ------------------------------------------------------------------
    runner = Runner(only=args.only)
    report = runner.scan(repo_root=repo_root, aab_path=aab_path)

    # ------------------------------------------------------------------
    # --fix: apply deterministic repairs, re-scan, attach before/after
    # ------------------------------------------------------------------
    fix_diff: str = ""
    if args.fix and repo_root:
        findings_before = list(report.findings)
        fix_diff, applied = apply_fixes(report, repo_root)

        if applied:
            # Re-scan so findings reflect the repaired files
            report_after = runner.scan(repo_root=repo_root, aab_path=aab_path)
            report_after.fix_applied = True
            report_after.findings_before_fix = findings_before
            report = report_after

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    if args.html:
        html_content = to_html(report)
        try:
            with open(args.html, "w", encoding="utf-8") as fh:
                fh.write(html_content)
        except OSError as exc:
            if not args.json_output:
                print(f"storegreen: error writing HTML: {exc}", file=sys.stderr)
            return 2

    if args.json_output:
        # Spec: nothing else on stdout in --json mode
        print(to_json(report))
        return 1 if report.has_block else 0

    # ------------------------------------------------------------------
    # --explain-rejection (runs after the scan so it can intersect results)
    # ------------------------------------------------------------------
    if args.explain_rejection:
        email_path = os.path.abspath(args.explain_rejection)
        if not os.path.isfile(email_path):
            msg = f"storegreen: error: rejection e-mail not found: {email_path}"
            if not args.json_output:
                print(msg, file=sys.stderr)
            return 2
        try:
            explain_result = explain(email_path, report)
        except ValueError as exc:
            if not args.json_output:
                print(f"storegreen: error: {exc}", file=sys.stderr)
            return 2

        if args.json_output:
            import json as _json
            out = {
                "explain_rejection": {
                    "email_file": explain_result.email_file,
                    "matched_symptoms": [
                        {
                            "symptom": m.symptom_label,
                            "quote": m.sentence,
                            "violated": m.violated,
                            "undecided": m.undecided,
                            "clean": m.clean,
                        }
                        for m in explain_result.matched_symptoms
                    ],
                    "unmapped_sentences": explain_result.unmapped_sentences,
                }
            }
            print(_json.dumps(out, indent=2, ensure_ascii=False))
            return 1 if report.has_block else 0

        if not args.quiet:
            use_colour = _use_colour(args.no_colour)
            print(_render_explain(explain_result, use_colour))
        return 1 if report.has_block else 0

    if not args.quiet:
        use_colour = _use_colour(args.no_colour)
        # Show the unified diff first when --fix was applied
        if fix_diff:
            print(_colour("── diff (applied by --fix) ──", _C.GREY, use_colour))
            print(fix_diff)
        print(_render_text(report, use_colour))
        # Show before/after finding counts when --fix was applied
        if report.fix_applied:
            before_block = sum(1 for f in report.findings_before_fix if f.severity == "BLOCK")
            after_block  = sum(1 for f in report.findings if f.severity == "BLOCK")
            before_risk  = sum(1 for f in report.findings_before_fix if f.severity == "RISK")
            after_risk   = sum(1 for f in report.findings if f.severity == "RISK")
            print(_colour(
                f"── before fix: {before_block} BLOCK  {before_risk} RISK  "
                f"·  after fix: {after_block} BLOCK  {after_risk} RISK ──",
                _C.GREY, use_colour,
            ))

    return 1 if report.has_block else 0


def entrypoint() -> None:
    sys.exit(main())


if __name__ == "__main__":
    entrypoint()
