# SPDX-License-Identifier: MIT
"""
tests/test_rules_base.py — unit tests for rules/base.py

Covers:
- Dataclass construction for all four result types
- Finding.__post_init__ rejects missing evidence and bad severity/decided_from
- Undecided.__post_init__ rejects missing evidence
- Passed.__post_init__ rejects bad decided_from
- Rule ABC cannot be instantiated without implementing check_source
- Default check_bundle returns NotApplicable
"""

import pytest

from storegreen.rules.base import (
    BundleContext,
    Evidence,
    Finding,
    FixHint,
    NotApplicable,
    Passed,
    Rule,
    SourceContext,
    Undecided,
)


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

def test_evidence_with_line():
    e = Evidence(file="app/build.gradle", line=42, found="targetSdk 35", expected="36")
    assert e.file == "app/build.gradle"
    assert e.line == 42


def test_evidence_binary_no_line():
    e = Evidence(file="base/lib/arm64-v8a/libfoo.so", line=None, found="p_align=0x1000", expected="p_align ≥ 0x4000")
    assert e.line is None


# ---------------------------------------------------------------------------
# FixHint
# ---------------------------------------------------------------------------

def test_fix_hint():
    fh = FixHint(automatic=True, description="add the receiver block")
    assert fh.automatic is True


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------

def _good_evidence():
    return Evidence(file="f.xml", line=1, found="x", expected="y")


def test_finding_valid():
    f = Finding(
        rule="AMZ-IAP-03",
        family="amazon-iap",
        severity="BLOCK",
        title="receiver missing",
        evidence=_good_evidence(),
        decided_from="source",
    )
    assert f.rule == "AMZ-IAP-03"
    assert f.fix is None


def test_finding_with_fix():
    f = Finding(
        rule="AMZ-IAP-03",
        family="amazon-iap",
        severity="BLOCK",
        title="receiver missing",
        evidence=_good_evidence(),
        decided_from="bundle",
        fix=FixHint(automatic=True, description="patch manifest"),
    )
    assert f.fix.automatic is True


def test_finding_rejects_none_evidence():
    with pytest.raises(ValueError, match="evidence must not be None"):
        Finding(
            rule="AMZ-IAP-03",
            family="amazon-iap",
            severity="BLOCK",
            title="t",
            evidence=None,  # type: ignore
            decided_from="source",
        )


def test_finding_rejects_bad_severity():
    with pytest.raises(ValueError, match="severity must be BLOCK"):
        Finding(
            rule="X", family="f", severity="CRITICAL",
            title="t", evidence=_good_evidence(), decided_from="source",
        )


def test_finding_rejects_bad_decided_from():
    with pytest.raises(ValueError, match="decided_from must be"):
        Finding(
            rule="X", family="f", severity="BLOCK",
            title="t", evidence=_good_evidence(), decided_from="guessed",
        )


# ---------------------------------------------------------------------------
# Undecided
# ---------------------------------------------------------------------------

def test_undecided_valid():
    u = Undecided(rule="GP-API-01", reason="env var", evidence=_good_evidence())
    assert u.reason == "env var"


def test_undecided_rejects_none_evidence():
    with pytest.raises(ValueError, match="evidence must not be None"):
        Undecided(rule="GP-API-01", reason="env var", evidence=None)  # type: ignore


# ---------------------------------------------------------------------------
# Passed
# ---------------------------------------------------------------------------

def test_passed_valid():
    p = Passed(rule="AMZ-IAP-01", note="key present", decided_from="bundle")
    assert p.evidence is None


def test_passed_with_evidence():
    p = Passed(
        rule="AMZ-IAP-01",
        note="key present; SHA-256=abc",
        decided_from="bundle",
        evidence=Evidence(file="base/assets/AppstoreAuthenticationKey.pem", line=None, found="sha=abc", expected="present"),
    )
    assert p.evidence is not None


def test_passed_rejects_bad_decided_from():
    with pytest.raises(ValueError, match="decided_from must be"):
        Passed(rule="X", note="ok", decided_from="nowhere")


# ---------------------------------------------------------------------------
# NotApplicable
# ---------------------------------------------------------------------------

def test_not_applicable():
    na = NotApplicable(rule="AMZ-IAP-01", reason="no amazon flavor")
    assert na.rule == "AMZ-IAP-01"


# ---------------------------------------------------------------------------
# Rule ABC
# ---------------------------------------------------------------------------

def test_rule_abc_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        Rule()  # type: ignore


def test_rule_default_check_bundle_returns_not_applicable():
    class ConcreteRule(Rule):
        id = "TEST-01"
        family = "test"
        severity = "BLOCK"
        tier = 1

        def check_source(self, ctx):
            return Passed(rule=self.id, note="ok", decided_from="source")

    rule = ConcreteRule()
    ctx = BundleContext(aab_path="/fake/path.aab")
    result = rule.check_bundle(ctx)
    assert isinstance(result, NotApplicable)
    assert result.rule == "TEST-01"


def test_rule_check_source_implemented():
    class ConcreteRule(Rule):
        id = "TEST-02"
        family = "test"
        severity = "RISK"
        tier = 1

        def check_source(self, ctx):
            return NotApplicable(rule=self.id, reason="no module found")

    rule = ConcreteRule()
    ctx = SourceContext(repo_root="/tmp")
    result = rule.check_source(ctx)
    assert isinstance(result, NotApplicable)
