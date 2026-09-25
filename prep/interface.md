# The interface, pinned before Bob invents one

Three things were never specified and Bob would have chosen them for us: the command line, the JSON
shape, and the exit codes. Everything downstream depends on them — my HTML polish, the video, the
README, the GitHub Action — so they are fixed here and Task 2 implements exactly this.

## Command line

```
storegreen --repo PATH            scan a source tree (default: .)
           --aab FILE             scan a built bundle instead of, or in addition to, the tree
           --only RULE            run one rule or family; repeatable (AMZ-IAP, GP-API, GP-BILL, …)
           --fix                  apply the deterministic repairs, then re-scan and report both
           --explain-rejection F  read a store rejection e-mail and map it to rule ids
           --last-version N       the versionCode already uploaded, for X-VER-01
           --json                 machine-readable to stdout, nothing else on stdout
           --html PATH            write one offline page
           --quiet                exit code only
           --no-colour            plain text
```

Flags are additive: `--repo` and `--aab` together scan both and merge the findings, marking each
with where it was decided. Nothing else may write to stdout in `--json` mode, and **nothing may
ever write to stderr on a successful run** — the crash hunter fails the build on a single byte.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | scanned, nothing that blocks a release |
| 1 | at least one **BLOCK** finding — the store would reject this |
| 2 | could not run at all: the path does not exist, or is not a directory |

**RISK, WARN and undecidable do not change the exit code.** A CI that fails on "this permission may
need a declaration" gets turned off within a week, and then nothing is checked at all. Exit 1 is
reserved for "the store will reject this", which is a claim we can defend line by line.

## JSON

```json
{
  "tool": "storegreen", "version": "0.1.0",
  "scanned": {"repo": "/abs/path", "aab": null, "modules": ["app"], "form_factor": "phone"},
  "summary": {"block": 1, "risk": 2, "warn": 0, "undecidable": 3, "passed": 15, "seconds": 0.42},
  "findings": [
    {
      "rule": "AMZ-IAP-03", "family": "amazon-iap", "severity": "BLOCK",
      "title": "the Amazon purchase receiver is not declared",
      "evidence": {"file": "app/src/amazon/AndroidManifest.xml", "line": 14,
                   "found": "<service android:name=\"...PurchasingService\"/>",
                   "expected": "a ResponseReceiver with the NOTIFY intent-filter"},
      "fix": {"automatic": true, "description": "add the receiver block to the amazon manifest"},
      "decided_from": "source"
    }
  ],
  "undecided": [
    {"rule": "GP-API-01", "reason": "targetSdk comes from System.getenv('SDK')",
     "evidence": {"file": "app/build.gradle", "line": 2}}
  ],
  "passed": [{"rule": "AMZ-IAP-01", "note": "key present in app/src/amazon/assets"}]
}
```

Rules for it: every finding carries `rule`, `severity`, and an `evidence` object with a file and a
line — **a finding without evidence is a bug, not a finding**. `undecided` is a separate list, not
findings with a special severity, because a judge scanning the output must see instantly that the
tool distinguishes "wrong" from "unknown". `passed` is present for the same reason: a report that
only lists problems cannot be told apart from a report that failed to run.

`decided_from` is `"source"`, `"bundle"` or `"both"`, so a reader always knows which half of the
tool produced a line.

## The HTML page

One file, no stylesheet, no script from anywhere else, no image, no network request of any kind —
a judge opens it offline and it is entirely the result. Scorecard at the top, findings first,
`undecided` in its own section, `passed` collapsed at the bottom. This is the frame the video shows,
so the layout is settled here rather than negotiated on Sunday.

## Stability

Rule ids are the contract. They appear in the terminal output, the JSON, the HTML and the tests,
and once a rule ships with an id the id does not change — the `--explain-rejection` mapping and the
fixtures both reference them.
