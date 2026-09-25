# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
report/json_report.py — serialize a ScanReport to a JSON string.
"""

from __future__ import annotations

import json
from typing import Optional

from storegreen.runner import ScanReport
from storegreen.report.schema import to_dict


def to_json(report: ScanReport, indent: Optional[int] = 2) -> str:
    """Return a JSON string of the report."""
    return json.dumps(to_dict(report), indent=indent, ensure_ascii=False)
