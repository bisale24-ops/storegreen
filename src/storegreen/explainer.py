# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
explainer.py — map a store rejection e-mail to rules via symptom matching.

Design (per prep/rules-catalog.md §12 item 4 and the task brief):

  Keyword matching is pointless and dishonest — the Amazon rejection e-mail
  names only a symptom ("IAP displays error"), not a root cause.

  Instead we do three things:
    1. Split the e-mail body into sentences and try to match each sentence
       to a *symptom group* — a named set of rules that can produce that
       observable symptom.
    2. For each matched group, intersect with the scan's findings/undecided
       to partition the candidate rules into:
         - "violated here"  — the rule fired in the scanned project
         - "clean here"     — the rule is Passed/NotApplicable for this project
         - "undecided here" — the rule couldn't be decided (honest caveat)
    3. Collect sentences that matched no group at all.

  The output is a plain dataclass; rendering is left to cli.py.

  The symptom table below is the *only* place we claim causation.  Adding a
  new symptom means adding a row here, never somewhere inside a regex or a
  fuzzy-match score.

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from storegreen.runner import ScanReport


# ---------------------------------------------------------------------------
# Symptom catalogue
# ---------------------------------------------------------------------------
# Each entry: (symptom_label, [trigger_phrases], [rule_ids_that_cause_it])
#
# trigger_phrases are lowercased substrings we look for in each sentence.
# A sentence matches a symptom if it contains ANY of the trigger phrases.
# Rule ids in the candidate list are checked against what the scan found.

@dataclass
class SymptomEntry:
    label: str           # human-readable symptom name
    triggers: List[str]  # lowercase substrings; any match → symptom fires
    rule_ids: List[str]  # candidate rules that can produce this symptom


_SYMPTOM_TABLE: List[SymptomEntry] = [
    SymptomEntry(
        label="IAP / purchase displays error at runtime",
        triggers=[
            "iap displays error",
            "iap display error",
            "error",            # broad — catches "app displays an error message"
            "purchase",
            "purchasing",
            "buy",
            "payment",
        ],
        rule_ids=["AMZ-IAP-01", "AMZ-IAP-03", "AMZ-IAP-04", "AMZ-IAP-06"],
    ),
    SymptomEntry(
        label="App rejected / not published",
        triggers=[
            "not published",
            "failed",
            "content policy",
            "rejection",
            "rejected",
            "remedial",
            "resubmit",
        ],
        rule_ids=["AMZ-IAP-01", "AMZ-IAP-03", "AMZ-IAP-04", "AMZ-IAP-06"],
    ),
    SymptomEntry(
        label="PurchasingService / SDK reference in rejection",
        triggers=[
            "purchasingservice",
            "purchasing service",
            "iap-implement-iap",
            "implement-iap",
            "appstore sdk",
            "appstore-sdk",
        ],
        rule_ids=["AMZ-IAP-03", "AMZ-IAP-04", "AMZ-IAP-06"],
    ),
]


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SentenceMapping:
    """One sentence from the e-mail and what it mapped to (if anything)."""
    sentence: str
    symptom_label: Optional[str]   # None → no match
    violated: List[str] = field(default_factory=list)   # found in this scan
    undecided: List[str] = field(default_factory=list)  # couldn't be decided
    clean: List[str] = field(default_factory=list)      # passed / not applicable


@dataclass
class ExplainResult:
    """Full output of explain()."""
    email_file: str
    # One entry per *unique symptom group* that fired (deduplicated across sentences)
    matched_symptoms: List[SentenceMapping] = field(default_factory=list)
    # Sentences that matched no symptom at all
    unmapped_sentences: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _sentences(text: str) -> List[str]:
    """Split text into non-empty sentences (split on . ! ? and newlines)."""
    parts = re.split(r'(?<=[.!?])\s+|\n', text)
    return [p.strip() for p in parts if p.strip()]


def _classify_rules(
    rule_ids: List[str],
    report: ScanReport,
) -> Tuple[List[str], List[str], List[str]]:
    """Partition rule_ids into (violated, undecided, clean) given a ScanReport."""
    finding_ids  = {f.rule for f in report.findings}
    undecided_ids = {u.rule for u in report.undecided}
    # anything else (passed, not_applicable, not_implemented) counts as clean/unknown
    violated: List[str] = []
    undecided: List[str] = []
    clean: List[str] = []
    for rid in rule_ids:
        if rid in finding_ids:
            violated.append(rid)
        elif rid in undecided_ids:
            undecided.append(rid)
        else:
            clean.append(rid)
    return violated, undecided, clean


def explain(email_path: str, report: ScanReport) -> ExplainResult:
    """Read *email_path* and map its content against *report*.

    Parameters
    ----------
    email_path : path to the plain-text rejection e-mail
    report     : ScanReport from scanning the project (source or bundle mode)
    """
    result = ExplainResult(email_file=email_path)

    try:
        with open(email_path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        # Fail hard so the caller sees a real error message
        raise ValueError(f"cannot read rejection e-mail: {email_path}: {exc}") from exc

    sentences = _sentences(text)

    # Track which symptom labels we have already emitted (deduplicate)
    emitted_symptoms: Dict[str, SentenceMapping] = {}

    for sentence in sentences:
        lower = sentence.lower()
        matched_any = False

        for symptom in _SYMPTOM_TABLE:
            if not any(trigger in lower for trigger in symptom.triggers):
                continue

            matched_any = True
            label = symptom.label

            if label not in emitted_symptoms:
                violated, undecided, clean = _classify_rules(symptom.rule_ids, report)
                mapping = SentenceMapping(
                    sentence=sentence,
                    symptom_label=label,
                    violated=violated,
                    undecided=undecided,
                    clean=clean,
                )
                emitted_symptoms[label] = mapping
                result.matched_symptoms.append(mapping)
            # else: already emitted this symptom group; don't repeat

        if not matched_any:
            result.unmapped_sentences.append(sentence)

    return result
