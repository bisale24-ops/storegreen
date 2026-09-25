# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
fixer.py — deterministic, safe, in-place repairs for --fix.

Applies only fixes that are unambiguous and do not require a secret:
  AMZ-IAP-06  append missing ProGuard keep lines to the first proguard file
  AMZ-IAP-04  add missing <queries> entries to AndroidManifest.xml
  AMZ-IAP-03  add the ResponseReceiver block to AndroidManifest.xml
  GP-API-01   raise targetSdk to the required level in build.gradle
  GP-BILL-01  raise the billing library version in build.gradle

AMZ-IAP-01 is intentionally excluded: the Amazon key cannot be fabricated.

Returns:
  (unified_diff_str, list_of_applied_rule_ids)

Never writes a file outside repo_root.
Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

import difflib
import os
import re
from typing import List, Optional, Tuple

from storegreen.rules.base import Finding
from storegreen.runner import ScanReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _unified_diff(old: str, new: str, label: str) -> str:
    """Return a unified diff string for a single file change."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    chunks = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{label}",
        tofile=f"b/{label}",
    ))
    return "".join(chunks)


def _is_inside(path: str, root: str) -> bool:
    """Return True when path is inside root (prevents escaping the repo)."""
    path = os.path.realpath(path)
    root = os.path.realpath(root)
    return path.startswith(root + os.sep) or path == root


# ---------------------------------------------------------------------------
# Fix AMZ-IAP-06: append missing ProGuard keep lines
# ---------------------------------------------------------------------------

_KEEP_RE      = re.compile(r'-keep\s+class\s+com\.amazon\.\*\*',      re.IGNORECASE)
_DONTWARN_RE  = re.compile(r'-dontwarn\s+com\.amazon\.\*\*',           re.IGNORECASE)
_KEEPATTR_RE  = re.compile(r'-keepattributes\s+\*Annotation\*',        re.IGNORECASE)

_PROGUARD_COMMENT_RE = re.compile(r'#[^\n]*')


def _strip_comments_proguard(text: str) -> str:
    return _PROGUARD_COMMENT_RE.sub("", text)


def _fix_amz_iap06(finding: Finding, repo_root: str) -> Optional[Tuple[str, str, str]]:
    """Return (label, old_text, new_text) or None if nothing to fix."""
    evidence_file = finding.evidence.file  # repo-relative path
    abs_path = os.path.join(repo_root, evidence_file)
    if not _is_inside(abs_path, repo_root) or not os.path.isfile(abs_path):
        return None

    old = _read(abs_path)
    stripped = _strip_comments_proguard(old)
    missing: List[str] = []
    if not _KEEP_RE.search(stripped):
        missing.append("-keep class com.amazon.** { *; }")
    if not _DONTWARN_RE.search(stripped):
        missing.append("-dontwarn com.amazon.**")
    if not _KEEPATTR_RE.search(stripped):
        missing.append("-keepattributes *Annotation*")

    if not missing:
        return None

    addition = "\n# Added by storegreen --fix (AMZ-IAP-06)\n" + "\n".join(missing) + "\n"
    new = old.rstrip("\n") + "\n" + addition
    return (evidence_file, old, new)


# ---------------------------------------------------------------------------
# Fix AMZ-IAP-04: add <queries> entries to AndroidManifest.xml
# ---------------------------------------------------------------------------

_VENEZIA   = "com.amazon.venezia"
_SDK_TEST  = "com.amazon.sdktestclient"

# Matches an existing <queries> block
_QUERIES_BLOCK_RE = re.compile(
    r'(<queries\b[^>]*>)(.*?)(</queries\s*>)',
    re.DOTALL | re.IGNORECASE,
)

_QUERIES_BLOCK = (
    "\n    <queries>\n"
    f'        <package android:name="{_VENEZIA}" />\n'
    f'        <package android:name="{_SDK_TEST}" />\n'
    "    </queries>\n"
)


def _strip_xml_comments(text: str) -> str:
    return re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)


def _fix_amz_iap04(finding: Finding, repo_root: str) -> Optional[Tuple[str, str, str]]:
    """Return (label, old_text, new_text) or None if nothing to fix."""
    evidence_file = finding.evidence.file
    abs_path = os.path.join(repo_root, evidence_file)
    if not _is_inside(abs_path, repo_root) or not os.path.isfile(abs_path):
        return None

    old = _read(abs_path)
    live = _strip_xml_comments(old)

    venezia_present = _VENEZIA in live
    sdk_test_present = _SDK_TEST in live

    if venezia_present and sdk_test_present:
        return None  # already fixed by another pass

    # Is there an existing <queries> block?
    m = _QUERIES_BLOCK_RE.search(live)
    if m:
        # Add missing entries inside the existing block
        open_tag = m.group(1)
        inner = m.group(2)
        close_tag = m.group(3)
        additions = ""
        if not venezia_present:
            additions += f'        <package android:name="{_VENEZIA}" />\n'
        if not sdk_test_present:
            additions += f'        <package android:name="{_SDK_TEST}" />\n'
        new_inner = inner.rstrip() + "\n" + additions
        new_block = open_tag + new_inner + close_tag
        # Replace the first occurrence in the *original* text (not live stripped)
        orig_m = _QUERIES_BLOCK_RE.search(old)
        if orig_m:
            new = old[:orig_m.start()] + new_block + old[orig_m.end():]
        else:
            new = old
    else:
        # Insert a new <queries> block before </manifest>
        close_manifest = old.rfind("</manifest>")
        if close_manifest == -1:
            return None
        new = old[:close_manifest] + _QUERIES_BLOCK + old[close_manifest:]

    return (evidence_file, old, new)


# ---------------------------------------------------------------------------
# Fix AMZ-IAP-03: add ResponseReceiver block to AndroidManifest.xml
# ---------------------------------------------------------------------------

_RECEIVER_NAME = "com.amazon.device.iap.ResponseReceiver"
_NOTIFY_PERMISSION = "com.amazon.inapp.purchasing.Permission.NOTIFY"
_NOTIFY_ACTION = "com.amazon.inapp.purchasing.NOTIFY"

_RECEIVER_BLOCK = (
    "\n        <!-- Added by storegreen --fix (AMZ-IAP-03) -->\n"
    '        <receiver\n'
    f'            android:name="{_RECEIVER_NAME}"\n'
    '            android:exported="true"\n'
    f'            android:permission="{_NOTIFY_PERMISSION}">\n'
    '            <intent-filter>\n'
    f'                <action android:name="{_NOTIFY_ACTION}" />\n'
    '            </intent-filter>\n'
    '        </receiver>\n'
)


def _fix_amz_iap03(finding: Finding, repo_root: str) -> Optional[Tuple[str, str, str]]:
    """Return (label, old_text, new_text) or None if nothing to fix."""
    evidence_file = finding.evidence.file
    abs_path = os.path.join(repo_root, evidence_file)
    if not _is_inside(abs_path, repo_root) or not os.path.isfile(abs_path):
        return None

    old = _read(abs_path)
    if _RECEIVER_NAME in _strip_xml_comments(old):
        return None  # already present

    # Insert before </application>
    close_app = old.rfind("</application>")
    if close_app == -1:
        return None
    new = old[:close_app] + _RECEIVER_BLOCK + old[close_app:]
    return (evidence_file, old, new)


# ---------------------------------------------------------------------------
# Fix GP-API-01: raise targetSdk in build.gradle
# ---------------------------------------------------------------------------

_TARGET_SDK_RE = re.compile(r'(targetSdk(?:Version)?\s*[=:]?\s*)(\d+)', re.IGNORECASE)


def _fix_gp_api01(finding: Finding, repo_root: str) -> Optional[Tuple[str, str, str]]:
    """Return (label, old_text, new_text) or None if nothing to fix."""
    evidence_file = finding.evidence.file
    abs_path = os.path.join(repo_root, evidence_file)
    if not _is_inside(abs_path, repo_root) or not os.path.isfile(abs_path):
        return None

    # Parse required SDK from the finding title (e.g. "targetSdk 35 is below … 36 for phone")
    required_m = re.search(r'below the required level\s+(\d+)', finding.title)
    if not required_m:
        return None
    required = int(required_m.group(1))

    old = _read(abs_path)
    m = _TARGET_SDK_RE.search(old)
    if not m:
        return None
    current = int(m.group(2))
    if current >= required:
        return None

    new = _TARGET_SDK_RE.sub(lambda mm: mm.group(1) + str(required), old, count=1)
    return (evidence_file, old, new)


# ---------------------------------------------------------------------------
# Fix GP-BILL-01: raise billing library version in build.gradle
# ---------------------------------------------------------------------------

# Matches "com.android.billingclient:billing[-ktx]:X.Y.Z" inside a string literal
_BILLING_DEP_RE = re.compile(
    r'(com\.android\.billingclient:billing(?:-ktx)?:)([\d][^\'"]*)',
    re.IGNORECASE,
)
_REQUIRED_BILLING = "8.0.0"


def _fix_gp_bill01(finding: Finding, repo_root: str) -> Optional[Tuple[str, str, str]]:
    """Return (label, old_text, new_text) or None if nothing to fix."""
    evidence_file = finding.evidence.file
    abs_path = os.path.join(repo_root, evidence_file)
    if not _is_inside(abs_path, repo_root) or not os.path.isfile(abs_path):
        return None

    old = _read(abs_path)
    m = _BILLING_DEP_RE.search(old)
    if not m:
        return None

    # Check the version catalog too (evidence may point there)
    new = _BILLING_DEP_RE.sub(
        lambda mm: mm.group(1) + _REQUIRED_BILLING,
        old,
        count=1,
    )
    if new == old:
        return None
    return (evidence_file, old, new)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_FIXERS = {
    "AMZ-IAP-06": _fix_amz_iap06,
    "AMZ-IAP-04": _fix_amz_iap04,
    "AMZ-IAP-03": _fix_amz_iap03,
    "GP-API-01":  _fix_gp_api01,
    "GP-BILL-01": _fix_gp_bill01,
}


def apply_fixes(
    report: ScanReport,
    repo_root: str,
) -> Tuple[str, List[str]]:
    """Apply all deterministic fixes to the files in *repo_root*.

    Parameters
    ----------
    report:    the ScanReport from the initial scan
    repo_root: absolute path — no file outside this tree is ever touched

    Returns
    -------
    (unified_diff_str, applied_rule_ids)
        unified_diff_str  — all changes in one unified-diff block
        applied_rule_ids  — list of rule IDs that were fixed (in order applied)
    """
    repo_root = os.path.realpath(repo_root)
    diff_parts: List[str] = []
    applied: List[str] = []

    for finding in report.findings:
        fixer_fn = _FIXERS.get(finding.rule)
        if fixer_fn is None:
            continue

        result = fixer_fn(finding, repo_root)
        if result is None:
            continue

        label, old, new = result
        if old == new:
            continue

        abs_path = os.path.join(repo_root, label)
        _write(abs_path, new)
        diff_parts.append(_unified_diff(old, new, label))
        applied.append(finding.rule)

    return "".join(diff_parts), applied
