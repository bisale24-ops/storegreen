"""Every factual claim in rules-catalog.md and demo-fixtures.md, checked against the real thing.

    python3 prep/verify-spec.py

Exits non-zero if any claim no longer holds. The spec is what Bob builds from on Saturday; a wrong
sentence in it costs hours of Bobcoins building the wrong thing. Network checks are reported as
SKIP when the network is unavailable — never as a pass.
"""
import hashlib
import pathlib
import re
import struct
import sys
import urllib.error
import urllib.request
import zipfile

DESKTOP = pathlib.Path.home() / "Desktop" / "KHLab"
PREP = pathlib.Path(__file__).resolve().parent
BUNDLES = ["lockly-amazon-v3.aab", "numsly-amazon-v7.aab",
           "scanly-amazon-v5.aab", "smeta-amazon-v3.aab"]

passed, failed, skipped = [], [], []


def check(name, condition, detail=""):
    (passed if condition else failed).append((name, detail))
    print("%-5s %s%s" % ("pass" if condition else "FAIL", name,
                         ("  — " + detail) if detail and not condition else ""))


def skip(name, why):
    skipped.append((name, why))
    print("%-5s %s  — %s" % ("skip", name, why))


def load_aligns(raw):
    """PT_LOAD alignments, by the offsets the spec tells Bob to use."""
    if len(raw) < 64 or raw[:4] != b"\x7fELF" or raw[4] not in (1, 2) or raw[5] not in (1, 2):
        return []
    is64, endian = raw[4] == 2, ("<" if raw[5] == 1 else ">")
    try:
        if is64:
            e_phoff, = struct.unpack_from(endian + "Q", raw, 0x20)
            e_phentsize, e_phnum = struct.unpack_from(endian + "HH", raw, 0x36)
        else:
            e_phoff, = struct.unpack_from(endian + "I", raw, 0x1C)
            e_phentsize, e_phnum = struct.unpack_from(endian + "HH", raw, 0x2A)
        out = []
        for i in range(e_phnum):
            off = e_phoff + i * e_phentsize
            if struct.unpack_from(endian + "I", raw, off)[0] != 1:
                continue
            out.append(struct.unpack_from((endian + "Q") if is64 else (endian + "I"),
                                          raw, off + (0x30 if is64 else 0x1C))[0])
        return out
    except struct.error:        # truncated or lying header: unreadable, not "aligned"
        return []


# ---- the bundles ---------------------------------------------------------------------------

present = [b for b in BUNDLES if (DESKTOP / b).exists()]
check("all four bundles are where the spec says they are",
      len(present) == 4, "found %s" % ", ".join(present))

keys, unaligned, total_libs, billing_perm, billing_dex, markers_ok, query_all = {}, [], 0, [], [], [], []
MARKERS = ["com.amazon.device.iap.ResponseReceiver", "com.amazon.venezia",
           "com.amazon.sdktestclient", "com.amazon.inapp.purchasing.NOTIFY",
           "com.amazon.inapp.purchasing.Permission.NOTIFY"]

for name in present:
    with zipfile.ZipFile(DESKTOP / name) as z:
        names = set(z.namelist())
        if "base/assets/AppstoreAuthenticationKey.pem" in names:
            keys[name] = hashlib.sha256(z.read("base/assets/AppstoreAuthenticationKey.pem")).hexdigest()
        manifest = z.read("base/manifest/AndroidManifest.xml")
        # claim: protobuf, not the AXML magic 03 00 08 00
        check("%s: manifest is protobuf, not AXML" % name,
              manifest[:4] != b"\x03\x00\x08\x00" and manifest[:1] == b"\x0a",
              "first bytes %s" % manifest[:4].hex())
        text = manifest.decode("utf-8", "replace")
        if all(m in text for m in MARKERS):
            markers_ok.append(name)
        if "android.permission.QUERY_ALL_PACKAGES" in text:
            query_all.append(name)
        if "com.android.vending.BILLING" in text:
            billing_perm.append(name)
        for entry in sorted(n for n in names if n.startswith("base/lib/arm64-v8a/") and n.endswith(".so")):
            total_libs += 1
            aligns = load_aligns(z.read(entry))
            if not aligns or min(aligns) < 0x4000:
                unaligned.append((name, entry.split("/")[-1], [hex(a) for a in aligns]))
        for entry in (n for n in names if n.endswith(".dex")):
            if b"com/android/billingclient" in z.read(entry):
                billing_dex.append(name)
                break

check("every bundle carries the Amazon key", len(keys) == 4, "found in %d" % len(keys))
check("the four keys are four different keys",
      len(set(keys.values())) == 4, "distinct fingerprints: %d" % len(set(keys.values())))
check("every bundle declares the Amazon markers the spec relies on",
      len(markers_ok) == 4, "complete in %s" % ", ".join(markers_ok))
check("no bundle declares QUERY_ALL_PACKAGES", not query_all, "declared by %s" % query_all)
check("fifteen 64-bit native libraries in total", total_libs == 15, "counted %d" % total_libs)
check("exactly one library fails the 16 KB rule", len(unaligned) == 1, "failing: %s" % unaligned)
check("and it is libsqlcipher.so in Numsly at 0x1000",
      len(unaligned) == 1 and unaligned[0][0] == "numsly-amazon-v7.aab"
      and unaligned[0][1] == "libsqlcipher.so" and set(unaligned[0][2]) == {"0x1000"},
      "got %s" % unaligned)
check("Play billing permission appears in exactly one bundle",
      billing_perm == ["scanly-amazon-v5.aab"], "in %s" % billing_perm)
check("Play billing classes ship in exactly that same bundle",
      billing_dex == ["scanly-amazon-v5.aab"], "in %s" % billing_dex)

# ---- the ELF reader itself -----------------------------------------------------------------

check("the ELF reader rejects a file that is not an ELF", load_aligns(b"PK\x03\x04 not elf") == [])
check("the ELF reader survives a truncated header",
      load_aligns(b"\x7fELF\x02\x01" + b"\x00" * 10) == [])
check("the ELF reader survives a header that lies about its table",
      load_aligns(b"\x7fELF\x02\x01" + b"\x00" * 26 + struct.pack("<Q", 0xFFFFFF)
                  + b"\x00" * 6 + struct.pack("<HH", 56, 99) + b"\x00" * 64) == [])
check("an unreadable library is not silently counted as aligned",
      load_aligns(b"\x7fELF" + b"\x00" * 8) == [])

# ---- the rest of the prep tree ---------------------------------------------------------------

rejection = PREP / "fixtures" / "amazon-rejection-crewsheet.txt"
body = rejection.read_text(encoding="utf-8", errors="replace") if rejection.exists() else ""
check("the real rejection e-mail is there for Task 6", rejection.exists() and len(body) > 800,
      "%d bytes" % len(body))
check("and it is the CrewSheet content-policy one",
      "CrewSheet" in body and "content policy" in body.lower() and "11 September 2026" in body)

ide = pathlib.Path("/Applications/IBM Bob.app/Contents/Resources/app/bin/bobide")
check("the Bob IDE launcher is at the path the runbook now uses", ide.exists())
check("the runbook no longer tells us to type a bare `bobide`",
      "\nbobide " not in (PREP / "SETUP-STATE.md").read_text())

catalog = (PREP / "rules-catalog.md").read_text()
declared = set(re.findall(r"\b((?:AMZ-IAP|GP-[A-Z0-9]+|X-[A-Z]+)-\d\d)\b", catalog))
check("the catalogue declares the expected number of rules", len(declared) >= 20,
      "declared %d: %s" % (len(declared), sorted(declared)))
for doc in ("demo-fixtures.md", "PROMPTS.md"):
    used = set(re.findall(r"\b((?:AMZ-IAP|GP-[A-Z0-9]+|X-[A-Z]+)-\d\d)\b", (PREP / doc).read_text()))
    check("every rule id used in %s exists in the catalogue" % doc, used <= declared,
          "unknown: %s" % sorted(used - declared))

check("the catalogue states the deadline that makes the pitch urgent", "01.11.2026" in catalog)
check("the catalogue keeps the honesty rule about secrets",
      "correctly absent is not a defect" in catalog)
check("the catalogue keeps the presence-only caveat for bundle mode",
      "presence is **not** a pass" in catalog)

# ---- the safety net that will catch Bob's code ------------------------------------------------

import subprocess, tempfile
corpus = pathlib.Path(tempfile.mkdtemp()) / "corpus"
gen = subprocess.run([sys.executable, str(PREP / "crash-corpus.py"), str(corpus)],
                     capture_output=True, text=True)
cases = sorted(p.name for p in corpus.iterdir() if p.is_dir()) if corpus.is_dir() else []
check("the adversarial corpus builds", gen.returncode == 0 and len(cases) >= 20,
      "%d cases, %s" % (len(cases), gen.stderr.strip()[:120]))
check("it includes the traps that actually break scanners",
      {"symlink-loop", "manifest-not-utf8", "aab-not-a-zip", "aab-truncated-so",
       "unreadable-file", "sane-control"} <= set(cases), "missing from %s" % cases)

STUB_CRASHES = "import sys\nif '--quiet' not in sys.argv:\n    raise ValueError('boom')\n"
STUB_HANGS = "import sys, time\nif '--json' in sys.argv:\n    time.sleep(30)\n"
STUB_NOISY = "import sys\nsys.stderr.write('warning\\n')\n"
STUB_CLEAN = (
    "import argparse, json, sys\n"
    "p = argparse.ArgumentParser()\n"
    "p.add_argument('--repo'); p.add_argument('--json', action='store_true')\n"
    "p.add_argument('--quiet', action='store_true'); p.add_argument('--html')\n"
    "a = p.parse_args()\n"
    "sys.stdout.write(json.dumps({'root': a.repo}) if a.json else ('' if a.quiet else 'ok\\n'))\n")
stubs = {"crashes": STUB_CRASHES, "hangs": STUB_HANGS, "noisy": STUB_NOISY, "clean": STUB_CLEAN}
written = {}
for label, body in stubs.items():
    path = corpus.parent / ("stub_%s.py" % label)
    path.write_text(body)
    written[label] = path
for label, expected in (("crashes", 1), ("hangs", 1), ("noisy", 1), ("clean", 0)):
    done = subprocess.run([sys.executable, str(PREP / "crash-hunt.py"), "--corpus", str(corpus),
                           "--timeout", "3", "--limit", "4", "--", sys.executable, str(written[label])],
                          capture_output=True, text=True)
    check("the crash hunter returns %d for a tool that %s" % (expected, label),
          done.returncode == expected, "got %s: %s" % (done.returncode, done.stdout[-200:]))

expect_doc = (PREP / "corpus-expectations.md").read_text()
uncovered = sorted(c for c in cases if c not in expect_doc)
check("every corpus case has a written expected verdict", not uncovered, "missing %s" % uncovered)
check("the expectations keep the three words apart",
      all(w in expect_doc for w in ("**finding**", "**pass**", "**undecidable**")))
check("the false-positive cases are in the expectations",
      "wear-os-app" in expect_doc and "secret-key-gitignored" in expect_doc)

iface = (PREP / "interface.md").read_text()
check("the interface pins the exit codes", "| 1 | at least one **BLOCK** finding" in iface)
check("RISK and WARN deliberately do not fail a build",
      "RISK, WARN and undecidable do not change the exit code" in iface)
check("the JSON keeps undecided separate from findings",
      '"undecided"' in iface and '"passed"' in iface)
check("the prompts point Bob at the pinned interface", "@prep/interface.md" in
      (PREP / "PROMPTS.md").read_text())
check("the prompts point Bob at the expected verdicts", "@prep/corpus-expectations.md" in
      (PREP / "PROMPTS.md").read_text())

tier_one = {"AMZ-IAP-01", "AMZ-IAP-03", "AMZ-IAP-04", "AMZ-IAP-06",
            "GP-API-01", "GP-BILL-01", "GP-16KB-01", "X-FLAVOR-01"}
section10 = catalog.split("# 10. What actually ships")[-1].split("# 11.")[0]
named = set(re.findall(r"\b((?:AMZ-IAP|GP-[A-Z0-9]+|X-[A-Z]+)-\d\d)\b", section10))
check("the shipping set is the eight rules with real-world evidence",
      tier_one <= named, "missing %s" % sorted(tier_one - named))
check("the two rules that fired on our own apps are in it",
      "fired on Numsly" in catalog and "fired on Scanly" in catalog)
check("unbuilt rules are reported rather than silently omitted",
      "**not implemented**, by id" in catalog)
check("decidability is counted, not just claimed",
      "decided" in catalog and "undecidable" in catalog and "not applicable" in catalog
      and "21 rules" in catalog)
check("the empty directory is the case that catches a lying tool",
      "indistinguishable from one that works" in expect_doc)
check("the counters are pinned per case, not left to the implementation",
      "The four counters, per case" in expect_doc)
script_paths = [pathlib.Path(__file__).resolve().parents[1] / "submission" / "video-script.md",
                pathlib.Path.home() / "Desktop/KHLab/ibm-bob-hackathon/submission/video-script.md"]
script = next((p for p in script_paths if p.exists()), None)
if script is None:
    skip("the video's strongest scene carries the number", "video-script.md not found")
else:
    check("the video's strongest scene carries the number",
          "each refusal naming the line it gave up on" in script.read_text())

# ---- the Play deadlines, which are the whole B family ----------------------------------------

check("billing: v9 is dated 2027, not 2028",
      "31.08.2027" in catalog and "v9 becomes mandatory **31.08.2027**" in catalog)
# The first version of this check looked for one exact sentence and missed the same claim written
# another way, three lines further down. Bob's plan-mode review caught what the test did not.
stale = [line.strip() for line in catalog.splitlines()
         if re.search(r"\bv?9\b", line) and "2028" in line and "v10" not in line]
check("no line anywhere still dates v9 to 2028", not stale, "still says: %s" % stale[:2])
for feature in ("android.hardware.type.watch", "android.software.leanback",
                "android.hardware.type.automotive"):
    check("the form-factor table detects %s" % feature, feature in catalog)
check("the target-API rule no longer hardcodes one number",
      "targetSdk` < 36 (phones)" not in catalog)
check("an undetectable form factor is documented as an assumption, not a silent BLOCK",
      "assume phone and say so in the evidence" in catalog)

OFFICIAL = {
    "https://developer.android.com/google/play/billing/deprecation-faq":
        ["version 8 or later", "Aug 31, 2026"],
    "https://support.google.com/googleplay/android-developer/answer/11926878":
        ["API level 36", "August 31, 2026", "November 1, 2026"],
}
for url, needles in OFFICIAL.items():
    try:
        request = urllib.request.Request(url, headers={"user-agent": "storegreen-spec-check"})
        page = urllib.request.urlopen(request, timeout=25).read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as error:
        skip("official page still says what the catalogue claims: %s" % url.split("/")[-1],
             "unreachable: %s" % error)
        continue
    missing = [n for n in needles if n not in page]
    check("official page still says what the catalogue claims: %s" % url.split("/")[-1],
          not missing, "missing %s" % missing)

# ---- the three repositories Sunday depends on --------------------------------------------

EXPECT = {
    "schorschii/FsClock-Android": ("master", "app/build.gradle",
                                   ["targetSdkVersion 36", "billing:8.0.0", "amazon-appstore-sdk:3.0.7"]),
    "jberkel/sms-backup-plus": ("master", "app/build.gradle",
                                ["targetSdk 35", "billing:7.1.1"]),
    "UweTrottmann/SeriesGuide": ("main", "app/build.gradle.kts",
                                 ["amazon", "AppstoreAuthenticationKey.pem"]),
}
for repo, (branch, path, needles) in EXPECT.items():
    url = "https://raw.githubusercontent.com/%s/%s/%s" % (repo, branch, path)
    try:
        text = urllib.request.urlopen(url, timeout=20).read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as error:
        skip("%s still matches the shortlist" % repo, "unreachable: %s" % error)
        continue
    missing = [n for n in needles if n not in text]
    check("%s still matches the shortlist" % repo, not missing, "missing %s" % missing)

print()
print("%d passed, %d failed, %d skipped" % (len(passed), len(failed), len(skipped)))
sys.exit(1 if failed else 0)
