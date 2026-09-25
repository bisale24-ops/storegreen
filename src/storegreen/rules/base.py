# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
rules/base.py — dataclasses and the Rule ABC.

All rule modules import from here.  No external dependencies.
Python 3.9 compatible (use Union instead of X | Y).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Union


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

@dataclass
class Evidence:
    """Where and what the rule looked at.

    `line` is None only for binary entries (ELF program headers, PEM bytes).
    For every text file a non-null line number is required.
    """
    file: str       # repo-relative or AAB-entry path
    line: Optional[int]  # None only for binary entries
    found: str      # verbatim excerpt or description of what was found
    expected: str   # what the store requires


# ---------------------------------------------------------------------------
# Fix hint
# ---------------------------------------------------------------------------

@dataclass
class FixHint:
    automatic: bool   # True  → runner.fixer can apply this without human input
    description: str  # human-readable explanation


# ---------------------------------------------------------------------------
# Rule outcomes
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """A rule ran, found a problem, and has evidence to back it up."""
    rule: str           # e.g. "AMZ-IAP-03"
    family: str         # e.g. "amazon-iap"
    severity: str       # "BLOCK" | "RISK" | "WARN"
    title: str
    evidence: Evidence
    decided_from: str   # "source" | "bundle" | "both"
    fix: Optional[FixHint] = None

    def __post_init__(self) -> None:
        if self.evidence is None:  # type: ignore[comparison-overlap]
            raise ValueError(
                f"Finding({self.rule}): evidence must not be None — "
                "a finding without evidence is a bug, not a finding"
            )
        if self.severity not in ("BLOCK", "RISK", "WARN"):
            raise ValueError(
                f"Finding({self.rule}): severity must be BLOCK, RISK, or WARN, "
                f"got {self.severity!r}"
            )
        if self.decided_from not in ("source", "bundle", "both"):
            raise ValueError(
                f"Finding({self.rule}): decided_from must be 'source', 'bundle', "
                f"or 'both', got {self.decided_from!r}"
            )


@dataclass
class Undecided:
    """A rule ran but could not reach a verdict, and records exactly why."""
    rule: str
    reason: str
    evidence: Evidence  # the file+line where the rule gave up; always present

    def __post_init__(self) -> None:
        if self.evidence is None:  # type: ignore[comparison-overlap]
            raise ValueError(
                f"Undecided({self.rule}): evidence must not be None — "
                "the line it gave up on must always be present"
            )


@dataclass
class Passed:
    """A rule ran and found no problem."""
    rule: str
    note: str
    decided_from: str   # "source" | "bundle" | "both"
    evidence: Optional[Evidence] = None  # required for binary checks (e.g. PEM SHA-256)

    def __post_init__(self) -> None:
        if self.decided_from not in ("source", "bundle", "both"):
            raise ValueError(
                f"Passed({self.rule}): decided_from must be 'source', 'bundle', "
                f"or 'both', got {self.decided_from!r}"
            )


@dataclass
class NotApplicable:
    """The rule's precondition is absent — it is not relevant to this project."""
    rule: str
    reason: str     # "no amazon flavor" | "no native libraries" | "no billing dependency" | …


# Union type for rule return values
RuleResult = Union[Finding, Undecided, Passed, NotApplicable]


# ---------------------------------------------------------------------------
# Context objects passed to rule.check_*
# ---------------------------------------------------------------------------

@dataclass
class SourceContext:
    """Everything a rule needs to evaluate a source tree."""
    repo_root: str                    # absolute path
    # populated by runner.py after project_layout + manifest_merger + gradle_reader
    modules: List[str] = field(default_factory=list)  # module names found
    # rules reach into these via helper methods on the context rather than
    # calling the readers directly, but the raw objects are here so a rule
    # that needs detail can get it.
    _layout: Optional[object] = field(default=None, repr=False)
    _manifests: Optional[object] = field(default=None, repr=False)
    _gradle: Optional[object] = field(default=None, repr=False)

    # Convenience accessors (set by runner.py)
    def get_layout(self) -> object:
        return self._layout

    def get_manifests(self) -> object:
        return self._manifests

    def get_gradle(self) -> object:
        return self._gradle


@dataclass
class BundleContext:
    """Everything a rule needs to evaluate a built AAB."""
    aab_path: str                     # absolute path to the .aab file
    _reader: Optional[object] = field(default=None, repr=False)  # AabReader

    def get_reader(self) -> object:
        return self._reader


# ---------------------------------------------------------------------------
# Rule ABC
# ---------------------------------------------------------------------------

class Rule(ABC):
    """Base class for every StoreGreen rule.

    Subclasses set class-level attributes:
        id       — e.g. "AMZ-IAP-03"
        family   — e.g. "amazon-iap"
        severity — "BLOCK" | "RISK" | "WARN"
        tier     — 1 = must ship; 2 = stretch
    """

    id: str
    family: str
    severity: str
    tier: int

    # ------------------------------------------------------------------
    # check_source is mandatory for every rule.
    # check_bundle defaults to NotApplicable for rules that only read source.
    # ------------------------------------------------------------------

    @abstractmethod
    def check_source(self, ctx: SourceContext) -> RuleResult:
        """Evaluate this rule against the source tree."""
        ...

    def check_bundle(self, ctx: BundleContext) -> RuleResult:
        """Evaluate this rule against a built AAB.

        Default implementation returns NotApplicable so that source-only rules
        do not need to override it.  Tier-1 bundle rules MUST override.
        """
        return NotApplicable(
            rule=self.id,
            reason="this rule does not inspect the bundle",
        )
