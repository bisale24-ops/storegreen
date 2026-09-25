# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
source/manifest_merger.py — merges AndroidManifest.xml source sets.

Merge order: src/main → src/<flavor> → src/<buildType>
Override semantics: later layers win when android:name matches.

Library manifests from AARs are NOT merged (they cannot be read without
resolving dependencies).  When a rule depends on something a library could
contribute, it must report 'cannot be determined'.

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

ANDROID_NS = "http://schemas.android.com/apk/res/android"


@dataclass
class AnnotatedElement:
    """An XML element annotated with the source that contributed it."""
    tag: str           # local tag name, e.g. "uses-permission"
    attrib: Dict[str, str]
    source_file: str   # absolute path to the manifest that contributed this
    source_line: int   # 1-based line number in that file
    text: Optional[str] = None

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.attrib.get(key, default)

    def android(self, local_name: str) -> Optional[str]:
        """Return the value of an android: attribute."""
        return self.attrib.get(f"{{{ANDROID_NS}}}{local_name}")


@dataclass
class MergedManifest:
    """Result of the manifest merge for one module + flavor combination."""
    module_name: str
    flavor: Optional[str]          # None = main-only
    package_name: Optional[str]    # from manifest/@package
    target_sdk: Optional[int]      # from uses-sdk/@android:targetSdkVersion
    min_sdk: Optional[int]
    source_files: List[str] = field(default_factory=list)   # in merge order
    elements: List[AnnotatedElement] = field(default_factory=list)

    def find_all(self, tag: str) -> List[AnnotatedElement]:
        """Return all elements with this tag (local name)."""
        return [e for e in self.elements if e.tag == tag]

    def find_first(self, tag: str) -> Optional[AnnotatedElement]:
        results = self.find_all(tag)
        return results[0] if results else None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _a(local: str) -> str:
    """Return the Clark-notation android: attribute name."""
    return f"{{{ANDROID_NS}}}{local}"


def _parse_manifest(path: str) -> Optional[Tuple[ET.Element, Dict[int, int]]]:
    """Parse an XML manifest and return (root_element, {element_id: lineno}).

    Returns None if the file cannot be read or is not valid XML.
    The line numbers are approximated by iterparse.
    """
    try:
        line_map: Dict[int, int] = {}
        events: List[Tuple[str, ET.Element]] = []
        for event, elem in ET.iterparse(path, events=("start",)):
            # ET does not expose line numbers directly; we store them via
            # a custom attribute injected during parse
            events.append((event, elem))
        # Fall back: parse without line numbers
        tree = ET.parse(path)
        return tree.getroot(), {}
    except (ET.ParseError, OSError):
        return None


def _parse_manifest_with_lines(path: str) -> Optional[Tuple[ET.Element, Dict[str, int]]]:
    """Parse manifest; return (root, {elem_key: line}).

    Since xml.etree.ElementTree does not provide line numbers from a file
    (only from iterparse on the stream), we approximate by scanning the
    raw text for line numbers.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            raw_lines = fh.readlines()
    except OSError:
        return None

    try:
        root = ET.fromstring("".join(raw_lines))
    except ET.ParseError:
        return None

    # Build a simple tag→first-line mapping by scanning the text.
    # This is good enough for the evidence requirement (file + line).
    tag_lines: Dict[str, int] = {}
    for lineno, text in enumerate(raw_lines, 1):
        stripped = text.strip()
        if stripped.startswith("<") and not stripped.startswith("</") and not stripped.startswith("<?") and not stripped.startswith("<!--"):
            # Extract the tag name (first word after <, ignoring namespace)
            inner = stripped[1:].split()[0].rstrip(">").rstrip("/")
            inner = inner.split(":")[-1]  # strip ns prefix
            if inner not in tag_lines:
                tag_lines[inner] = lineno

    return root, tag_lines


def _element_line(raw_text: str, attrib_value: str, fallback: int = 1) -> int:
    """Find the first line in *raw_text* that contains *attrib_value*."""
    if not attrib_value:
        return fallback
    for lineno, line in enumerate(raw_text.splitlines(), 1):
        if attrib_value in line:
            return lineno
    return fallback


def _load_manifest_elements(path: str, source_label: str) -> Tuple[List[AnnotatedElement], Optional[str], Optional[int], Optional[int]]:
    """Load all child elements from a manifest file.

    Returns (elements, package_name, target_sdk, min_sdk).
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError:
        return [], None, None, None

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return [], None, None, None

    package_name = root.get("package")
    target_sdk: Optional[int] = None
    min_sdk: Optional[int] = None

    elements: List[AnnotatedElement] = []
    raw_lines = raw.splitlines()

    def best_line(elem: ET.Element) -> int:
        # Try to find the element in raw text by its name attribute
        name_val = elem.get(_a("name")) or elem.get("name") or ""
        if name_val:
            for i, line in enumerate(raw_lines, 1):
                if name_val in line:
                    return i
        # Fall back to tag name search
        local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        for i, line in enumerate(raw_lines, 1):
            if f"<{local}" in line or f"<android:{local}" in line:
                return i
        return 1

    def local_tag(elem: ET.Element) -> str:
        tag = elem.tag
        if "}" in tag:
            return tag.split("}")[-1]
        return tag

    # uses-sdk is a direct child of manifest
    for child in root:
        ltag = local_tag(child)
        if ltag == "uses-sdk":
            ts = child.get(_a("targetSdkVersion"))
            ms = child.get(_a("minSdkVersion"))
            if ts and ts.isdigit():
                target_sdk = int(ts)
            if ms and ms.isdigit():
                min_sdk = int(ms)
            continue

        # Recurse one level into <application> to get activities, receivers, etc.
        if ltag == "application":
            for app_child in child:
                app_ltag = local_tag(app_child)
                elements.append(AnnotatedElement(
                    tag=app_ltag,
                    attrib=dict(app_child.attrib),
                    source_file=path,
                    source_line=best_line(app_child),
                    text=(app_child.text or "").strip() or None,
                ))
            # Also record the application element itself
            elements.append(AnnotatedElement(
                tag="application",
                attrib=dict(child.attrib),
                source_file=path,
                source_line=best_line(child),
            ))
            continue

        elements.append(AnnotatedElement(
            tag=ltag,
            attrib=dict(child.attrib),
            source_file=path,
            source_line=best_line(child),
            text=(child.text or "").strip() or None,
        ))

    return elements, package_name, target_sdk, min_sdk


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def merge(
    module_name: str,
    main_manifest_path: Optional[str],
    flavor_manifest_paths: Optional[List[str]] = None,
    build_type_manifest_paths: Optional[List[str]] = None,
    flavor: Optional[str] = None,
) -> MergedManifest:
    """Merge manifest source sets in order: main → flavor → build-type.

    Override semantics: an element in a later layer replaces an element with
    the same (tag, android:name) from an earlier layer.  Elements without an
    android:name are appended (they cannot be safely merged without a full
    aapt2 run).

    Library manifests from AARs are not included.
    """
    merged = MergedManifest(
        module_name=module_name,
        flavor=flavor,
        package_name=None,
        target_sdk=None,
        min_sdk=None,
    )

    # (tag, android:name) → AnnotatedElement  — last writer wins
    keyed: Dict[Tuple[str, Optional[str]], AnnotatedElement] = {}
    unnamed: List[AnnotatedElement] = []

    all_paths: List[str] = []
    if main_manifest_path and os.path.isfile(main_manifest_path):
        all_paths.append(main_manifest_path)
    for p in (flavor_manifest_paths or []):
        if os.path.isfile(p):
            all_paths.append(p)
    for p in (build_type_manifest_paths or []):
        if os.path.isfile(p):
            all_paths.append(p)

    for path in all_paths:
        merged.source_files.append(path)
        elements, pkg, ts, ms = _load_manifest_elements(path, path)
        if pkg and merged.package_name is None:
            merged.package_name = pkg
        if ts is not None:
            merged.target_sdk = ts   # later wins
        if ms is not None:
            merged.min_sdk = ms

        for elem in elements:
            android_name = elem.android("name")
            if android_name:
                keyed[(elem.tag, android_name)] = elem
            else:
                unnamed.append(elem)

    merged.elements = list(keyed.values()) + unnamed
    return merged
