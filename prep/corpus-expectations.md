# What the right answer is for each corpus case

`crash-hunt.py` proves the tool does not fall over. It says nothing about whether the tool is
**right**. These are the verdicts Task 3's tests must encode, written before the event so they
cannot be bent afterwards to match whatever Bob happened to build.

Three words are used precisely, and the distinction is the product:

- **finding** — the store will reject or penalise this, here is the evidence;
- **pass** — checked, and it is sound;
- **undecidable** — could not be determined from what was available, with the reason. Never a pass.

## Gradle, read without running Gradle

| Case | Right answer |
|---|---|
| `kotlin-dsl` | findings: GP-API-01 (`targetSdk = 35` < 36 for a phone), GP-BILL-01 (billing 7.1.1 < 8). Kotlin DSL must not be a reason to give up |
| `version-catalog` | same two findings, with evidence pointing at `gradle/libs.versions.toml`, not at the build file that merely references it |
| `buildsrc-constants` | same two findings; the constants are plain literals in `buildSrc` and are resolvable by substitution |
| `gradle-properties` | same two findings; values come from `gradle.properties` |
| `gradle-computed-version` | **undecidable** for GP-API-01 — the value comes from `System.getenv`. The finding must quote the line it gave up on |
| `toml-broken` | **undecidable**, reason "the version catalogue does not parse", and the rest of the scan still completes |
| `composite-build` | the included build is outside the scan root: report what is in range, and say that `includeBuild '../shared'` was not followed |

## Which module is the app

| Case | Right answer |
|---|---|
| `multi-module-one-app` | exactly one module is scanned as an application — the one applying `com.android.application`. The two libraries are listed as skipped, not reported as clean apps |
| `two-app-modules` | both are scanned and reported separately; `free` has GP-API-01, `paid` does not. A single merged verdict for the repository would be wrong |
| `gradle-without-manifest` | undecidable for every manifest rule, with that reason; Gradle rules still run |
| `only-a-manifest` | the reverse: manifest rules run, Gradle rules undecidable |

## Form factor decides the target API level

| Case | targetSdk | Right answer |
|---|---|---|
| `wear-os-app` | 35 | **pass** — Wear OS requires 35. A BLOCK here is the false positive the rule was corrected to prevent |
| `android-tv-app` | 34 | **pass** — leanback means TV, which requires 34 |
| `automotive-app` | 35 | **pass** — automotive requires 35 |
| `sane-control` | 36 | pass, and the evidence says the decision was made for a phone |

Every one of these must state in the evidence which form factor it decided for. A pass whose
reasoning is invisible is indistinguishable from a rule that did not run.

## Secrets and flavors

| Case | Right answer |
|---|---|
| `secret-key-gitignored` | AMZ-IAP-01 is **not** a BLOCK: the key is gitignored on purpose and the build file says it is added at build time. RISK at most, worded as a release-time check. This is the SeriesGuide case |
| `flavors-and-overrides` | AMZ-IAP-07/08 fire on the amazon flavor's "Get the full version on our website" string; the play flavor is untouched. Amazon SDK in the amazon flavor and Play billing in the play flavor is **correct scoping** — X-FLAVOR-01 must stay silent here |

## The inputs that are simply broken

For `empty`, `no-android`, `manifest-not-xml`, `manifest-empty`, `manifest-not-utf8`,
`manifest-xml-bomb`, `symlink-loop`, `dangling-symlink`, `manifest-is-a-directory`,
`unreadable-file`, `deep-tree`, `weird-names`, `huge-single-line`, `aab-not-a-zip`,
`aab-empty-zip`, `aab-truncated-so`, `aab-lying-elf-header`, `aab-so-is-empty`:

the answer is always the same shape — **no crash, no silent pass, a named reason**. The XML entity
bomb has one extra requirement: whatever parses the manifest must not expand entities, so the run
finishes in milliseconds rather than eating memory.

## The four counters, per case

Section 11 of `rules-catalog.md` makes decidability a measured output. The acceptance table pins it,
because a counter nobody checks drifts into decoration:

| Case | decided | undecidable | not applicable |
|---|---|---|---|
| `sane-control` | GP-API-01, GP-BILL-01 | none | the whole Amazon family — no amazon flavor |
| `gradle-computed-version` | GP-BILL-01 | GP-API-01, reason quoted with its line | Amazon family |
| `toml-broken` | none | GP-API-01 and GP-BILL-01, reason "the catalogue does not parse" | Amazon family |
| `empty` | none | none | everything — and the report says so rather than showing all green |
| `flavors-and-overrides` | the Amazon family, X-FLAVOR-01 (silent, correct scoping) | none | GP-16KB-01, no native libraries |
| `wear-os-app` | GP-API-01, decided **pass** for form factor `wear` | none | Amazon family, billing |

**`empty` is the case that catches a lying tool.** A scanner that reports "0 findings" on an empty
directory is indistinguishable from one that works, until the day it silently stops working. The
counters must show nothing was decided.

## How this is used

Task 3 asks Bob for a unit test per rule. The tests must cover this table, and the cases here are
the fixtures. On Sunday morning the same table is the acceptance list: any row where the tool
disagrees is either a bug to fix or a line in "what it does not do" — never something quietly left
out of the report.
