# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
bundle/manifest_bytes.py — UTF-8 string search in protobuf manifest bytes.

AAB manifests use protobuf wire format, not AXML.  The strings the Amazon
rules care about appear as plain UTF-8 substrings in the binary, so we do
not need a full protobuf parser for presence checks.

Confidence caveat (from spec §1): absence is a finding; presence is
"declared, structure not verifiable from a bundle, re-run on the source tree".

Python 3.9 compatible, standard library only.
"""

from __future__ import annotations

from typing import Optional, Tuple


# Entry path of the manifest inside a bundle
MANIFEST_ENTRY = "base/manifest/AndroidManifest.xml"


class ManifestBytes:
    """Wrapper around raw protobuf manifest bytes that supports string search."""

    def __init__(self, data: bytes, entry_path: str = MANIFEST_ENTRY) -> None:
        self._data = data
        self.entry_path = entry_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def contains(self, text: str) -> bool:
        """Return True if *text* appears as a UTF-8 substring in the manifest."""
        return text.encode("utf-8") in self._data

    def find_offset(self, text: str) -> Optional[int]:
        """Return the byte offset of the first occurrence of *text*, or None."""
        needle = text.encode("utf-8")
        idx = self._data.find(needle)
        return idx if idx >= 0 else None

    def search(self, text: str) -> Tuple[bool, Optional[str]]:
        """Search for *text* and return (found, snippet).

        *snippet* is a short printable context around the match, or None if
        not found.  Useful for the ``found`` field of an Evidence object.
        """
        needle = text.encode("utf-8")
        idx = self._data.find(needle)
        if idx < 0:
            return False, None
        # Grab up to 60 bytes around the match for a readable snippet
        start = max(0, idx - 10)
        end = min(len(self._data), idx + len(needle) + 10)
        raw_ctx = self._data[start:end]
        # Decode printable ASCII only for the snippet
        snippet = "".join(chr(b) if 32 <= b < 127 else "." for b in raw_ctx)
        return True, snippet

    @property
    def size(self) -> int:
        return len(self._data)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def from_aab(reader: "AabReader") -> Optional["ManifestBytes"]:  # noqa: F821
    """Read the manifest bytes from an open AabReader.

    Returns None if the entry is missing (caller should treat as Undecided).
    """
    data = reader.read(MANIFEST_ENTRY)
    if data is None:
        return None
    return ManifestBytes(data, MANIFEST_ENTRY)
