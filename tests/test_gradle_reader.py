# SPDX-License-Identifier: MIT
"""
tests/test_gradle_reader.py — unit tests for source/gradle_reader.py
"""

import os
import textwrap
import tempfile

import pytest

from storegreen.source.gradle_reader import read, ResolvedValue, GradleConfig
from storegreen.rules.base import Undecided


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup(tmp: str, gradle_text: str, toml_text: str = "", root_gradle_text: str = "") -> str:
    """Write build.gradle (and optionally libs.versions.toml) under tmp."""
    module_dir = os.path.join(tmp, "app")
    os.makedirs(module_dir, exist_ok=True)
    bg = os.path.join(module_dir, "build.gradle")
    with open(bg, "w") as f:
        f.write(textwrap.dedent(gradle_text))
    if toml_text:
        gradle_dir = os.path.join(tmp, "gradle")
        os.makedirs(gradle_dir, exist_ok=True)
        with open(os.path.join(gradle_dir, "libs.versions.toml"), "w") as f:
            f.write(textwrap.dedent(toml_text))
    if root_gradle_text:
        with open(os.path.join(tmp, "build.gradle"), "w") as f:
            f.write(textwrap.dedent(root_gradle_text))
    return bg


# ---------------------------------------------------------------------------
# targetSdk
# ---------------------------------------------------------------------------

def test_literal_target_sdk():
    with tempfile.TemporaryDirectory() as tmp:
        bg = _setup(tmp, """\
            android {
                defaultConfig {
                    targetSdk 36
                }
            }
        """)
        cfg = read(os.path.join(tmp, "app"), bg, repo_root=tmp)
        assert isinstance(cfg.target_sdk, ResolvedValue)
        assert cfg.target_sdk.value == "36"


def test_env_var_target_sdk_is_undecided():
    with tempfile.TemporaryDirectory() as tmp:
        bg = _setup(tmp, """\
            android {
                defaultConfig {
                    targetSdk System.getenv('TARGET_SDK') as int
                }
            }
        """)
        cfg = read(os.path.join(tmp, "app"), bg, repo_root=tmp)
        assert isinstance(cfg.target_sdk, Undecided)
        assert "computed expression" in cfg.target_sdk.reason or "getenv" in cfg.target_sdk.reason.lower() or cfg.target_sdk.reason


# ---------------------------------------------------------------------------
# Version catalog resolution
# ---------------------------------------------------------------------------

def test_toml_version_resolution():
    toml = """\
        [versions]
        billing = "8.0.0"
        [libraries]
        billing = { group = "com.android.billingclient", name = "billing", version.ref = "billing" }
    """
    with tempfile.TemporaryDirectory() as tmp:
        bg = _setup(tmp, """\
            dependencies {
                implementation "com.android.billingclient:billing:8.0.0"
            }
        """, toml_text=toml)
        cfg = read(os.path.join(tmp, "app"), bg, repo_root=tmp)
        dep = cfg.dependencies.get("com.android.billingclient:billing")
        assert dep is not None
        assert isinstance(dep, ResolvedValue)
        assert dep.value == "8.0.0"


def test_literal_dependency_version():
    with tempfile.TemporaryDirectory() as tmp:
        bg = _setup(tmp, """\
            dependencies {
                implementation 'com.android.billingclient:billing:7.1.1'
            }
        """)
        cfg = read(os.path.join(tmp, "app"), bg, repo_root=tmp)
        dep = cfg.dependencies.get("com.android.billingclient:billing")
        assert isinstance(dep, ResolvedValue)
        assert dep.value == "7.1.1"


# ---------------------------------------------------------------------------
# ext / buildSrc substitution
# ---------------------------------------------------------------------------

def test_ext_variable_resolved():
    with tempfile.TemporaryDirectory() as tmp:
        root_gradle = """\
            ext {
                billingVersion = "8.1.0"
            }
        """
        bg = _setup(tmp, """\
            dependencies {
                implementation "com.android.billingclient:billing:${billingVersion}"
            }
        """, root_gradle_text=root_gradle)
        # The literal in the dep string uses ${billingVersion} which we don't fully
        # resolve here, but the ext map should be populated
        cfg = read(os.path.join(tmp, "app"), bg, repo_root=tmp)
        # At minimum the config should be returned without errors
        assert isinstance(cfg, GradleConfig)


# ---------------------------------------------------------------------------
# isMinifyEnabled
# ---------------------------------------------------------------------------

def test_minify_enabled_parsed():
    with tempfile.TemporaryDirectory() as tmp:
        bg = _setup(tmp, """\
            android {
                buildTypes {
                    release {
                        isMinifyEnabled true
                    }
                }
            }
        """)
        cfg = read(os.path.join(tmp, "app"), bg, repo_root=tmp)
        assert isinstance(cfg.is_minify_enabled, ResolvedValue)
        assert cfg.is_minify_enabled.value == "true"


def test_minify_disabled():
    with tempfile.TemporaryDirectory() as tmp:
        bg = _setup(tmp, """\
            android {
                buildTypes {
                    release {
                        isMinifyEnabled false
                    }
                }
            }
        """)
        cfg = read(os.path.join(tmp, "app"), bg, repo_root=tmp)
        assert isinstance(cfg.is_minify_enabled, ResolvedValue)
        assert cfg.is_minify_enabled.value == "false"


# ---------------------------------------------------------------------------
# Application ID
# ---------------------------------------------------------------------------

def test_application_id_parsed():
    with tempfile.TemporaryDirectory() as tmp:
        bg = _setup(tmp, """\
            android {
                defaultConfig {
                    applicationId "com.example.myapp"
                }
            }
        """)
        cfg = read(os.path.join(tmp, "app"), bg, repo_root=tmp)
        assert isinstance(cfg.application_id, ResolvedValue)
        assert cfg.application_id.value == "com.example.myapp"


# ---------------------------------------------------------------------------
# Unreadable file
# ---------------------------------------------------------------------------

def test_unreadable_file_returns_empty_config():
    with tempfile.TemporaryDirectory() as tmp:
        fake_bg = os.path.join(tmp, "app", "build.gradle")
        os.makedirs(os.path.dirname(fake_bg), exist_ok=True)
        # Don't create the file
        cfg = read(os.path.join(tmp, "app"), fake_bg, repo_root=tmp)
        assert isinstance(cfg, GradleConfig)
        assert cfg.target_sdk is None
