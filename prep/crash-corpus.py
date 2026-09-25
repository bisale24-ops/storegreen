"""Build the inputs that break scanners. Written before the event; run against whatever Bob builds.

    python3 prep/crash-corpus.py /tmp/corpus

Every directory it creates is a repository StoreGreen must survive — not pass, survive. The
difference matters: a finding is fine, "cannot be determined" is fine, a traceback is not, and
neither is a clean exit that quietly examined nothing.
"""
import pathlib
import shutil
import struct
import sys
import zipfile


def write(root, path, data):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        target.write_bytes(data)
    else:
        target.write_text(data, encoding="utf-8")
    return target


MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.example.app">
  <application android:label="x"><activity android:name=".Main"/></application>
</manifest>
"""
GRADLE = """android { compileSdk 36
  defaultConfig { applicationId "com.example.app"; targetSdk 36 } }
dependencies { implementation 'com.android.billingclient:billing:8.0.0' }
"""


def build(base):
    base = pathlib.Path(base)
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    cases = {}

    def case(name):
        d = base / name
        d.mkdir(parents=True, exist_ok=True)
        cases[name] = d
        return d

    # --- nothing to work with -----------------------------------------------------------
    case("empty")
    d = case("no-android"); write(d, "README.md", "# just a python project\n"); write(d, "main.py", "print(1)\n")
    d = case("only-a-manifest"); write(d, "AndroidManifest.xml", MANIFEST)
    d = case("gradle-without-manifest"); write(d, "app/build.gradle", GRADLE)

    # --- malformed on purpose -----------------------------------------------------------
    d = case("manifest-not-xml"); write(d, "app/src/main/AndroidManifest.xml", "<manifest><application>\n")
    write(d, "app/build.gradle", GRADLE)
    d = case("manifest-empty"); write(d, "app/src/main/AndroidManifest.xml", "")
    d = case("manifest-not-utf8"); write(d, "app/src/main/AndroidManifest.xml",
                                          b"<manifest package=\"\xff\xfe\xfa\"/>")
    d = case("manifest-xml-bomb")            # billion laughs, in case anyone reaches for an entity parser
    write(d, "app/src/main/AndroidManifest.xml",
          '<?xml version="1.0"?><!DOCTYPE m [<!ENTITY a "aa"><!ENTITY b "&a;&a;&a;&a;&a;&a;">'
          '<!ENTITY c "&b;&b;&b;&b;&b;&b;">]><manifest>&c;</manifest>')
    d = case("gradle-computed-version")
    write(d, "app/build.gradle", "def v = System.getenv('SDK') ?: 36\nandroid { defaultConfig { targetSdk v.toInteger() } }\n")
    d = case("toml-broken"); write(d, "gradle/libs.versions.toml", "[versions\nbilling = \n")
    write(d, "app/build.gradle", "dependencies { implementation libs.billing }\n")
    d = case("huge-single-line"); write(d, "app/src/main/AndroidManifest.xml",
                                        "<manifest>" + "<!--" + "x" * 3_000_000 + "-->" + "</manifest>")

    # --- file system traps ---------------------------------------------------------------
    d = case("symlink-loop"); write(d, "app/build.gradle", GRADLE); (d / "loop").symlink_to(d, target_is_directory=True)
    d = case("dangling-symlink"); (d / "app").mkdir(); (d / "app" / "build.gradle").symlink_to(d / "gone")
    d = case("manifest-is-a-directory"); (d / "app/src/main/AndroidManifest.xml").mkdir(parents=True)
    d = case("unreadable-file"); p = write(d, "app/build.gradle", GRADLE); p.chmod(0o000)
    d = case("deep-tree"); write(d, "/".join(["a"] * 40) + "/build.gradle", GRADLE)
    d = case("weird-names"); write(d, "app/src/main/AndroidManifest.xml", MANIFEST)
    write(d, "app/src/ma in/пробел и юникод/build.gradle", GRADLE)

    # --- bundles that are not bundles ------------------------------------------------------
    d = case("aab-not-a-zip"); write(d, "app.aab", b"this is not a zip at all")
    d = case("aab-empty-zip")
    with zipfile.ZipFile(d / "app.aab", "w"):
        pass
    d = case("aab-truncated-so")
    with zipfile.ZipFile(d / "app.aab", "w") as z:
        z.writestr("base/lib/arm64-v8a/libshort.so", b"\x7fELF\x02\x01" + b"\x00" * 10)
        z.writestr("base/manifest/AndroidManifest.xml", b"\x0a\x00")
    d = case("aab-lying-elf-header")
    with zipfile.ZipFile(d / "app.aab", "w") as z:
        header = bytearray(b"\x7fELF\x02\x01" + b"\x00" * 58)
        header[0x20:0x28] = struct.pack("<Q", 0xFFFFFFF)   # program headers past the end
        header[0x36:0x3A] = struct.pack("<HH", 56, 99)
        z.writestr("base/lib/arm64-v8a/liblies.so", bytes(header))
    d = case("aab-so-is-empty")
    with zipfile.ZipFile(d / "app.aab", "w") as z:
        z.writestr("base/lib/arm64-v8a/libempty.so", b"")

    # --- Gradle as it actually appears in the wild --------------------------------------
    d = case("kotlin-dsl")
    write(d, "app/build.gradle.kts",
          'plugins { id("com.android.application") }\n'
          'android { namespace = "com.example"\n'
          '  defaultConfig { targetSdk = 35 }\n'
          '  buildTypes { release { isMinifyEnabled = true } } }\n'
          'dependencies { implementation("com.android.billingclient:billing:7.1.1") }\n')
    write(d, "app/src/main/AndroidManifest.xml", MANIFEST)

    d = case("version-catalog")
    write(d, "gradle/libs.versions.toml",
          '[versions]\nbilling = "7.1.1"\ntargetSdk = "35"\n'
          '[libraries]\nbilling = { module = "com.android.billingclient:billing", version.ref = "billing" }\n')
    write(d, "app/build.gradle.kts",
          'android { defaultConfig { targetSdk = libs.versions.targetSdk.get().toInt() } }\n'
          'dependencies { implementation(libs.billing) }\n')
    write(d, "app/src/main/AndroidManifest.xml", MANIFEST)

    d = case("buildsrc-constants")
    write(d, "buildSrc/src/main/kotlin/Versions.kt",
          'object Versions {\n  const val targetSdk = 35\n  const val billing = "7.1.1"\n}\n')
    write(d, "app/build.gradle.kts",
          'android { defaultConfig { targetSdk = Versions.targetSdk } }\n'
          'dependencies { implementation("com.android.billingclient:billing:${Versions.billing}") }\n')

    d = case("gradle-properties")
    write(d, "gradle.properties", "TARGET_SDK=35\nBILLING=7.1.1\n")
    write(d, "app/build.gradle",
          "android { defaultConfig { targetSdk TARGET_SDK.toInteger() } }\n"
          "dependencies { implementation \"com.android.billingclient:billing:$BILLING\" }\n")

    d = case("multi-module-one-app")
    write(d, "settings.gradle", "include ':app', ':core', ':design'\n")
    write(d, "app/build.gradle", "apply plugin: 'com.android.application'\n" + GRADLE)
    write(d, "core/build.gradle", "apply plugin: 'com.android.library'\nandroid { defaultConfig { } }\n")
    write(d, "design/build.gradle", "apply plugin: 'com.android.library'\n")
    write(d, "app/src/main/AndroidManifest.xml", MANIFEST)
    write(d, "core/src/main/AndroidManifest.xml", MANIFEST.replace("com.example.app", "com.example.core"))

    d = case("two-app-modules")
    write(d, "settings.gradle", "include ':free', ':paid'\n")
    for module, target in (("free", "35"), ("paid", "36")):
        write(d, "%s/build.gradle" % module,
              "apply plugin: 'com.android.application'\nandroid { defaultConfig { targetSdk %s } }\n" % target)
        write(d, "%s/src/main/AndroidManifest.xml" % module, MANIFEST)

    d = case("composite-build")
    write(d, "settings.gradle", "includeBuild '../shared'\ninclude ':app'\n")
    write(d, "app/build.gradle", GRADLE)

    d = case("flavors-and-overrides")
    write(d, "app/build.gradle",
          "android { flavorDimensions 'store'\n"
          "  productFlavors { amazon { dimension 'store' }\n"
          "                   play { dimension 'store' } }\n"
          "  defaultConfig { targetSdk 36 } }\n"
          "dependencies { amazonImplementation 'com.amazon.device:amazon-appstore-sdk:3.0.7'\n"
          "               playImplementation 'com.android.billingclient:billing:8.0.0' }\n")
    write(d, "app/src/main/AndroidManifest.xml", MANIFEST)
    write(d, "app/src/amazon/AndroidManifest.xml",
          MANIFEST.replace('android:label="x"', 'android:label="amazon"'))
    write(d, "app/src/amazon/res/values/strings.xml",
          '<resources><string name="buy">Get the full version on our website</string></resources>')

    # the amazon key is a secret: correctly absent, and gitignored on purpose (the SeriesGuide case)
    d = case("secret-key-gitignored")
    write(d, ".gitignore", "*.keystore\nkeystore.properties\napp/src/amazon/assets/*.pem\n")
    write(d, "app/build.gradle",
          "// Note: requires to add AppstoreAuthenticationKey.pem into amazon/assets.\n" + GRADLE)
    write(d, "app/src/main/AndroidManifest.xml", MANIFEST)

    # form factors: the rule must not demand API 36 of a watch or a television
    d = case("wear-os-app")
    write(d, "app/src/main/AndroidManifest.xml",
          MANIFEST.replace("<application",
                           '<uses-feature android:name="android.hardware.type.watch"/>\n  <application'))
    write(d, "app/build.gradle", "android { defaultConfig { targetSdk 35 } }\n")

    d = case("android-tv-app")
    write(d, "app/src/main/AndroidManifest.xml",
          MANIFEST.replace("<application",
                           '<uses-feature android:name="android.software.leanback" android:required="true"/>\n  <application'))
    write(d, "app/build.gradle", "android { defaultConfig { targetSdk 34 } }\n")

    d = case("automotive-app")
    write(d, "app/src/main/AndroidManifest.xml",
          MANIFEST.replace("<application",
                           '<uses-feature android:name="android.hardware.type.automotive"/>\n  <application'))
    write(d, "app/build.gradle", "android { defaultConfig { targetSdk 35 } }\n")

    # --- a sane control, so a harness that fails everything is visible ----------------------
    d = case("sane-control")
    write(d, "app/src/main/AndroidManifest.xml", MANIFEST)
    write(d, "app/build.gradle", GRADLE)
    write(d, "README.md", "# a perfectly ordinary android project\n")

    return cases


if __name__ == "__main__":
    where = sys.argv[1] if len(sys.argv) > 1 else "/tmp/storegreen-corpus"
    made = build(where)
    for name in sorted(made):
        print(name)
    print("\n%d cases in %s" % (len(made), where))
