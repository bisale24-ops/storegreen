# SPDX-License-Identifier: MIT
"""
tests/test_project_layout.py — unit tests for source/project_layout.py
"""

import os
import textwrap
import tempfile

import pytest

from storegreen.source.project_layout import discover, ModuleLayout


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_android_module(base: str, name: str, flavors: list = None, has_manifest: bool = True) -> str:
    """Create a minimal Android module directory and return its path."""
    module_dir = os.path.join(base, name)
    os.makedirs(module_dir, exist_ok=True)

    flavor_block = ""
    if flavors:
        flavor_entries = "\n".join(f"        {f} {{}}" for f in flavors)
        flavor_block = f"""
    flavorDimensions "store"
    productFlavors {{
{flavor_entries}
    }}"""

    gradle_text = textwrap.dedent(f"""\
        plugins {{
            id 'com.android.application'
        }}
        android {{
            compileSdk 34
            defaultConfig {{
                applicationId "com.example.{name}"
                minSdk 21
                targetSdk 34
                versionCode 1
                versionName "1.0"
            }}{flavor_block}
            buildTypes {{
                release {{ isMinifyEnabled false }}
                debug {{}}
            }}
        }}
    """)
    with open(os.path.join(module_dir, "build.gradle"), "w") as f:
        f.write(gradle_text)

    if has_manifest:
        src_main = os.path.join(module_dir, "src", "main")
        os.makedirs(src_main, exist_ok=True)
        with open(os.path.join(src_main, "AndroidManifest.xml"), "w") as f:
            f.write(textwrap.dedent(f"""\
                <?xml version="1.0" encoding="utf-8"?>
                <manifest xmlns:android="http://schemas.android.com/apk/res/android"
                    package="com.example.{name}">
                    <application android:label="{name}" />
                </manifest>
            """))

        if flavors:
            for flavor in flavors:
                flavor_dir = os.path.join(module_dir, "src", flavor)
                os.makedirs(flavor_dir, exist_ok=True)
                with open(os.path.join(flavor_dir, "AndroidManifest.xml"), "w") as f:
                    f.write(textwrap.dedent(f"""\
                        <?xml version="1.0" encoding="utf-8"?>
                        <manifest xmlns:android="http://schemas.android.com/apk/res/android">
                        </manifest>
                    """))

    return module_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_single_module_no_settings():
    with tempfile.TemporaryDirectory() as tmp:
        _make_android_module(tmp, "app", flavors=["amazon", "google"])
        layout = discover(tmp)
        assert len(layout.modules) == 1
        module = layout.modules[0]
        assert module.name == "app"
        assert "amazon" in module.flavors
        assert "google" in module.flavors
        assert module.main_manifest is not None
        assert os.path.isfile(module.main_manifest)


def test_module_has_flavor_manifests():
    with tempfile.TemporaryDirectory() as tmp:
        _make_android_module(tmp, "app", flavors=["amazon", "google"])
        layout = discover(tmp)
        module = layout.modules[0]
        assert "amazon" in module.flavor_manifests
        assert "google" in module.flavor_manifests


def test_multi_module_with_settings():
    with tempfile.TemporaryDirectory() as tmp:
        # Write settings.gradle
        with open(os.path.join(tmp, "settings.gradle"), "w") as f:
            f.write("include ':app', ':wear'\n")
        _make_android_module(tmp, "app")
        _make_android_module(tmp, "wear")
        layout = discover(tmp)
        names = [m.name for m in layout.modules]
        assert "app" in names
        assert "wear" in names


def test_non_android_directory_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        _make_android_module(tmp, "app")
        # Add a non-Android subdirectory
        other = os.path.join(tmp, "scripts")
        os.makedirs(other)
        with open(os.path.join(other, "deploy.sh"), "w") as f:
            f.write("#!/bin/bash\n")
        layout = discover(tmp)
        names = [m.name for m in layout.modules]
        assert "scripts" not in names


def test_application_id_parsed():
    with tempfile.TemporaryDirectory() as tmp:
        _make_android_module(tmp, "app")
        layout = discover(tmp)
        module = layout.modules[0]
        assert module.application_id == "com.example.app"


def test_build_types_parsed():
    with tempfile.TemporaryDirectory() as tmp:
        _make_android_module(tmp, "app")
        layout = discover(tmp)
        module = layout.modules[0]
        assert "release" in module.build_types
        assert "debug" in module.build_types


def test_get_module_by_name():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "settings.gradle"), "w") as f:
            f.write("include ':app', ':lib'\n")
        _make_android_module(tmp, "app")
        _make_android_module(tmp, "lib")
        layout = discover(tmp)
        assert layout.get_module("app") is not None
        assert layout.get_module("missing") is None


def test_empty_repo_returns_empty_layout():
    with tempfile.TemporaryDirectory() as tmp:
        layout = discover(tmp)
        assert layout.modules == []
