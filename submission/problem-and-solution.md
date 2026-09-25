On 10 September I uploaded an Android app to the Amazon Appstore. On 11 September it was rejected:
"IAP displays error." On my test phone the purchase worked. The build was missing one file — the
app's own `AppstoreAuthenticationKey.pem` — which no emulator can reveal, because an emulator has no
Appstore on it. The fix took four minutes. Getting back to a published app took 73 hours and two
more uploads.

That is the workflow StoreGreen improves: release and deployment. The reviewer is the first thing in
the pipeline that checks whether a build satisfies the store, and it runs after you upload. Between
writing the code and learning it is wrong there is a queue measured in days, and everything that
goes wrong in that gap is knowable from the repository in advance. Nothing looks.

StoreGreen is a preflight for Android releases. It reads a project the way a reviewer would: merges
the manifests in Gradle's own order, resolves versions out of `libs.versions.toml`, `build.gradle`
or `buildSrc`, and reads the bundle you are about to ship: the Amazon purchase key, the declared
receiver, the alignment of every native library, whether one store's billing leaked into another's. Each finding names the rule, the file, the line and the fix. Exit code 1 means a
store would reject this. `--fix` applies the deterministic repairs and re-scans;
`--explain-rejection` maps a rejection e-mail back to rules and lines.

Three things make it worth a judge's attention.

**It covers ground nothing else does.** The closest tools — `rejectproof`,
`app-store-preflight-skills`, `store-preflight-mcp` — are iOS, or Play policy only. None checks
Amazon Appstore in-app purchasing, and none maps a rejection e-mail to a line of code.

**It is measurably right on real software.** I measured the expected answers on four of my own
shipping bundles before a line of it existed, so the acceptance test had a known result. Then it ran
over **83 public Android repositories found by searching GitHub**: 69 BLOCK findings in 45 of them,
29 where it said honestly that it could not decide, and **zero crashes**. It also found two defects
in my own published apps I did not know about — a native library not aligned for 16 KB pages, so
that app cannot be updated on Play after 1 February 2027, and another shipping Play's billing
library inside its Amazon build.

**It refuses to guess.** A Wear OS app at `targetSdk 35` is correct, not a violation — the required
level depends on form factor, and the report names the one it decided for. A key absent
from a public repository is a secret kept properly. A value that comes from an environment variable
is reported as `cannot be determined`, with the line it gave up on. Every run prints how many rules
were decided, undecidable, not applicable and not implemented, so a report can never imply coverage
it does not have.

The deadline is real: every Play extension for API 36 and Billing 8 expires on 1 November 2026.
