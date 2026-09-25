# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
report/html_report.py — ScanReport → single self-contained HTML file.

No Jinja2, no external dependencies, no network.  One f-string template.
CSS is inline in the <style> block.  No <script> tags.
"""

from __future__ import annotations

from typing import List

from storegreen.runner import ScanReport
from storegreen.report.schema import to_dict
from storegreen import __version__


_SEV_COLOR = {"BLOCK": "#b91c1c", "RISK": "#b45309", "WARN": "#1d4ed8"}
_SEV_BG    = {"BLOCK": "#fee2e2", "RISK": "#fef3c7", "WARN": "#dbeafe"}


def _esc(s: object) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _finding_html(f: dict) -> str:
    sev = f["severity"]
    color = _SEV_COLOR.get(sev, "#374151")
    bg    = _SEV_BG.get(sev, "#f3f4f6")
    ev = f.get("evidence") or {}
    fix_html = ""
    if f.get("fix"):
        fix_desc = _esc(f["fix"].get("description", ""))
        auto = "✎ automatic" if f["fix"].get("automatic") else "✎ manual"
        fix_html = f'<div class="fix"><span class="fix-badge">{auto}</span> {fix_desc}</div>'
    from_html = f'<span class="from">decided from: {_esc(f.get("decided_from", "?"))}</span>'
    ev_file = _esc(ev.get("file", ""))
    ev_line = ev.get("line")
    ev_loc = f"{ev_file}:{ev_line}" if ev_line else ev_file
    return f"""
<div class="finding" style="border-left:4px solid {color}; background:{bg}; padding:12px 16px; margin-bottom:12px; border-radius:4px;">
  <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
    <span class="sev" style="background:{color}; color:#fff; padding:2px 8px; border-radius:3px; font-size:12px; font-weight:700;">{_esc(sev)}</span>
    <span class="rule-id" style="font-family:monospace; font-weight:700;">{_esc(f["rule"])}</span>
    {from_html}
  </div>
  <div class="title" style="font-weight:600; margin-bottom:6px;">{_esc(f["title"])}</div>
  <div class="evidence" style="font-family:monospace; font-size:13px; color:#374151;">
    <div><strong>at:</strong> {_esc(ev_loc)}</div>
    <div><strong>found:</strong> {_esc(ev.get("found", ""))}</div>
    <div><strong>expected:</strong> {_esc(ev.get("expected", ""))}</div>
  </div>
  {fix_html}
</div>"""


def _undecided_html(u: dict) -> str:
    ev = u.get("evidence") or {}
    ev_file = _esc(ev.get("file", ""))
    ev_line = ev.get("line")
    ev_loc = f"{ev_file}:{ev_line}" if ev_line else ev_file
    return f"""
<div class="undecided" style="border-left:4px solid #6b7280; background:#f9fafb; padding:10px 16px; margin-bottom:8px; border-radius:4px;">
  <span style="font-family:monospace; font-weight:700;">{_esc(u["rule"])}</span>
  <span style="color:#6b7280;"> · </span>{_esc(u["reason"])}
  <div style="font-size:12px; color:#6b7280; margin-top:2px;">gave up at {_esc(ev_loc)}</div>
</div>"""


def to_html(report: ScanReport) -> str:
    d = to_dict(report)
    summary = d["summary"]
    scanned = d["scanned"]

    block_count = summary["block"]
    risk_count  = summary["risk"]
    warn_count  = summary["warn"]
    unk_count   = summary["undecidable"]
    pass_count  = summary["passed"]
    na_count    = summary["not_applicable"]
    ni_count    = summary["not_implemented"]
    secs        = summary["seconds"]

    modules_str = ", ".join(scanned["modules"]) or "—"
    ffs_str     = ", ".join(scanned["form_factors"]) or "phone"
    repo_str    = _esc(scanned["repo"] or "—")
    aab_str     = _esc(scanned["aab"] or "—")

    verdict_color = "#15803d" if block_count == 0 else "#b91c1c"
    verdict_text  = "✓ Ready to submit" if block_count == 0 else f"✗ {block_count} BLOCK — store will reject"

    # Findings section
    findings_html = ""
    if d["findings"]:
        findings_html = "<h2 style='margin-top:24px;'>Findings</h2>" + "".join(_finding_html(f) for f in d["findings"])
    else:
        findings_html = "<p style='color:#15803d; font-weight:600;'>No findings.</p>"

    # Undecided section
    undecided_html = ""
    if d["undecided"]:
        rows = "".join(_undecided_html(u) for u in d["undecided"])
        undecided_html = f"<h2 style='margin-top:24px;'>Undecided ({unk_count})</h2>{rows}"

    # Passed section (collapsed)
    passed_html = ""
    if d["passed"]:
        rows = "".join(
            f'<div style="padding:4px 0; font-size:13px;"><span style="font-family:monospace;">{_esc(p["rule"])}</span> — {_esc(p["note"])}</div>'
            for p in d["passed"]
        )
        passed_html = f"""
<details style="margin-top:24px;">
  <summary style="cursor:pointer; font-weight:600; font-size:15px;">{pass_count} rules passed</summary>
  <div style="padding:12px 0;">{rows}</div>
</details>"""

    # Not applicable
    na_html = ""
    if d["not_applicable"]:
        rows = ", ".join(_esc(n["rule"]) for n in d["not_applicable"])
        na_html = f'<p style="color:#6b7280; font-size:13px; margin-top:16px;"><strong>Not applicable ({na_count}):</strong> {rows}</p>'

    # Not implemented
    ni_html = ""
    if d["not_implemented"]:
        rows = ", ".join(_esc(r) for r in d["not_implemented"])
        ni_html = f'<p style="color:#6b7280; font-size:13px; margin-top:8px;"><strong>Not implemented ({ni_count}):</strong> {rows}</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>StoreGreen report</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", system-ui, sans-serif; font-size:15px; line-height:1.6; color:#1f2328; background:#fff; max-width:820px; margin:40px auto; padding:0 24px; }}
  h1 {{ font-size:22px; margin-bottom:4px; }}
  .scorecard {{ background:#f7f8fa; border:1px solid #e5e7eb; border-radius:6px; padding:20px 24px; margin-bottom:24px; }}
  .verdict {{ font-size:20px; font-weight:700; color:{verdict_color}; margin-bottom:12px; }}
  .counts {{ display:flex; gap:20px; flex-wrap:wrap; font-size:14px; }}
  .count-item {{ display:flex; flex-direction:column; align-items:center; }}
  .count-num {{ font-size:28px; font-weight:700; line-height:1; }}
  .count-label {{ color:#57606a; font-size:12px; }}
  .meta {{ font-size:13px; color:#57606a; margin-top:12px; }}
  h2 {{ font-size:17px; margin-bottom:12px; }}
</style>
</head>
<body>
<h1>StoreGreen <span style="font-weight:400; color:#57606a; font-size:16px;">v{_esc(__version__)}</span></h1>

<div class="scorecard">
  <div class="verdict">{verdict_text}</div>
  <div class="counts">
    <div class="count-item"><span class="count-num" style="color:#b91c1c;">{block_count}</span><span class="count-label">BLOCK</span></div>
    <div class="count-item"><span class="count-num" style="color:#b45309;">{risk_count}</span><span class="count-label">RISK</span></div>
    <div class="count-item"><span class="count-num" style="color:#1d4ed8;">{warn_count}</span><span class="count-label">WARN</span></div>
    <div class="count-item"><span class="count-num" style="color:#6b7280;">{unk_count}</span><span class="count-label">undecidable</span></div>
    <div class="count-item"><span class="count-num" style="color:#15803d;">{pass_count}</span><span class="count-label">passed</span></div>
  </div>
  <div class="meta">
    modules: {_esc(modules_str)} · form factor: {_esc(ffs_str)} · {_esc(secs)}s<br>
    repo: {repo_str}<br>
    aab: {aab_str}
  </div>
</div>

{findings_html}
{undecided_html}
{passed_html}
{na_html}
{ni_html}

<hr style="border:none; border-top:1px solid #e5e7eb; margin-top:40px;">
<p style="text-align:center; font-size:12px; color:#57606a;">StoreGreen v{_esc(__version__)} · MIT licence</p>
</body>
</html>"""
