# Problem & Solution Statement

*(target: 500 words or less — count checked before submitting)*

On 10 September I uploaded version 1.0.0 of an Android app to the Amazon Appstore. On 11 September
it was rejected: "in-app purchase displays an error." On my test phone the purchase worked. The
build was missing one file — the app's own `AppstoreAuthenticationKey.pem` — which nothing in the
Android toolchain checks and no emulator can reveal, because an emulator has no Appstore on it.
The fix took four minutes. Getting back to a published app took 73 hours and two more uploads.

That is the workflow StoreGreen improves: **release and deployment**. The reviewer is the first
thing in the pipeline that checks whether a build satisfies the store, and the reviewer runs after
you upload, not before. Between writing the code and learning it is wrong there is a queue measured
in days. Everything that goes wrong in that gap is knowable in advance from the repository — and
nothing looks.

StoreGreen is a command-line preflight for Android releases. It reads a project the way a reviewer
would: merges the manifests in Gradle's own order, resolves versions out of `libs.versions.toml`,
`build.gradle` or `buildSrc`, and reads the bundle you are about to ship — the presence of the
Amazon key, the declared purchase receiver, the alignment of every native library. Each finding
names the rule, the file and the line, and the fix. Exit code 1 means a store would reject this;
`--fix` applies the repairs that are deterministic and re-runs the scan.

Three things make it worth a judge's attention.

**It covers ground nothing else does.** The closest tools — `rejectproof`, `app-store-preflight-skills`,
`store-preflight-mcp` — are iOS, or Play policy only. None of them checks Amazon Appstore in-app
purchasing, which is where our own rejection came from, and none maps a rejection e-mail back to a
line of code.

**It is measurably right on real software.** Before a line of it existed I measured the answers on
four of my own shipping bundles, so the acceptance test has a known result. It found two defects I
did not know about: a native library in one app is not aligned for 16 KB pages, so that app cannot
be updated on Google Play after 1 February 2027; and another ships Google Play's billing library
inside its Amazon build. [fill: results across N public repositories]

**It refuses to guess.** A Wear OS app at `targetSdk 35` is correct, not a violation — the required
level depends on form factor. A purchase key absent from a public repository is a secret kept
properly, not a defect. When a value comes from an environment variable, the rule reports
`cannot be determined` and names the line it gave up on. Every run prints how many rules were
decided, how many were undecidable and how many are not implemented, so the report can never imply
coverage it does not have.

The deadline that makes this urgent is real: every Play extension for API 36 and Billing 8 expires
on 1 November 2026, five weeks from now.
