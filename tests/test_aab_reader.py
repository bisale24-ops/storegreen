# SPDX-License-Identifier: MIT
"""
tests/test_aab_reader.py — unit tests for bundle/aab_reader.py and
bundle/manifest_bytes.py
"""

import io
import os
import tempfile
import zipfile

import pytest

from storegreen.bundle.aab_reader import AabReader
from storegreen.bundle.manifest_bytes import ManifestBytes, MANIFEST_ENTRY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_aab(tmp: str, entries: dict) -> str:
    """Create a minimal .aab (zip) with the given {name: bytes} entries."""
    path = os.path.join(tmp, "test.aab")
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


# ---------------------------------------------------------------------------
# AabReader
# ---------------------------------------------------------------------------

class TestAabReader:
    def test_context_manager(self, tmp_path):
        path = _make_aab(str(tmp_path), {
            "base/manifest/AndroidManifest.xml": b"\x0a\x00manifest",
            "base/assets/AppstoreAuthenticationKey.pem": b"-----BEGIN CERTIFICATE-----",
        })
        with AabReader(path) as r:
            assert r.has(MANIFEST_ENTRY)
            assert r.has("base/assets/AppstoreAuthenticationKey.pem")
            assert not r.has("base/assets/nonexistent.pem")

    def test_read_returns_bytes(self, tmp_path):
        data = b"\x0a\x00hello world"
        path = _make_aab(str(tmp_path), {MANIFEST_ENTRY: data})
        with AabReader(path) as r:
            result = r.read(MANIFEST_ENTRY)
        assert result == data

    def test_read_missing_returns_none(self, tmp_path):
        path = _make_aab(str(tmp_path), {MANIFEST_ENTRY: b"data"})
        with AabReader(path) as r:
            result = r.read("nonexistent/entry")
        assert result is None

    def test_list_prefix(self, tmp_path):
        path = _make_aab(str(tmp_path), {
            "base/lib/arm64-v8a/libfoo.so": b"\x7fELF",
            "base/lib/arm64-v8a/libbar.so": b"\x7fELF",
            "base/lib/x86/libfoo.so": b"\x7fELF",
            "base/manifest/AndroidManifest.xml": b"",
        })
        with AabReader(path) as r:
            arm64 = r.list_prefix("base/lib/arm64-v8a/")
        assert len(arm64) == 2
        assert all(n.startswith("base/lib/arm64-v8a/") for n in arm64)

    def test_iter_abi_libs(self, tmp_path):
        path = _make_aab(str(tmp_path), {
            "base/lib/arm64-v8a/libfoo.so": b"\x7fELF",
            "base/lib/arm64-v8a/libbar.so": b"\x7fELF",
            "base/lib/arm64-v8a/resources.pb": b"",  # not a .so
        })
        with AabReader(path) as r:
            libs = list(r.iter_abi_libs("arm64-v8a"))
        assert len(libs) == 2
        assert all(n.endswith(".so") for n in libs)

    def test_requires_context_manager(self, tmp_path):
        path = _make_aab(str(tmp_path), {MANIFEST_ENTRY: b""})
        r = AabReader(path)
        with pytest.raises(RuntimeError, match="context manager"):
            r.read(MANIFEST_ENTRY)

    def test_namelist(self, tmp_path):
        entries = {"a/b.txt": b"hello", "c/d.so": b"data"}
        path = _make_aab(str(tmp_path), entries)
        with AabReader(path) as r:
            names = r.namelist()
        assert set(names) == set(entries.keys())


# ---------------------------------------------------------------------------
# ManifestBytes
# ---------------------------------------------------------------------------

class TestManifestBytes:
    def _manifest(self, text: str) -> ManifestBytes:
        # Simulate protobuf-style bytes that contain readable UTF-8 strings
        data = b"\x0a\x00" + text.encode("utf-8") + b"\x00\x00"
        return ManifestBytes(data)

    def test_contains_present_string(self):
        m = self._manifest("com.amazon.device.iap.ResponseReceiver")
        assert m.contains("com.amazon.device.iap.ResponseReceiver")

    def test_contains_absent_string(self):
        m = self._manifest("com.amazon.device.iap.ResponseReceiver")
        assert not m.contains("com.amazon.venezia")

    def test_search_found_returns_snippet(self):
        m = self._manifest("com.amazon.venezia packaged here")
        found, snippet = m.search("com.amazon.venezia")
        assert found is True
        assert snippet is not None
        assert "venezia" in snippet

    def test_search_not_found(self):
        m = self._manifest("nothing relevant")
        found, snippet = m.search("com.amazon.venezia")
        assert found is False
        assert snippet is None

    def test_empty_manifest(self):
        m = ManifestBytes(b"")
        assert not m.contains("anything")
        assert m.size == 0

    def test_find_offset(self):
        m = self._manifest("hello world")
        offset = m.find_offset("world")
        assert offset is not None
        assert offset > 0

    def test_find_offset_missing(self):
        m = self._manifest("hello world")
        assert m.find_offset("venus") is None
