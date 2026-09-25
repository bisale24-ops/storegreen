# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
source/gradle_reader.py — reads build configuration without running Gradle.

Resolution order:
  1. gradle/libs.versions.toml   (version catalog)
  2. Literal value in build.gradle[.kts]
  3. ext / buildSrc constant (plain substitution only)

If the value resolves to a computed expression, a function call, or an
environment variable, the reader stops and returns an Undecided with the
line that blocked it.

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Union

from storegreen.rules.base import Evidence, Undecided


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ResolvedValue:
    """A value that was successfully resolved to a string."""
    value: str
    source_file: str   # absolute path to where it was resolved
    source_line: int   # 1-based line number


@dataclass
class GradleConfig:
    """Resolved build configuration for one module."""
    module_root: str
    build_gradle: str

    target_sdk: Union[ResolvedValue, Undecided, None] = None
    min_sdk: Union[ResolvedValue, Undecided, None] = None
    compile_sdk: Union[ResolvedValue, Undecided, None] = None
    version_code: Union[ResolvedValue, Undecided, None] = None
    version_name: Union[ResolvedValue, Undecided, None] = None
    application_id: Union[ResolvedValue, Undecided, None] = None

    # dependency name → resolved version (or Undecided)
    dependencies: Dict[str, Union[ResolvedValue, Undecided]] = field(default_factory=dict)

    # raw build types found in the file
    is_minify_enabled: Union[ResolvedValue, Undecided, None] = None
    proguard_files: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# TOML catalog parser (minimal, stdlib only)
# ---------------------------------------------------------------------------

def _parse_versions_toml(path: str) -> Dict[str, Tuple[str, int]]:
    """Return {alias: (version_string, line_number)} from a libs.versions.toml.

    Only parses the [versions] and [libraries] tables.
    Values that are not plain strings are skipped.
    """
    result: Dict[str, Tuple[str, int]] = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return result

    in_versions = False
    in_libraries = False
    lib_versions: Dict[str, Tuple[str, int]] = {}

    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            in_versions = section == "versions"
            in_libraries = section == "libraries"
            continue
        if line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip().strip('"')
        value = value.strip()

        if in_versions:
            # versions.foo = "1.2.3"
            if value.startswith('"') and value.endswith('"'):
                result[key] = (value[1:-1], lineno)
            elif value.startswith("'") and value.endswith("'"):
                result[key] = (value[1:-1], lineno)
        elif in_libraries:
            # module = { group = "x", name = "y", version.ref = "foo" }
            # or module = "group:name:version"
            ref_m = re.search(r'version\.ref\s*=\s*["\']([^"\']+)["\']', value)
            if ref_m:
                lib_versions[key] = (ref_m.group(1), lineno)  # type: ignore
            # plain version inline: module = { ..., version = "1.2.3" }
            ver_m = re.search(r'(?<!\.)version\s*=\s*["\']([^"\']+)["\']', value)
            if ver_m and not ref_m:
                result[key] = (ver_m.group(1), lineno)

    # Resolve library version.refs
    for lib_key, (ref_alias, lib_line) in lib_versions.items():
        if ref_alias in result:
            result[lib_key] = (result[ref_alias][0], result[ref_alias][1])
        else:
            # Unresolvable ref — record it with empty version to signal failure
            result[lib_key] = ("__unresolved__", lib_line)

    return result


# ---------------------------------------------------------------------------
# Gradle text helpers
# ---------------------------------------------------------------------------

# Patterns for key gradle properties
_SDK_PROPS = {
    "target_sdk": re.compile(r'targetSdk(?:Version)?\s*[=:]?\s*(\S+)', re.IGNORECASE),
    "min_sdk": re.compile(r'minSdk(?:Version)?\s*[=:]?\s*(\S+)', re.IGNORECASE),
    "compile_sdk": re.compile(r'compileSdk(?:Version)?\s*[=:]?\s*(\S+)', re.IGNORECASE),
    "version_code": re.compile(r'versionCode\s*[=:]?\s*(\S+)', re.IGNORECASE),
    "version_name": re.compile(r'versionName\s*[=:]?\s*["\']?([^"\'\\n]+?)["\']?\s*$', re.IGNORECASE | re.MULTILINE),
    "application_id": re.compile(r'applicationId\s*[=:]?\s*["\']([A-Za-z0-9_.]+)["\']', re.IGNORECASE),
}

# Patterns that mean "we cannot resolve this"
_UNRESOLVABLE = re.compile(
    r'System\.getenv|getProperty|rootProject\.|ext\.|buildSrc\.'
    r'|\bfile\s*\(|\bproject\s*\(|\bproviders\.'
)

# ext.foo = value  (in root build.gradle or android { defaultConfig { } })
_EXT_RE = re.compile(r'ext\s*\.\s*(\w+)\s*=\s*(.+)')

# Implementation dependency patterns
_DEP_RE = re.compile(
    r'(?:implementation|api|compileOnly|runtimeOnly|amazonImplementation|googleImplementation)'
    r'\s*\(?["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_DEP_CATALOG_RE = re.compile(
    r'(?:implementation|api|compileOnly|runtimeOnly|amazonImplementation|googleImplementation)'
    r'\s*\(?\s*(?:libs\.)(\w+(?:\.\w+)*)',
    re.IGNORECASE,
)

_MINIFY_RE = re.compile(r'isMinifyEnabled\s*[=:]?\s*(true|false)', re.IGNORECASE)


# Matches a bare version string like 8.0.0, 1.2.3-alpha04, 36, etc.
# Used when the surrounding quotes have already been stripped (e.g. from
# a gradle coordinate "group:artifact:version" split).
_BARE_VERSION_RE = re.compile(r'^[\d][\w.\-+]*$')


def _is_literal_int(s: str) -> bool:
    return s.strip().lstrip("-").isdigit()


def _is_literal_string(s: str) -> bool:
    s = s.strip()
    return (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'"))


def _is_bare_literal(s: str) -> bool:
    """True for already-unquoted values that are clearly static literals.

    Covers version strings (8.0.0, 1.2.3-alpha04), application IDs
    (com.example.app), and plain integers.  Returns False for anything
    containing $, (, whitespace, or env-variable markers.
    """
    s = s.strip()
    if not s:
        return False
    # Reject anything that looks like a computed expression
    if any(c in s for c in ('$', '(', ')', ' ', '\t', '\n')):
        return False
    # Must start with a digit, letter, or underscore (not an operator)
    return bool(_BARE_VERSION_RE.match(s) or re.match(r'^[a-zA-Z_][a-zA-Z0-9_.]*$', s))


def _resolve_value(
    raw: str,
    lineno: int,
    source_file: str,
    ext_map: Dict[str, Tuple[str, int]],
    catalog: Dict[str, Tuple[str, int]],
    rule_id: str = "?",
    already_unquoted: bool = False,
    catalog_path: Optional[str] = None,
) -> Union[ResolvedValue, Undecided]:
    """Attempt to resolve a raw gradle value to a concrete string.

    Parameters
    ----------
    already_unquoted : bool
        True when the caller has already stripped quotes (e.g. a version
        extracted from a "group:artifact:version" coordinate split, or an
        applicationId captured by a regex group inside the quotes).
        In that case a bare dotted string like "8.0.0" or "com.example.app"
        is accepted as a literal without requiring wrapping quotes.
    """
    raw = raw.strip().rstrip(",").rstrip(";")

    # Literal integer
    if _is_literal_int(raw):
        return ResolvedValue(value=raw, source_file=source_file, source_line=lineno)

    # Quoted string (e.g. "8.0.0" still has its quotes at this point)
    if _is_literal_string(raw):
        return ResolvedValue(value=raw[1:-1], source_file=source_file, source_line=lineno)

    # Already-unquoted bare literal (version string, application id, etc.)
    if already_unquoted and _is_bare_literal(raw):
        return ResolvedValue(value=raw, source_file=source_file, source_line=lineno)

    # Catalog reference: libs.versions.xxx
    cat_m = re.match(r'libs\.versions\.(\w+)(?:\.get\(\))?', raw)
    if cat_m:
        alias = cat_m.group(1)
        if alias in catalog:
            v, vline = catalog[alias]
            if v == "__unresolved__":
                return Undecided(
                    rule=rule_id,
                    reason=f"version catalog alias {alias!r} references an unresolvable value",
                    evidence=Evidence(file=source_file, line=lineno, found=raw, expected="a literal value"),
                )
            # Evidence points at the toml catalog file where the value is defined
            resolved_file = catalog_path if catalog_path else source_file
            return ResolvedValue(value=v, source_file=resolved_file, source_line=vline)

    # ext.foo reference
    ext_m = re.match(r'(?:ext\.)?(\w+)', raw)
    if ext_m:
        name = ext_m.group(1)
        if name in ext_map:
            v, vline = ext_map[name]
            return ResolvedValue(value=v, source_file=source_file, source_line=vline)

    # Anything else — unresolvable
    if _UNRESOLVABLE.search(raw):
        return Undecided(
            rule=rule_id,
            reason=f"value is a computed expression: {raw!r}",
            evidence=Evidence(file=source_file, line=lineno, found=raw, expected="a literal value"),
        )

    return Undecided(
        rule=rule_id,
        reason=f"could not resolve: {raw!r}",
        evidence=Evidence(file=source_file, line=lineno, found=raw, expected="a literal value"),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read(module_root: str, build_gradle: str, repo_root: Optional[str] = None) -> GradleConfig:
    """Read and resolve Gradle build config for one module.

    Parameters
    ----------
    module_root:  absolute path to the module directory
    build_gradle: absolute path to build.gradle or build.gradle.kts
    repo_root:    absolute path to the repo root (for catalog lookup)
    """
    cfg = GradleConfig(module_root=module_root, build_gradle=build_gradle)

    if repo_root is None:
        repo_root = os.path.dirname(module_root)

    # ------------------------------------------------------------------
    # 1. Load version catalog
    # ------------------------------------------------------------------
    catalog: Dict[str, Tuple[str, int]] = {}
    catalog_path_candidate = os.path.join(repo_root, "gradle", "libs.versions.toml")
    catalog_path: Optional[str] = None
    if os.path.isfile(catalog_path_candidate):
        catalog_path = catalog_path_candidate
        catalog = _parse_versions_toml(catalog_path)

    # ------------------------------------------------------------------
    # 2. Read build.gradle text
    # ------------------------------------------------------------------
    try:
        with open(build_gradle, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return cfg

    full_text = "".join(lines)

    # ------------------------------------------------------------------
    # 3. Build an ext map from root build.gradle
    # ------------------------------------------------------------------
    ext_map: Dict[str, Tuple[str, int]] = {}
    root_gradle_candidates = [
        os.path.join(repo_root, "build.gradle.kts"),
        os.path.join(repo_root, "build.gradle"),
    ]
    for rg in root_gradle_candidates:
        if os.path.isfile(rg) and rg != build_gradle:
            try:
                with open(rg, "r", encoding="utf-8", errors="replace") as fh:
                    root_lines = fh.readlines()
                for li, rl in enumerate(root_lines, 1):
                    m = _EXT_RE.search(rl)
                    if m:
                        k, v = m.group(1), m.group(2).strip().strip('"').strip("'")
                        ext_map[k] = (v, li)
            except OSError:
                pass
            break

    # Also pick up ext from the module gradle itself
    for li, line in enumerate(lines, 1):
        m = _EXT_RE.search(line)
        if m:
            k, v = m.group(1), m.group(2).strip().strip('"').strip("'")
            ext_map[k] = (v, li)

    # ------------------------------------------------------------------
    # 4. Extract SDK properties
    # ------------------------------------------------------------------
    for prop_key, pattern in _SDK_PROPS.items():
        for li, line in enumerate(lines, 1):
            m = pattern.search(line)
            if m:
                raw = m.group(1)
                # The regex for application_id and version_name captures inside
                # the quotes, so the value is already unquoted.
                already_unquoted = prop_key in ("application_id", "version_name")
                resolved = _resolve_value(
                    raw, li, build_gradle, ext_map, catalog,
                    rule_id=prop_key, already_unquoted=already_unquoted,
                    catalog_path=catalog_path if catalog else None,
                )
                setattr(cfg, prop_key, resolved)
                break

    # ------------------------------------------------------------------
    # 5. Extract dependencies
    # ------------------------------------------------------------------
    for li, line in enumerate(lines, 1):
        # Catalog-style: libs.amazonIap or libs.amazon.appstore.sdk
        m = _DEP_CATALOG_RE.search(line)
        if m:
            alias = m.group(1).replace(".", "-")  # libs.amazon.appstore.sdk → amazon-appstore-sdk
            # Normalize to group:artifact style by looking up in catalog
            if alias in catalog:
                v, vline = catalog[alias]
                if v != "__unresolved__":
                    cfg.dependencies[alias] = ResolvedValue(
                        value=v, source_file=catalog_path or build_gradle, source_line=vline
                    )
                else:
                    cfg.dependencies[alias] = Undecided(
                        rule="gradle",
                        reason=f"catalog alias {alias!r} unresolvable",
                        evidence=Evidence(file=build_gradle, line=li, found=line.strip(), expected="a version string"),
                    )
            continue

        # Literal: "group:artifact:version"
        m2 = _DEP_RE.search(line)
        if m2:
            coord = m2.group(1)
            parts = coord.split(":")
            if len(parts) >= 3:
                group_artifact = ":".join(parts[:2])
                version_raw = parts[2]
                # Version is already unquoted — it was split out of the
                # coordinate string that was itself inside the outer quotes.
                resolved = _resolve_value(
                    version_raw, li, build_gradle, ext_map, catalog,
                    rule_id="dep", already_unquoted=True,
                    catalog_path=catalog_path if catalog else None,
                )
                cfg.dependencies[group_artifact] = resolved
            elif len(parts) == 2:
                # No version in literal — could be from BOM; record as undecided
                group_artifact = coord
                cfg.dependencies[group_artifact] = Undecided(
                    rule="dep",
                    reason="dependency has no version (may use a BOM)",
                    evidence=Evidence(file=build_gradle, line=li, found=coord, expected="group:artifact:version"),
                )

    # ------------------------------------------------------------------
    # 6. isMinifyEnabled
    # ------------------------------------------------------------------
    for li, line in enumerate(lines, 1):
        m = _MINIFY_RE.search(line)
        if m:
            cfg.is_minify_enabled = ResolvedValue(
                value=m.group(1).lower(),
                source_file=build_gradle,
                source_line=li,
            )
            break

    return cfg
