# SPDX-License-Identifier: MIT
"""
tests/test_manifest_merger.py — unit tests for source/manifest_merger.py
"""

import os
import textwrap
import tempfile

import pytest

from storegreen.source.manifest_merger import merge, MergedManifest, ANDROID_NS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: str, content: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(content))
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_merge_main_only():
    with tempfile.TemporaryDirectory() as tmp:
        main = _write(os.path.join(tmp, "main", "AndroidManifest.xml"), """\
            <?xml version="1.0" encoding="utf-8"?>
            <manifest xmlns:android="http://schemas.android.com/apk/res/android"
                package="com.example.app">
                <uses-sdk android:minSdkVersion="21" android:targetSdkVersion="34" />
                <uses-permission android:name="android.permission.INTERNET" />
                <application android:label="App" />
            </manifest>
        """)
        result = merge("app", main)
        assert isinstance(result, MergedManifest)
        assert result.package_name == "com.example.app"
        assert result.target_sdk == 34
        assert result.min_sdk == 21
        # Should have the permission element
        perms = result.find_all("uses-permission")
        assert len(perms) == 1
        assert perms[0].android("name") == "android.permission.INTERNET"


def test_flavor_overrides_element():
    with tempfile.TemporaryDirectory() as tmp:
        main = _write(os.path.join(tmp, "main", "AndroidManifest.xml"), """\
            <?xml version="1.0" encoding="utf-8"?>
            <manifest xmlns:android="http://schemas.android.com/apk/res/android"
                package="com.example.app">
                <uses-sdk android:targetSdkVersion="34" />
                <application>
                    <activity android:name=".MainActivity" android:exported="false" />
                </application>
            </manifest>
        """)
        flavor = _write(os.path.join(tmp, "amazon", "AndroidManifest.xml"), """\
            <?xml version="1.0" encoding="utf-8"?>
            <manifest xmlns:android="http://schemas.android.com/apk/res/android">
                <application>
                    <activity android:name=".MainActivity" android:exported="true" />
                </application>
            </manifest>
        """)
        result = merge("app", main, [flavor], flavor="amazon")
        activities = result.find_all("activity")
        # Should only have one activity (flavor overrides main)
        assert len(activities) == 1
        # The flavor value wins (exported=true)
        assert activities[0].android("exported") == "true"
        assert activities[0].source_file == flavor


def test_library_manifest_not_included():
    """Merging never includes library (AAR) manifests — only what we pass."""
    with tempfile.TemporaryDirectory() as tmp:
        main = _write(os.path.join(tmp, "main", "AndroidManifest.xml"), """\
            <?xml version="1.0" encoding="utf-8"?>
            <manifest xmlns:android="http://schemas.android.com/apk/res/android"
                package="com.example.app">
                <uses-sdk android:targetSdkVersion="34" />
                <application />
            </manifest>
        """)
        # No flavor or build-type manifests passed — result should not contain
        # any library-contributed elements
        result = merge("app", main)
        # The result should only contain what was in main
        assert len(result.source_files) == 1
        assert result.source_files[0] == main


def test_element_source_annotation():
    with tempfile.TemporaryDirectory() as tmp:
        main = _write(os.path.join(tmp, "main", "AndroidManifest.xml"), """\
            <?xml version="1.0" encoding="utf-8"?>
            <manifest xmlns:android="http://schemas.android.com/apk/res/android"
                package="com.example.app">
                <uses-sdk android:targetSdkVersion="34" />
                <uses-permission android:name="android.permission.CAMERA" />
                <application />
            </manifest>
        """)
        result = merge("app", main)
        perms = result.find_all("uses-permission")
        assert len(perms) == 1
        assert perms[0].source_file == main
        assert perms[0].source_line >= 1


def test_merge_with_missing_main():
    result = merge("app", "/nonexistent/path/AndroidManifest.xml")
    assert result.package_name is None
    assert result.elements == []


def test_merge_invalid_xml():
    with tempfile.TemporaryDirectory() as tmp:
        bad = _write(os.path.join(tmp, "bad", "AndroidManifest.xml"), """\
            this is not XML at all
        """)
        result = merge("app", bad)
        assert result.elements == []


def test_build_type_overrides_flavor():
    with tempfile.TemporaryDirectory() as tmp:
        main = _write(os.path.join(tmp, "main", "AndroidManifest.xml"), """\
            <?xml version="1.0" encoding="utf-8"?>
            <manifest xmlns:android="http://schemas.android.com/apk/res/android"
                package="com.example.app">
                <uses-sdk android:targetSdkVersion="34" />
                <application>
                    <service android:name=".MyService" android:exported="false" />
                </application>
            </manifest>
        """)
        flavor = _write(os.path.join(tmp, "amazon", "AndroidManifest.xml"), """\
            <?xml version="1.0" encoding="utf-8"?>
            <manifest xmlns:android="http://schemas.android.com/apk/res/android">
                <application>
                    <service android:name=".MyService" android:exported="true" />
                </application>
            </manifest>
        """)
        buildtype = _write(os.path.join(tmp, "release", "AndroidManifest.xml"), """\
            <?xml version="1.0" encoding="utf-8"?>
            <manifest xmlns:android="http://schemas.android.com/apk/res/android">
                <application>
                    <service android:name=".MyService" android:exported="false" />
                </application>
            </manifest>
        """)
        result = merge("app", main, [flavor], [buildtype], flavor="amazon")
        services = result.find_all("service")
        assert len(services) == 1
        # build-type wins last
        assert services[0].android("exported") == "false"
