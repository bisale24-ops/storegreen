# Rules catalog — store rejection preflight

Spec for the checker Bob will build on 25–27.09. Every rule has: what fails, how to detect it statically
from the repo / built AAB, how to fix it, and where the rule comes from. No code here on purpose —
the implementation must be written with IBM Bob during the event.

Severity: **BLOCK** = the store will reject or refuse the upload. **RISK** = likely rejection at review.
**WARN** = not a rejection today, but a dated deadline.

---

## A. Amazon Appstore — In-App Purchasing (Appstore SDK)

Origin: real rejection. CrewSheet 1.0.0, 11.09.2026, Content Policy FAILED — "IAP displays error".
Tested on an emulator and a Galaxy phone without the Appstore, where a failed purchase looks normal.

| ID | Sev | Fails when | Detect | Fix |
|----|-----|-----------|--------|-----|
| AMZ-IAP-01 | BLOCK **in bundle mode only** | `AppstoreAuthenticationKey.pem` missing from the shipped bundle | AAB `base/assets/`. In a source tree its absence is RISK with the reason "the key is a secret and does not belong in a public repository" — see section 7, and never a BLOCK | download the app's own public key: Console → app → Upload Your App File → Additional information → View public key |
| AMZ-IAP-02 | BLOCK | the key belongs to a different app | fingerprint of the .pem equals another app's key in the same workspace | each app has its own key; never copy between apps |
| AMZ-IAP-03 | BLOCK | no `com.amazon.device.iap.ResponseReceiver` in merged manifest | receiver absent, or not `exported="true"`, or missing `permission="com.amazon.inapp.purchasing.Permission.NOTIFY"`, or no intent-filter `com.amazon.inapp.purchasing.NOTIFY` | add the receiver block; a `PurchasingService` service does not replace it |
| AMZ-IAP-04 | BLOCK | `<queries>` lacks `com.amazon.venezia` (and `com.amazon.sdktestclient`) with targetSdk ≥ 30 | parse merged manifest | add both `<package>` entries |
| AMZ-IAP-05 | RISK | app blocks `purchase()` behind its own checks | call sites where `PurchasingService.purchase` is guarded by `getUserData` result or package-presence checks | call `purchase()` directly; Amazon opens the purchase UI itself |
| AMZ-IAP-06 | BLOCK | R8 strips/merges SDK classes | release `isMinifyEnabled = true` and proguard lacks `-keep class com.amazon.** { *; }`, `-dontwarn com.amazon.**`, `-keepattributes *Annotation*` (rules only for `com.amazon.device.iap.**` are not enough) | add the three lines; symptom at runtime: `registerListener` → "Resource already registered" |
| AMZ-IAP-07 | RISK | flavor string overrides still say the old thing | `src/<amazonFlavor>/res/values*/strings.xml` shadows a key fixed only in `main` | diff flavor overrides against main |
| AMZ-IAP-08 | RISK | links that send buyers outside Amazon ("full version on our site") | URLs / text in amazon flavor resources pointing to an external purchase | remove from the amazon flavor |

Evidence rule for the report: every finding cites file + line, or AAB entry path. No finding without evidence.

Sources: Amazon docs `iap-implement-iap`, `appstore-sdk-troubleshooting`; our own rejection notice.

## B. Google Play — dated platform requirements (re-verified 22.09.2026 against official pages)

| ID | Sev | Fails when | Detect | Fix |
|----|-----|-----------|--------|-----|
| GP-API-01 | BLOCK | new app / update below the level required for its **form factor** — since 31.08.2026; extension to 01.11.2026 | `targetSdk` in module build file / merged manifest, **and the form factor from the manifest** | raise to the required level, then run behaviour-change checks |
| GP-API-02 | WARN | existing app below the availability floor for its form factor stops reaching new users | same | raise |
| GP-BILL-01 | BLOCK | Play Billing Library < 8 in a new app or update — since 31.08.2026 (extension to 01.11.2026) | `com.android.billingclient:billing*` version in dependencies / version catalog | migrate to 8+ (note v8 API removals) |
| GP-16KB-01 | WARN (BLOCK from 01.02.2027) | native `.so` not aligned for 16 KB pages, targetSdk ≥ 35, 64-bit | ELF `LOAD` segment alignment < 2^14 in AAB `lib/arm64-v8a/*.so` | AGP 8.5.1+, NDK r28+, rebuild native deps. From 01.02.2027 updates that do not support 16 KB cannot be released; no extension mentioned |
| GP-BILL-02 | WARN | Play Billing Library < 9 | same as GP-BILL-01 | v9 becomes mandatory **31.08.2027** (extension to 01.11.2027); v10 by 31.08.2028. Each version has two years plus a three-month extension |

## C. Google Play — policy declarations (static signals)

| ID | Sev | Fails when | Detect | Fix |
|----|-----|-----------|--------|-----|
| GP-PERM-01 | RISK | `QUERY_ALL_PACKAGES` without a core use case | permission in merged manifest | replace with targeted `<queries>` |
| GP-PERM-02 | RISK | `MANAGE_EXTERNAL_STORAGE`, SMS / Call Log, `ACCESS_BACKGROUND_LOCATION` | permission present | remove, or prepare the Play declaration form |
| GP-PRIV-01 | BLOCK | app requests sensitive data but has no privacy policy URL | sensitive permissions present and no policy URL in repo store metadata / in-app | add a reachable policy URL |
| GP-DS-01 | RISK | Data Safety answers contradict the build | SDKs that collect data (ads, analytics, crash) present while the saved Data Safety draft says "no data collected" | align the form with dependencies |
| GP-EXP-01 | BLOCK | component with an intent-filter lacks `android:exported` (targetSdk ≥ 31) | merged manifest | set `exported` explicitly |

## D. Cross-store

| ID | Sev | Fails when | Detect | Fix |
|----|-----|-----------|--------|-----|
| X-VER-01 | BLOCK | `versionCode` not higher than the last uploaded one | compare with a `store-state.json` the tool keeps per store | bump |
| X-SIGN-01 | BLOCK | release signed with debug key | AAB signature cert subject `CN=Android Debug` | sign with upload key |
| X-FLAVOR-01 | RISK | one store's billing SDK leaks into another store's flavor | Play Billing in amazon flavor or Amazon IAP in play flavor | scope dependencies per flavor |

---

Sources for B (fetched 22.09.2026):
- targetSdk: support.google.com/googleplay/android-developer/answer/11926878 — API 36 for new apps and updates from
  31.08.2026, extension to 01.11.2026; existing apps below API 35 stop reaching new users on newer devices.
- Billing: developer.android.com/google/play/billing/deprecation-faq — v8+ from 31.08.2026, extension to 01.11.2026;
  v9 from **31.08.2027**, extension to 01.11.2027 (each version expires two years after the one before,
  with a three-month extension; corrected 25.09.2026 and again confirmed by Bob's review of this file).
- 16 KB: developer.android.com/guide/practices/page-sizes — from 01.02.2027 non-compliant updates cannot be released.

**Timing hook for the pitch:** every app that took the Play extension has until **01.11.2026** — about five weeks after
the hackathon. That is the "why now" for business value.

## Decisions (settled 22.09.2026)

- **Source tree by default, built AAB as the second step.** Source mode is instant on stage and covers every rule
  except the ones that need the binary; AAB mode (AMZ-IAP-01 in `base/assets/`, GP-16KB-01 ELF alignment,
  AMZ-IAP-03/04 by string presence, X-FLAVOR-01 by dex) is the "and it also reads what you actually
  ship" moment in the video. **X-SIGN-01 is not part of it** — section 1 drops it from bundle mode,
  and this line used to contradict that.
- GP-16KB-01 date: the developer.android.com page above is the single source; the conflicting older dates are dropped.

---

# Implementation decisions, verified against real artifacts (25.09.2026, before kick-off)

Checked against the four Amazon bundles on the desktop — Numsly v7, Lockly v3, Scanly v5, Smeta v3 —
because a spec written from memory is how Bob ends up building the wrong thing precisely.

## 1. The AAB manifest is protobuf, not binary XML

`base/manifest/AndroidManifest.xml` in a real bundle starts `0a b3 82 01 0a 39 0a 07 android 12 2a
http://schemas…` — protobuf wire format. It is **not** the AXML format an APK uses, so an AXML
parser silently fails on every bundle. Do not write one.

**But protobuf leaves the strings readable**, which was measured, not assumed: every marker the
Amazon rules care about appears as plain UTF-8 inside `base/manifest/AndroidManifest.xml` in all
four bundles — `com.amazon.device.iap.ResponseReceiver`, `com.amazon.venezia`,
`com.amazon.sdktestclient`, `com.amazon.inapp.purchasing.NOTIFY` and the NOTIFY permission. So
bundle mode covers more than presence of files:

| Rule | What is read from the bundle | Confidence |
|---|---|---|
| AMZ-IAP-01 | `base/assets/AppstoreAuthenticationKey.pem` exists; report its SHA-256 | exact |
| AMZ-IAP-03 | the receiver's name appears in the manifest bytes | **presence only** — `exported`, the permission attribute and the intent-filter cannot be attributed to the element without a real protobuf parse. Report "declared" or "absent", never "correctly declared" |
| AMZ-IAP-04 | `com.amazon.venezia` / `com.amazon.sdktestclient` appear | presence only, same caveat |
| X-FLAVOR-01 | `com.android.vending.BILLING` in the manifest, and `com/android/billingclient` in `classes.dex` | exact — two independent signals |
| GP-PERM-01 | `android.permission.QUERY_ALL_PACKAGES` appears | presence only |
| GP-16KB-01 | `base/lib/<abi>/*.so`, ELF program headers | exact |
| X-SIGN-01 | **dropped from AAB mode** — an `.aab` carries a jar signature, and parsing a DER certificate by hand is a day of work for one line of report. Report it as `cannot be determined` and say to run `jarsigner -verify -verbose` |

The honesty rule for presence-only checks: absence is a finding, presence is **not** a pass — it
downgrades to "declared; structure not verifiable from a bundle, re-run on the source tree".

Everything else stays in source mode. This is a strength in the pitch, not a limitation: the tool
answers before a bundle exists, which is the whole point of a preflight.

## 2. The 16 KB check, exactly

Pure Python, no NDK, no `readelf`. For each `base/lib/<abi>/*.so`: confirm `\x7fELF`; byte 4 gives
32/64-bit, byte 5 the endianness; read `e_phoff`, `e_phentsize`, `e_phnum` (at 0x20/0x36 for 64-bit,
0x1c/0x2a for 32-bit); walk the program headers; for every header whose `p_type` is 1 (`PT_LOAD`)
read `p_align` (offset 0x30 in a 64-bit header, 0x1c in a 32-bit one). **A library passes when every
`PT_LOAD` alignment is at least 0x4000.** Only 64-bit ABIs are in scope for the rule.

**And it must not crash on a file that is not what it claims to be.** Writing this check the
obvious way throws `struct.error` on a truncated library — found by running the spec's own
algorithm against a deliberately short buffer before the event. Guard on all of it: fewer than 64
bytes, a class byte that is neither 1 nor 2, an endianness byte that is neither, a program-header
table that runs past the end of the file. The load-bearing part is catching the unpack error
itself — measured: reverting the length guard alone changes nothing, because the exception handler
already covers it, so do not let the explicit guards give a false sense of completeness. They exist
to produce a clearer reason string, not to be the safety net. Every one of those is
`cannot be determined — unreadable ELF`, never a pass and never an exception. An empty result from
the reader must never be read as "aligned": no `PT_LOAD` segments found is itself the undecidable
case.

**Verified baseline, and it is the demo:** across fifteen native libraries in the four bundles,
exactly one fails — `libsqlcipher.so` in Numsly, `p_align 0x1000` on all three `PT_LOAD` segments,
while `libandroidx.graphics.path.so` and `libdatastore_shared_counter.so` beside it are already
`0x4000`. So Numsly cannot be updated on Google Play after 01.02.2027 until sqlcipher is rebuilt.
A real, dated defect in a shipping app beats any seeded fixture — lead the demo with it.
All four bundles do carry `base/assets/AppstoreAuthenticationKey.pem`, with four **different**
SHA-256 fingerprints — so AMZ-IAP-01 is demonstrably not a false accuser, and AMZ-IAP-02's premise
(one key per app) holds on real data.

**Second real finding, and it is the better demo: `X-FLAVOR-01` fires on Scanly.** Its Amazon
bundle carries the Play billing permission `com.android.vending.BILLING` in the manifest *and*
`com/android/billingclient` classes in `classes.dex`, beside the Amazon IAP SDK it actually uses.
Numsly, scanned the same way, carries only Amazon IAP — a clean control in the same run, from the
same author, which is what makes the finding credible rather than a scanner shouting. This is
exactly the bug class the tool exists for: one store's billing leaked into another store's flavor,
shipped, in an app that is on sale.

## 3. What "merged manifest" means when nothing is built

Gradle is not run, so the tool merges what the source tree has, in this order: `src/main`, then the
flavor, then the build type, with later layers overriding by `android:name`. **Library manifests
from AARs are not merged** — they cannot be read without resolving dependencies.

Consequence, and it must be honest in the report: when a rule depends on something a library could
contribute (a receiver, a permission, `exported`), a clean source tree gives
`cannot be determined — a dependency may still contribute this; re-run with --aab`. Never a pass.
This single distinction is what separates a preflight from a linter that lies.

## 4. Reading versions out of Gradle without running Gradle

In order: `gradle/libs.versions.toml`, then a literal in `build.gradle[.kts]`, then a
`ext`/`buildSrc` constant resolvable by plain substitution. If the value is a computed expression,
a function call, or read from a property file that is not in the repository, the rule reports
`cannot be determined` **with the line it gave up on**. Applies to GP-API-01/02, GP-BILL-01/02
and X-FLAVOR-01.

## 5. Three rules that cannot honestly be decided, and what they become

- **X-VER-01** (versionCode higher than the last upload) — nothing in the repository knows what was
  uploaded. It becomes opt-in: compares against a `--last-version N` given on the command line, and
  is otherwise skipped with that reason. It must not invent a `store-state.json` and pretend.
- **GP-DS-01** (Data Safety answers versus dependencies) — the saved Data Safety draft lives in the
  Play Console, not the repo. Keep the useful half: list the dependencies that collect data (ads,
  analytics, crash reporting) as `declare these in Data Safety`, and drop the contradiction claim.
- **AMZ-IAP-02** (key belongs to a different app) — needs two apps to compare. Becomes: report the
  key's SHA-256 so it can be compared by hand, and flag only the case where the same fingerprint
  appears twice under one scan root.

## 6. The impact numbers the challenge asks for

The brief rewards measurable impact, so the tool prints it rather than leaving it to the pitch:

- **The loop it replaces, from our own e-mails:** CrewSheet 1.0.0 submitted 10.09 14:38 UTC,
  rejected 11.09 18:42 UTC, live only as 1.0.2 on 13.09 15:50 UTC — 73 hours and two extra builds
  for one missing file. StoreGreen answers the same question in under a second, before upload.
- **Rules checked / decided / undecidable**, printed at the end of every run.
- **Findings across real repositories**, not fixtures: the four bundles above, plus the open-source
  Android apps scanned on Sunday morning.
- **`--fix` before/after:** findings by severity, what remains and why each remainder is not safe to
  fix automatically.

## 7. A secret that is correctly absent is not a defect

Caught before the event by re-reading the Sunday credibility list. **SeriesGuide** has an `amazon`
flavor and its own build file carries the line *"Note: requires to add AppstoreAuthenticationKey.pem
into amazon/assets"* — the key is deliberately not committed, because it is a secret. A naive
AMZ-IAP-01 would report BLOCK on it, and the maintainer would be right to say the tool is wrong.

So the rule is split by mode, and this is not a detail — it is the difference between a tool an
Android developer trusts and one they close:

- **Source mode:** the key's absence is `cannot be determined — the key is a secret and does not
  belong in a public repository; verify it in the build that produces the bundle`. Severity RISK,
  never BLOCK. If the build file or CI config shows the key being injected, say so and drop it to
  a note.
- **Bundle mode:** absence is BLOCK, because at that point the artifact either ships the key or it
  does not. This is the mode the real CrewSheet rejection would have been caught in.

The same reasoning applies to anything else a repository is *supposed* to omit: signing keys,
`keystore.properties`, service-account JSON. The tool never treats a correctly kept secret as a
finding.

**Pitch value:** the most carefully maintained project in our sample leaves itself a comment in the
build file so a human remembers. StoreGreen turns that comment into a check that runs.

## 8. Target API level is not one number — form factor decides it

Re-read from the official page an hour before kick-off, and it corrected the rule. A single
`targetSdk < 36 → BLOCK` would falsely reject every watch, TV and car app it ever scanned.

| Form factor | Detect in the manifest | Required for new apps and updates, 31.08.2026 | Availability floor for existing apps |
|---|---|---|---|
| Phone / tablet (default) | none of the below | **36** | 35 |
| Wear OS | `uses-feature android.hardware.type.watch` | **35** | 34 |
| Android Automotive | `uses-feature android.hardware.type.automotive` | **35** | 32 |
| Android TV | `uses-feature android.software.leanback` or a LEANBACK_LAUNCHER intent-filter | **34** | 34 |
| Android XR | XR feature / SDK in the manifest | **34** | 34 |

A module can be more than one of these; take the **lowest** applicable requirement and say in the
finding which form factor the decision was made for. If the form factor cannot be determined,
assume phone and say so in the evidence — the report must never hide which assumption produced a
BLOCK.

Sources re-fetched 25.09.2026: `support.google.com/googleplay/android-developer/answer/11926878`
(API 36 for new apps and updates from 31.08.2026, extension to 01.11.2026, availability floor 35)
and `developer.android.com/google/play/billing/deprecation-faq` (the table gives each version's own
expiry: 7 expires 31.08.2026 so 8+ is required now, 8 expires 31.08.2027 so **9+ from then**, 9
expires 31.08.2028).

## 9. The Sunday list, re-verified 25.09.2026 (one hour before kick-off)

Read from the current build files, not from notes:

| Repo | State now | Expected |
|---|---|---|
| `schorschii/FsClock-Android` | targetSdk 36, billing 8.0.0, appstore-sdk 3.0.7, clean `amazon`/`google` flavors | the control: mostly green |
| `jberkel/sms-backup-plus` | targetSdk 35, billing 7.1.1 | two BLOCKs: GP-API-01 and GP-BILL-01, both past the 31.08.2026 deadline |
| `UweTrottmann/SeriesGuide` | `amazon` flavor, deps via version catalog (`libs.amazon.appstore.sdk`), pem not committed by design | exercises both the `libs.versions.toml` resolution and the secret rule above |

All three still match the shortlist taken on 17.09, so Sunday's runs will not have to be improvised.

---

# 10. What actually ships, and what is a stretch

Twenty-one rules half-built is worse than eight rules finished, and with forty Bobcoins on a solo
account the choice is forced rather than philosophical. So the set is split, and the split has a
property worth saying out loud in the pitch:

**every tier-one rule has already been run against a real shipping artifact — it either fired or
came back clean on one of the four bundles, before a line of the tool existed.** None of them is a
rule invented to pad a list.

| Rule | Why it is tier one | Its real-world evidence |
|---|---|---|
| AMZ-IAP-01 | the exact cause of our rejection | present in all four bundles; absent is what CrewSheet 1.0.0 shipped |
| AMZ-IAP-03 | the receiver Amazon requires; no competitor checks it | declared in all four, verified in the protobuf manifest |
| AMZ-IAP-04 | `queries` for `com.amazon.venezia`, silent failure without it | declared in all four |
| AMZ-IAP-06 | R8 strips the SDK and the symptom appears only on a real device | the one that cost two extra builds |
| GP-API-01 | dated, in force since 31.08.2026, extension ends 01.11.2026 | corrected today to decide by form factor |
| GP-BILL-01 | dated, same deadline | `sms-backup-plus` is on 7.1.1 today |
| GP-16KB-01 | dated 01.02.2027 | **fired on Numsly**: `libsqlcipher.so` at `p_align 0x1000` |
| X-FLAVOR-01 | the bug class the tool exists for | **fired on Scanly**: Play billing inside an Amazon build |

Everything else — AMZ-IAP-02/05/07/08, GP-API-02, GP-BILL-02, GP-PERM-01/02, GP-PRIV-01, GP-DS-01,
GP-EXP-01, X-SIGN-01, X-VER-01 — is tier two. Implemented only when tier one is finished, tested and
survives the crash hunt. A tier-two rule that is not built is listed in the report as
**not implemented**, by id, so the report never implies coverage it does not have.

# 11. Decidability is a feature, and it is the number we show

The claim that separates this from a linter is that it knows what it does not know. That is worth
nothing as a sentence in a README and everything as a number in the output, so it is measured:

```
21 rules  ·  8 implemented  ·  6 decided on this repository  ·  2 undecidable  ·  13 not implemented
```

- **decided** — the rule ran and reached a verdict, finding or pass, with evidence;
- **undecidable** — the rule ran and refused, and says why and at which line;
- **not applicable** — the rule does not apply here (no Amazon flavor, no native libraries);
- **not implemented** — tier two, named by id.

Two things follow, and both go in the video:

1. **A repository where more rules are undecidable than decided is itself the finding.** A build
   whose target version comes out of an environment variable and whose dependencies come from a
   composite build cannot be checked by anyone — not by us, not by the reviewer, not by the
   developer. Reporting that honestly is more useful than a green tick.
2. **The score is reproducible.** Run it twice on the same tree and the four numbers are identical;
   they are part of the JSON, and the acceptance table in `corpus-expectations.md` pins what they
   must be for every corpus case.

The strongest single frame in the demo is the one where the tool says nothing at all about a Wear OS
app at target thirty-five, about a Play-scoped billing dependency in a Play flavor, and about an
Amazon key that is correctly absent from a public repository — and says why for each.


---

# 12. Answers to what Bob asked, 25.09.2026 21:15

Bob's plan-mode review found three contradictions I had introduced and seven genuine gaps. The
contradictions are fixed above. These are the rulings on the gaps, so nothing is decided twice:

1. **Which module does an `--aab` belong to?** Match the bundle's application id from its protobuf
   manifest against the `applicationId` of each source module. No match, or more than one: report
   the bundle findings on their own and say the module could not be matched. Bob's proposal, taken.
2. **`X-VER-01` without `--last-version`** is `not applicable`, not undecidable — the precondition is
   missing, not the evidence. The note says how to enable it. Bob's proposal, taken.
3. **`--fix` output**: the JSON gains `"fix_applied": true` and `"findings_before_fix"`, with
   `"findings"` holding the state after. The page renders the two side by side. Bob's proposal, taken.
4. **`--explain-rejection F`**: `F` is a **plain-text file** — the body of a store e-mail, pasted. The
   output is a list of `{quote, rule, evidence, fix}`, one per sentence that maps to a rule, plus a
   list of sentences that map to nothing, shown as such. It never invents a mapping. The fixture is
   `prep/fixtures/amazon-rejection-crewsheet.txt`.
5. **`form_factor` becomes an array** in `scanned`, and the GP-API-01 finding names the specific form
   factor that produced its verdict. Bob is right that a module can be more than one.
6. — fixed above.
7. — fixed above.
8. — fixed above.
9. **`GP-PRIV-01`** goes to tier two with a written assumption: store metadata means a Fastlane
   `fastlane/metadata/android/**/full_description.txt` tree or a `store/` directory at the repo root.
   If neither exists the rule is `not applicable`, not a finding.
10. **`Passed` carries an optional `evidence`**, and it is required for any rule that made a binary
    check — the PEM fingerprint is exactly the case where a pass needs to be auditable. Bob is right
    that the spec contradicted itself here.
