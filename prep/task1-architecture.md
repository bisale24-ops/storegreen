I'll read all three specification files before proposing anything.

Now I have a complete picture. Here is the full architecture proposal.

---

# StoreGreen — Architecture Proposal

## 1. Module layout

```
storegreen/
├── storegreen/                  # importable package
│   ├── __init__.py
│   ├── cli.py                   # argparse entry point; owns exit codes
│   ├── runner.py                # orchestrates scan, merges source+bundle results
│   │
│   ├── source/
│   │   ├── manifest_merger.py   # main → flavor → build-type merge (no AARs)
│   │   ├── gradle_reader.py     # libs.versions.toml → build.gradle → ext/buildSrc
│   │   └── project_layout.py   # discovers modules, flavors, build types
│   │
│   ├── bundle/
│   │   ├── aab_reader.py        # ZipFile wrapper; entry-path helpers
│   │   ├── manifest_bytes.py    # UTF-8 string search in protobuf manifest bytes
│   │   └── elf_reader.py        # PT_LOAD alignment; all guard branches
│   │
│   ├── rules/
│   │   ├── base.py              # Rule ABC + Finding / Undecided / Passed dataclasses
│   │   ├── amz_iap.py           # AMZ-IAP-01 … 08
│   │   ├── gp_api.py            # GP-API-01/02
│   │   ├── gp_billing.py        # GP-BILL-01/02
│   │   ├── gp_16kb.py           # GP-16KB-01
│   │   ├── gp_policy.py         # GP-PERM-01/02, GP-PRIV-01, GP-DS-01, GP-EXP-01
│   │   └── cross_store.py       # X-VER-01, X-SIGN-01, X-FLAVOR-01
│   │
│   ├── report/
│   │   ├── schema.py            # dataclasses → typed JSON dict (the canonical model)
│   │   ├── json_report.py       # serialize schema → JSON string
│   │   └── html_report.py       # schema → single self-contained HTML file
│   │
│   └── fixer.py                 # --fix: deterministic repairs + re-scan
│
├── fixtures/
│   ├── tipjar-amazon/           # Fixture 1 (Task 4)
│   └── notes-play/              # Fixture 2 (Task 4)
│
├── tests/
│   ├── corpus-expectations.md   # pinned decided/undecidable/passed counts per corpus case
│   └── test_*.py
│
└── prep/                        # spec docs (read-only)
```

**Dependency direction is strictly top-down.** `rules/` imports from `source/` and `bundle/`; `report/` imports from `rules/base.py` only; `cli.py` imports from `runner.py` only. Nothing imports upward.

---

## 2. The shape of a rule

Every rule is a class in the `rules/` package that inherits from `Rule`:

```python
# rules/base.py

@dataclass
class Evidence:
    file: str           # repo-relative or AAB-entry path
    line: int | None    # None only for binary entries (ELF, PEM)
    found: str          # verbatim excerpt or description of what was found
    expected: str       # what the store requires

@dataclass
class Finding:
    rule: str           # e.g. "AMZ-IAP-03"
    family: str         # e.g. "amazon-iap"
    severity: str       # "BLOCK" | "RISK" | "WARN"
    title: str
    evidence: Evidence
    fix: FixHint | None
    decided_from: str   # "source" | "bundle" | "both"

@dataclass
class Undecided:
    rule: str
    reason: str
    evidence: Evidence  # file + line where the rule gave up; always present

@dataclass
class Passed:
    rule: str
    note: str
    decided_from: str

@dataclass
class NotApplicable:
    rule: str
    reason: str         # "no amazon flavor" | "no native libraries" | …

class Rule(ABC):
    id: str             # e.g. "AMZ-IAP-03"
    family: str
    severity: str
    tier: int           # 1 = must ship; 2 = stretch

    @abstractmethod
    def check_source(self, ctx: SourceContext) -> Finding | Undecided | Passed | NotApplicable:
        ...

    def check_bundle(self, ctx: BundleContext) -> Finding | Undecided | Passed | NotApplicable:
        # default: Undecided — tier-2 rules only override what they implement
        return Undecided(rule=self.id, reason="not implemented", evidence=...)
```

Key invariants enforced at this layer:
- `Undecided` always carries an `Evidence` with the file and line where the rule stopped. No `Undecided` without it.
- `Finding` always carries `Evidence`. A `Finding` constructed without evidence raises at `__post_init__`.
- `Passed` carries `decided_from` so the HTML can label it.
- `NotApplicable` is not the same as `Undecided`. It is emitted when the rule's precondition is absent from the project (no Amazon flavor, no native `.so`, no billing dependency). It does not count against the decidability score.

---

## 3. How a rule reports evidence

The spec rule is absolute: **a finding without evidence is a bug, not a finding.** Evidence is always one of:

| Situation | `file` | `line` | `found` | `expected` |
|---|---|---|---|---|
| XML element in a source manifest | repo-relative path | element's start line | verbatim opening tag | what the store requires |
| Gradle value | repo-relative path | the literal line number | the literal text of the line | what the store requires |
| Binary AAB entry (presence/absence) | AAB-entry path e.g. `base/assets/AppstoreAuthenticationKey.pem` | `null` | SHA-256 or `"absent"` | `"must be present"` |
| ELF program header | AAB-entry path e.g. `base/lib/arm64-v8a/libsqlcipher.so` | `null` | `p_align=0x1000 on PT_LOAD[0]` | `p_align ≥ 0x4000` |
| UTF-8 string found in protobuf manifest bytes | `base/manifest/AndroidManifest.xml` | `null` | verbatim matched string | what was expected |
| Rule gave up (Undecided) | the file it last read | the line it last had | the expression it could not resolve | `"a literal value"` |

The `line: null` cases are binary formats only. For every text file a non-null line number is required.

---

## 4. JSON report schema

This is the canonical contract. The `schema.py` module owns the typed dataclasses; `json_report.py` serializes them. Both are generated from the same dataclasses, so they cannot diverge.

```json
{
  "tool": "storegreen",
  "version": "0.1.0",
  "scanned": {
    "repo": "/abs/path",         // null if --aab only
    "aab":  "/abs/path.aab",     // null if source only
    "modules": ["app"],
    "form_factor": "phone"       // "phone" | "wear" | "tv" | "automotive" | "xr"
  },
  "summary": {
    "block": 1,
    "risk": 2,
    "warn": 0,
    "undecidable": 3,
    "passed": 15,
    "not_applicable": 2,
    "not_implemented": 13,
    "seconds": 0.42
  },
  "findings": [
    {
      "rule": "AMZ-IAP-03",
      "family": "amazon-iap",
      "severity": "BLOCK",
      "title": "the Amazon purchase receiver is not declared",
      "evidence": {
        "file": "app/src/amazon/AndroidManifest.xml",
        "line": 14,
        "found": "<service android:name=\"…PurchasingService\"/>",
        "expected": "a ResponseReceiver with the NOTIFY intent-filter"
      },
      "fix": {
        "automatic": true,
        "description": "add the receiver block to the amazon manifest"
      },
      "decided_from": "source"
    }
  ],
  "undecided": [
    {
      "rule": "GP-API-01",
      "reason": "targetSdk comes from System.getenv('SDK')",
      "evidence": {
        "file": "app/build.gradle",
        "line": 2,
        "found": "targetSdk System.getenv('SDK')",
        "expected": "a literal integer"
      }
    }
  ],
  "passed": [
    {
      "rule": "AMZ-IAP-01",
      "note": "key present; SHA-256 = a3f1…",
      "decided_from": "bundle"
    }
  ],
  "not_applicable": [
    {
      "rule": "AMZ-IAP-01",
      "reason": "no amazon flavor found"
    }
  ],
  "not_implemented": ["GP-PERM-01", "GP-PERM-02", "GP-PRIV-01", "…"]
}
```

**Differences from the spec's example that are intentional:**
- `not_applicable` and `not_implemented` are top-level arrays, not folded into `undecided`. The spec is clear that "a judge scanning the output must see instantly that the tool distinguishes wrong from unknown" — the same logic separates "unknown" from "irrelevant" and "not built yet".
- `summary.not_applicable` and `summary.not_implemented` are counted explicitly, so the decidability line the tool prints (`8 implemented · 6 decided · 2 undecidable · 13 not implemented`) maps directly to the JSON.
- `evidence` is present on `undecided` entries — the spec says the line it gave up on must always be there.

---

## 5. How the HTML report is produced

`html_report.py` takes the same typed dataclasses that `json_report.py` serializes — it does not re-parse JSON. It produces a single `str` of self-contained HTML with all CSS inlined, written to the path given to `--html`.

**Layout (pinned in the spec):**

```
┌─────────────────────────────────────────────────┐
│  StoreGreen  ·  app  ·  phone  ·  0.42 s        │
│  ████ 1 BLOCK   ░░░░ 2 RISK   ░ 0 WARN          │
│  Scanned: source+bundle · 6 decided · 2 unknown │
└─────────────────────────────────────────────────┘

  BLOCK  AMZ-IAP-03
  "the Amazon purchase receiver is not declared"
  app/src/amazon/AndroidManifest.xml:14
    found:    <service android:name="…PurchasingService"/>
    expected: a ResponseReceiver with the NOTIFY intent-filter
  ✎ Fix available: add the receiver block to the amazon manifest

  ─── UNDECIDED (2) ───────────────────────────────
  GP-API-01 · targetSdk comes from System.getenv('SDK')
    gave up at app/build.gradle:2

  ─── PASSED (collapsed) ──────────────────────────
  <details><summary>15 rules passed</summary>…</details>

  ─── NOT IMPLEMENTED (13) ────────────────────────
  GP-PERM-01, GP-PERM-02, GP-PRIV-01 …
```

The template is a Python f-string or minimal hand-written HTML generator in `html_report.py` — no Jinja2, no external dependency, because the spec requires the tool to be installable in one step. CSS is a `<style>` block in the `<head>`. No `<script>`. No external URLs.

---

## 6. Which rules need what

### Source-only (no AAB needed)

| Rule | What it reads |
|---|---|
| AMZ-IAP-03 | merged manifest (source) |
| AMZ-IAP-04 | merged manifest (source) |
| AMZ-IAP-05 | Kotlin/Java source — `PurchasingService.purchase` call sites |
| AMZ-IAP-06 | `build.gradle` `isMinifyEnabled`, proguard files |
| AMZ-IAP-07 | flavor `res/values*/strings.xml` vs `main` strings |
| AMZ-IAP-08 | amazon flavor resource strings |
| GP-API-01/02 | `targetSdk` from Gradle + form factor from merged manifest |
| GP-BILL-01/02 | billing dependency version from Gradle |
| GP-PERM-01/02 | merged manifest |
| GP-PRIV-01 | merged manifest + repo store-metadata files |
| GP-DS-01 | dependency list (narrowed: list data-collecting SDKs) |
| GP-EXP-01 | merged manifest |
| X-VER-01 | `versionCode` from Gradle + `--last-version` flag |
| X-FLAVOR-01 | dependency scoping in `build.gradle` (partial signal) |

### Needs the AAB

| Rule | What it reads | Why source is insufficient |
|---|---|---|
| AMZ-IAP-01 | `base/assets/AppstoreAuthenticationKey.pem` presence + SHA-256 | Key is a secret; source absence is RISK not BLOCK |
| AMZ-IAP-02 | PEM SHA-256 across multiple scanned bundles | Needs the actual key bytes to fingerprint |
| AMZ-IAP-03 | protobuf manifest byte search | Presence-only confidence; source mode gets full attribute fidelity |
| AMZ-IAP-04 | protobuf manifest byte search | Same |
| GP-16KB-01 | ELF PT_LOAD headers in `base/lib/arm64-v8a/*.so` | Native libraries aren't in source |
| X-SIGN-01 | **Undecided in both modes** (jar cert parsing dropped per spec §1) | — |
| X-FLAVOR-01 | `classes.dex` for `com/android/billingclient` + manifest for `com.android.vending.BILLING` | Source Gradle read is a partial signal; dex is authoritative |

### Source + Bundle (both used, result merged by `runner.py`)

AMZ-IAP-01, AMZ-IAP-03, AMZ-IAP-04, X-FLAVOR-01: source gives structural evidence (attributes, scoping), bundle gives binary confirmation. When both are run, `decided_from: "both"` and the report cites both evidence objects.

---

## 7. The decidability summary line

```
21 rules  ·  8 implemented  ·  6 decided  ·  2 undecidable  ·  2 not applicable  ·  13 not implemented
```

Printed to stdout (or encoded in JSON) at the end of every run. The four numbers are part of the JSON `summary` object and are pinned in `tests/corpus-expectations.md` for every corpus case. Running twice on the same tree produces identical numbers.

---

## 8. Build order

1. **`rules/base.py`** — `Evidence`, `Finding`, `Undecided`, `Passed`, `NotApplicable`, `FixHint`, `Rule` ABC, `SourceContext`, `BundleContext`. No external dependencies. No rule logic. Tests: dataclass construction, the `__post_init__` guard on `Finding` without evidence.

2. **`source/project_layout.py`** — discovers `src/main`, flavor directories, build types from `build.gradle`; returns a `ProjectLayout` with module paths and flavor names. Tests against `fixtures/`.

3. **`source/manifest_merger.py`** — XML merge in order main → flavor → build-type; no AARs; override by `android:name`. Returns a `MergedManifest` with every element annotated with its contributing file and line. Tests: element from main, element overridden by flavor, library-contributed element absent.

4. **`source/gradle_reader.py`** — `libs.versions.toml` → literal in `build.gradle` → `ext`/`buildSrc` constant; stops and returns `Undecided` with the line on any computed expression. Tests: TOML resolution, `${}` substitution, unresolvable env var.

5. **`bundle/aab_reader.py` + `bundle/manifest_bytes.py`** — `ZipFile` wrapper; UTF-8 string search in protobuf bytes with byte-offset evidence. Tests: present string, absent string.

6. **`bundle/elf_reader.py`** — ELF PT_LOAD alignment reader; all guard branches produce `cannot be determined — unreadable ELF`, never a pass, never an exception. Tests: 64-bit aligned, 64-bit misaligned (`libsqlcipher.so` baseline), truncated file, wrong magic, 32-bit skipped.

7. **Tier-1 rules** — implement each rule class in `rules/`; each file covers one family. Rule order: `amz_iap.py` (AMZ-IAP-01/03/04/06), `gp_api.py` (GP-API-01), `gp_billing.py` (GP-BILL-01), `gp_16kb.py` (GP-16KB-01), `cross_store.py` (X-FLAVOR-01). Tests for each against fixtures and real-bundle expectations from `corpus-expectations.md`.

8. **`runner.py`** — takes `ProjectLayout` + optional AAB path, runs all instantiated rules, merges source+bundle findings, produces the typed report object. Tests: source-only run, bundle-only run, combined run.

9. **`report/schema.py` + `report/json_report.py`** — serialize the report object to the JSON schema. Tests: round-trip, all four lists present even when empty, `undecided[].evidence` always has a line.

10. **`report/html_report.py`** — report object → self-contained HTML string. Tests: no external URLs, `<details>` for passed, all severity classes present.

11. **`cli.py`** — argparse wiring, exit codes, `--fix` call to `fixer.py`, `--json`/`--html`/`--quiet` modes, nothing on stdout in `--json` mode except the JSON, nothing on stderr on a clean run.

12. **`fixtures/` generation (Task 4)** — `tipjar-amazon` and `notes-play` created by Bob; each seeded defect verified to fire the expected rule.

13. **`tests/corpus-expectations.md` + acceptance tests** — pin decided/undecidable/passed counts for every corpus case (four real bundles + two fixtures + three public repos). CI fails if the numbers shift.

14. **Tier-2 rules** — AMZ-IAP-02/05/07/08, GP-API-02, GP-BILL-02, GP-PERM-01/02, GP-PRIV-01, GP-DS-01, GP-EXP-01, X-VER-01, X-SIGN-01 — only when tier 1 is finished and passes the crash hunt.

---

## 9. Ambiguities and things that look wrong

**Genuine ambiguities (spec does not resolve them):**

1. **`--repo` + `--aab` together: which module does the AAB belong to?** A multi-module project may have `app/` and `wear/` modules. The runner needs to know which `build.gradle` to read alongside a given AAB. The spec says "scan both and merge findings" but does not say how the AAB is associated with a module. *Proposed resolution:* the runner infers the module from the AAB's `base/manifest/AndroidManifest.xml` application id and matches it to the module with the same `applicationId` in the source tree; report as unmatched if ambiguous.

2. **`not_applicable` versus `undecidable` for X-VER-01 without `--last-version`.** The spec says "skipped with that reason." Is a skipped rule `not_applicable` or `undecided`? The two have different counts in the summary line and different semantics. *Proposed resolution:* `not_applicable` — the rule's precondition (a known upload baseline) is absent, not the rule's evidence. The report note should say "pass `--last-version N` to enable".

3. **The `--fix` flag re-scans and "reports both" — but reports them how?** The JSON schema has no before/after field. *Proposed resolution:* the JSON gets a top-level `"fix_applied": true` and a second `"findings_before_fix"` list alongside the normal `"findings"` (which is the after state). The HTML renders a two-column or two-section diff.

4. **`--explain-rejection F` is in the CLI but has no spec for what `F` is or what the output looks like.** It reads a "store rejection e-mail" and maps it to rule IDs — but the mapping table, the input format (plain text? `.eml`?), and the output format are not defined anywhere.

5. **`form_factor` in `scanned` is a single value, but the spec (§8) says a module can be more than one form factor.** If an app targets both phone and Wear OS, which `form_factor` goes in `scanned`? *Proposed resolution:* `form_factor` becomes an array in `scanned`; the GP-API-01 finding cites the specific form factor that produced the verdict.

**Things that look wrong:**

6. **GP-BILL-02's deadline in the rules table contradicts §8's corrected re-read.** The rules table (section B) says "v9 from 31.08.2028, extension to 01.11.2028" but §8 says "v9 from 31.08.2027". The correction note in §8 explicitly says "re-fetched 25.09.2026" and "8 expires 31.08.2027 so 9+ from then" — so §8 is authoritative. The rules table body text is wrong and must be updated before GP-BILL-02 is implemented.

7. **AMZ-IAP-01 in source mode uses `src/<amazonFlavor>/assets/` as the detection path, but the spec (§7) says the key is a secret and should not be committed.** In source mode, absence of the key should always be RISK ("cannot be determined — the key is a secret"), never a BLOCK, and presence is just noted. The rules table implies the file absence in source is the detection — which would make every well-maintained repository a false positive. §7 resolves this correctly; the rules table is misleading on this point.

8. **`X-SIGN-01` is listed in the Decisions section as "AAB mode: AMZ-IAP-01 in `base/assets/`, GP-16KB-01 ELF alignment, X-SIGN-01"** (implying it is an AAB-mode rule), but §1 explicitly drops it from AAB mode too ("parsing a DER certificate by hand is a day of work… Report it as `cannot be determined`"). These two statements contradict each other. §1 is the later, more specific decision and should win.

9. **`GP-PRIV-01` depends on "no privacy policy URL in repo store metadata / in-app."** There is no spec for what "repo store metadata" means — the directory, the file name, and the format are undefined. FastLane `metadata/`? A `store_listing/` directory? A field in `build.gradle`? Without this, GP-PRIV-01 cannot be implemented in source mode. It should either be tier-2 with a documented assumption, or the spec should name the expected path.

10. **The `passed` list in the spec's JSON example has no `evidence` field**, but the spec text says "a finding without evidence is a bug, not a finding." This creates an inconsistency: `passed` entries have a `note` but no structured evidence. For auditing purposes (especially AMZ-IAP-01 where the PEM SHA-256 is the evidence of a pass), `passed` should carry the same `evidence` structure as `finding`. *Proposed resolution:* add an optional `evidence` field to `Passed`; it is required for any rule that performed a binary check.