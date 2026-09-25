# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
bundle/aab_reader.py — ZipFile wrapper for Android App Bundles.

Provides entry-path helpers and access to individual entry bytes.
No external dependencies.  Python 3.9 compatible.
"""

from __future__ import annotations

import os
import zipfile
from typing import Iterator, List, Optional


class AabReader:
    """Read-only view of an Android App Bundle (.aab) file.

    Usage::

        with AabReader(path) as r:
            data = r.read("base/manifest/AndroidManifest.xml")
            for name in r.list_prefix("base/lib/"):
                ...
    """

    def __init__(self, path: str) -> None:
        self._path = os.path.abspath(path)
        self._zf: Optional[zipfile.ZipFile] = None

    # ------------------------------------------------------------------
    # Context-manager interface
    # ------------------------------------------------------------------

    def __enter__(self) -> "AabReader":
        self._zf = zipfile.ZipFile(self._path, "r")
        return self

    def __exit__(self, *_: object) -> None:
        if self._zf is not None:
            self._zf.close()
            self._zf = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def path(self) -> str:
        return self._path

    def namelist(self) -> List[str]:
        """Return all entry names in the bundle."""
        self._require_open()
        return self._zf.namelist()  # type: ignore[union-attr]

    def list_prefix(self, prefix: str) -> List[str]:
        """Return entry names that start with *prefix*."""
        return [n for n in self.namelist() if n.startswith(prefix)]

    def has(self, entry: str) -> bool:
        """Return True if *entry* is present in the bundle."""
        self._require_open()
        try:
            self._zf.getinfo(entry)  # type: ignore[union-attr]
            return True
        except KeyError:
            return False

    def read(self, entry: str) -> Optional[bytes]:
        """Return the bytes of *entry*, or None if it is not present."""
        self._require_open()
        try:
            return self._zf.read(entry)  # type: ignore[union-attr]
        except KeyError:
            return None

    def iter_abi_libs(self, abi: str) -> Iterator[str]:
        """Yield entry names for all .so files under base/lib/<abi>/."""
        prefix = f"base/lib/{abi}/"
        for name in self.list_prefix(prefix):
            if name.endswith(".so"):
                yield name

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_open(self) -> None:
        if self._zf is None:
            raise RuntimeError(
                "AabReader must be used as a context manager "
                "(with AabReader(path) as r:)"
            )
