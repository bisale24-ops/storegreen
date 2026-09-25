# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
rules/gp_16kb.py — Google Play 16 KB page-alignment rule (tier 1).

Implements:
  GP-16KB-01  native .so not aligned for 16 KB pages, targetSdk ≥ 35, 64-bit

Detection: ELF PT_LOAD segment alignment < 2^14 (0x4000) in
  base/lib/arm64-v8a/*.so  (64-bit ABIs only, per spec)

Severity: WARN now; BLOCK from 01.02.2027.

The ELF reader never raises — all error cases return Undecided.
An empty PT_LOAD set is also Undecided (spec §2: empty result must never
be read as aligned).

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

import os
from typing import List

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
from storegreen.bundle.elf_reader import read_alignments, ElfResult


# 64-bit ABIs only (spec §2)
_64BIT_ABIS = ("arm64-v8a", "x86_64")

_REQUIRED_ALIGN = 0x4000


class GpSixteenKb01(Rule):
    """GP-16KB-01 — native .so not 16 KB aligned."""

    id = "GP-16KB-01"
    family = "google-play-16kb"
    severity = "WARN"   # BLOCK from 01.02.2027
    tier = 1

    def check_source(self, ctx: SourceContext) -> RuleResult:
        # Native libraries only exist in the built bundle; source check is N/A.
        return NotApplicable(
            rule=self.id,
            reason="ELF alignment can only be checked from a built .aab; re-run with --aab",
        )

    def check_bundle(self, ctx: BundleContext) -> RuleResult:
        from storegreen.bundle.aab_reader import AabReader

        failures: List[ElfResult] = []
        undecidables: List[ElfResult] = []
        lib_count = 0

        try:
            with AabReader(ctx.aab_path) as reader:
                for abi in _64BIT_ABIS:
                    for entry_name in reader.iter_abi_libs(abi):
                        lib_count += 1
                        data = reader.read(entry_name)
                        if data is None:
                            undecidables.append(ElfResult(
                                entry_path=entry_name,
                                readable=False,
                                reason="cannot be determined — entry unreadable",
                                bits=None,
                            ))
                            continue

                        result = read_alignments(data, entry_name)

                        if not result.readable:
                            undecidables.append(result)
                            continue

                        if not result.alignments:
                            # No PT_LOAD segments — undecidable per spec
                            undecidables.append(ElfResult(
                                entry_path=entry_name,
                                readable=False,
                                reason="cannot be determined — no PT_LOAD segments found",
                                bits=result.bits,
                            ))
                            continue

                        if not result.is_aligned_16kb:
                            failures.append(result)

        except Exception as exc:
            return Undecided(
                rule=self.id,
                reason=f"cannot read bundle: {exc}",
                evidence=Evidence(
                    file=ctx.aab_path, line=None,
                    found=str(exc), expected="readable .aab",
                ),
            )

        if lib_count == 0:
            return NotApplicable(
                rule=self.id,
                reason="no 64-bit native libraries found in bundle",
            )

        # Report the first unreadable library as Undecided (if no failures)
        if undecidables and not failures:
            u = undecidables[0]
            return Undecided(
                rule=self.id,
                reason=u.reason or "cannot be determined — unreadable ELF",
                evidence=Evidence(
                    file=u.entry_path, line=None,
                    found=u.reason or "unreadable",
                    expected="readable ELF with PT_LOAD alignments",
                ),
            )

        if failures:
            # Report the first failing library; list all in the found field
            first = failures[0]
            min_align = first.min_alignment
            align_hex = f"{min_align:#x}" if min_align is not None else "unknown"
            all_bad = "; ".join(
                f"{r.entry_path} (min p_align={r.min_alignment:#x})"
                for r in failures
                if r.min_alignment is not None
            )
            return Finding(
                rule=self.id,
                family=self.family,
                severity=self.severity,
                title=(
                    f"{os.path.basename(first.entry_path)} PT_LOAD alignment "
                    f"{align_hex} < 0x4000; 16 KB page support missing "
                    "(BLOCK from 01.02.2027)"
                ),
                evidence=Evidence(
                    file=first.entry_path,
                    line=None,
                    found=f"min p_align = {align_hex}; failing: {all_bad}",
                    expected="every PT_LOAD p_align ≥ 0x4000 (16 KB)",
                ),
                decided_from="bundle",
                fix=FixHint(
                    automatic=False,
                    description=(
                        "Rebuild native libraries with AGP 8.5.1+ and NDK r28+. "
                        "Third-party native dependencies (e.g. SQLCipher) must also "
                        "be rebuilt — a prebuilt .so cannot be patched post-build."
                    ),
                ),
            )

        # All libraries passed
        return Passed(
            rule=self.id,
            note=f"all {lib_count} 64-bit native libraries have PT_LOAD p_align ≥ 0x4000",
            decided_from="bundle",
            evidence=Evidence(
                file=f"base/lib/arm64-v8a/ ({lib_count} libraries)",
                line=None,
                found=f"{lib_count} libraries checked, all aligned",
                expected="every PT_LOAD p_align ≥ 0x4000",
            ),
        )
