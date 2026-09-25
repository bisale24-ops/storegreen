# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
source/project_layout.py — discovers modules, flavors, and build types.

Returns a ProjectLayout that describes every Android module found under the
repo root.  Gradle is never executed; the information is read from
build.gradle / build.gradle.kts and from the directory tree.

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ModuleLayout:
    """Discovered structure of a single Gradle module."""
    name: str               # e.g. "app"
    root: str               # absolute path to the module directory
    build_gradle: str       # absolute path to build.gradle or build.gradle.kts
    # Source sets (absolute paths); may not all exist on disk
    main_manifest: Optional[str] = None    # src/main/AndroidManifest.xml
    flavors: List[str] = field(default_factory=list)   # flavor names only
    build_types: List[str] = field(default_factory=list)  # "release", "debug", …
    # flavor dir → list of manifest paths that exist
    flavor_manifests: Dict[str, List[str]] = field(default_factory=dict)
    application_id: Optional[str] = None   # read from build.gradle if literal


@dataclass
class ProjectLayout:
    """Top-level project discovery result."""
    repo_root: str
    modules: List[ModuleLayout] = field(default_factory=list)

    def get_module(self, name: str) -> Optional[ModuleLayout]:
        for m in self.modules:
            if m.name == name:
                return m
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_APP_ID_RE = re.compile(
    r'applicationId\s+["\']([A-Za-z0-9_.]+)["\']'
)
_APP_ID_KTS_RE = re.compile(
    r'applicationId\s*=\s*["\']([A-Za-z0-9_.]+)["\']'
)


def _read_text(path: str) -> Optional[str]:
    """Return file contents or None if unreadable."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _extract_block(text: str, keyword: str) -> Optional[str]:
    """Return the text of the first top-level '{…}' block after *keyword*.

    Handles arbitrary nesting depth by counting braces.  Returns None if
    the keyword is not found or the block is not balanced.
    """
    start = text.find(keyword)
    if start < 0:
        return None
    brace_start = text.find("{", start)
    if brace_start < 0:
        return None
    depth = 0
    for i in range(brace_start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[brace_start + 1 : i]
    return None  # unbalanced


def _names_in_block(block: str) -> List[str]:
    """Return names of all direct children declared as `name { … }` in *block*.

    Handles the pattern seen in both productFlavors and buildTypes:
        amazon { … }
        google { … }
    Only captures names at depth 0 (direct children of the block), skipping
    the body of each child entry.

    Algorithm: track brace depth across the whole block.  Each time depth is
    0 and we see an identifier immediately followed (possibly with whitespace)
    by '{', record that name and let the depth counter absorb the body.
    """
    names: List[str] = []
    depth = 0
    i = 0
    n = len(block)
    while i < n:
        ch = block[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0 and ch not in (" ", "\t", "\n", "\r"):
            # Try to match an identifier followed (with optional whitespace) by '{'
            m = re.match(r'([A-Za-z_]\w*)\s*\{', block[i:])
            if m:
                name = m.group(1)
                if name not in ("create", "getByName", "named", "maybeCreate"):
                    names.append(name)
                # Don't advance i past the '{' here — let the main loop hit it
                # next and increment depth.  Just skip past the identifier chars.
                i += len(name)  # loop will do i+=1 → lands on whitespace or '{'
                continue
        i += 1
    return names


def _parse_flavors(gradle_text: str) -> List[str]:
    block = _extract_block(gradle_text, "productFlavors")
    if block is None:
        return []
    return _names_in_block(block)


def _parse_build_types(gradle_text: str) -> List[str]:
    block = _extract_block(gradle_text, "buildTypes")
    if block is None:
        return ["release", "debug"]
    names = _names_in_block(block)
    return names if names else ["release", "debug"]


def _parse_application_id(gradle_text: str) -> Optional[str]:
    for pattern in (_APP_ID_KTS_RE, _APP_ID_RE):
        m = pattern.search(gradle_text)
        if m:
            return m.group(1)
    return None


def _find_manifest(module_root: str, source_set: str) -> Optional[str]:
    candidate = os.path.join(module_root, "src", source_set, "AndroidManifest.xml")
    return candidate if os.path.isfile(candidate) else None


def _flavor_manifest_paths(module_root: str, flavor: str) -> List[str]:
    """Return all manifest paths for a flavor (may be empty if none exist)."""
    paths: List[str] = []
    for source_set in (flavor,):
        p = _find_manifest(module_root, source_set)
        if p:
            paths.append(p)
    return paths


def _is_android_module(directory: str) -> Optional[str]:
    """Return the path to build.gradle(.kts) if this looks like an Android module."""
    for name in ("build.gradle.kts", "build.gradle"):
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate):
            text = _read_text(candidate) or ""
            if "android {" in text or "com.android.application" in text or "com.android.library" in text:
                return candidate
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def discover(repo_root: str) -> ProjectLayout:
    """Walk *repo_root* and return a ProjectLayout describing every Android module.

    Strategy:
    - If ``repo_root/build.gradle`` is itself an Android module, treat the root
      as a single-module project named after the directory.
    - Otherwise scan one level of sub-directories for modules.
    - ``settings.gradle`` / ``settings.gradle.kts`` ``include`` lines take
      precedence when present, because they are authoritative.
    """
    repo_root = os.path.abspath(repo_root)
    layout = ProjectLayout(repo_root=repo_root)

    # ------------------------------------------------------------------
    # 1.  Try to read module names from settings.gradle[.kts]
    # ------------------------------------------------------------------
    module_names: List[str] = []
    for settings_name in ("settings.gradle.kts", "settings.gradle"):
        settings_path = os.path.join(repo_root, settings_name)
        text = _read_text(settings_path)
        if text:
            # Handles all common forms:
            #   include ':app', ':wear'
            #   include(":app", ":wear")
            #   include(":app")
            # Strategy: find each include statement, then extract all
            # module names (after the colon) from that line/call.
            found: List[str] = []
            for line in text.splitlines():
                if "include" not in line:
                    continue
                # Extract every :name or "name" or 'name' token on the line
                # that follows an include keyword.
                # Match: optional colon, then the module name word.
                names_on_line = re.findall(r'["\']:?(\w+)["\']', line)
                found.extend(names_on_line)
            if found:
                module_names = found
                break

    # ------------------------------------------------------------------
    # 2.  Fall back: scan directories + root itself
    # ------------------------------------------------------------------
    if not module_names:
        candidates = [repo_root] + [
            os.path.join(repo_root, d)
            for d in os.listdir(repo_root)
            if os.path.isdir(os.path.join(repo_root, d))
            and not d.startswith(".")
            and d not in ("build", "gradle", "prep", "fixtures", "tests", "src",
                          "bob_sessions", "runs", "video")
        ]
        for d in candidates:
            bg = _is_android_module(d)
            if bg:
                name = os.path.basename(d) if d != repo_root else os.path.basename(repo_root)
                _add_module(layout, name, d, bg)
        return layout

    # ------------------------------------------------------------------
    # 3.  Resolve the named modules
    # ------------------------------------------------------------------
    for name in module_names:
        module_dir = os.path.join(repo_root, name)
        if not os.path.isdir(module_dir):
            continue
        bg = _is_android_module(module_dir)
        if bg:
            _add_module(layout, name, module_dir, bg)

    # If settings names exist but none resolved, fall back to root
    if not layout.modules:
        bg = _is_android_module(repo_root)
        if bg:
            _add_module(layout, os.path.basename(repo_root), repo_root, bg)

    return layout


def _add_module(layout: ProjectLayout, name: str, module_dir: str, build_gradle: str) -> None:
    gradle_text = _read_text(build_gradle) or ""
    flavors = _parse_flavors(gradle_text)
    build_types = _parse_build_types(gradle_text)
    app_id = _parse_application_id(gradle_text)

    main_manifest = _find_manifest(module_dir, "main")

    flavor_manifests: Dict[str, List[str]] = {}
    for f in flavors:
        paths = _flavor_manifest_paths(module_dir, f)
        if paths:
            flavor_manifests[f] = paths

    layout.modules.append(ModuleLayout(
        name=name,
        root=module_dir,
        build_gradle=build_gradle,
        main_manifest=main_manifest,
        flavors=flavors,
        build_types=build_types,
        flavor_manifests=flavor_manifests,
        application_id=app_id,
    ))
