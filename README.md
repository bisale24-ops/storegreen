# StoreGreen

Know why the store will reject your build — before the store does.

```bash
git clone https://github.com/bisale24-ops/storegreen && cd storegreen
./run.sh --repo path/to/android-project          # nothing to install
./run.sh --aab path/to/app.aab                   # or read what you actually ship
```

## The problem

On 10 September I uploaded an Android app to the Amazon Appstore. On 11 September it was rejected:
*in-app purchase displays an error*. The build was missing one file — the app's own
`AppstoreAuthenticationKey.pem` — which no emulator can reveal, because an emulator has no
Appstore on it. The fix took four minutes. Getting back to a published app took **73 hours and two
more uploads**.

The reviewer is the first thing in the release pipeline that checks whether a build satisfies the
store, and the reviewer runs *after* you upload. Everything that goes wrong in that gap is knowable
from the repository in advance, and nothing looks.

## What it checks

Eight rules ship. Each one has already been run against real, shipping software — it either fired
or came back clean on four bundles that are on sale today, before a line of the tool existed.

| rule | it asks | evidence |
|---|---|---|
| `AMZ-IAP-01` | is the Amazon purchase key in the bundle? | `base/assets/AppstoreAuthenticationKey.pem`, with its SHA-256 |
| `AMZ-IAP-03` | is the purchase receiver declared? | the merged manifest, or the bundle's protobuf manifest |
| `AMZ-IAP-04` | can the app see the Appstore at all? | `<queries>` for `com.amazon.venezia` |
| `AMZ-IAP-06` | will R8 strip the SDK? | `isMinifyEnabled` and the ProGuard keep rules |
| `GP-API-01` | is `targetSdk` high enough **for this form factor**? | Gradle, plus the manifest's form-factor features |
| `GP-BILL-01` | is Play Billing 8 or later? | the version catalogue, the build file or `buildSrc` |
| `GP-16KB-01` | are the native libraries 16 KB aligned? | `PT_LOAD` alignment in every `base/lib/arm64-v8a/*.so` |
| `X-FLAVOR-01` | has one store's billing leaked into another's build? | the manifest permission **and** the dex classes |

## What it does not do

- It does not judge what it cannot decide. A `targetSdk` that comes from an environment variable is
  reported as `cannot be determined`, with the line it gave up on — never as a pass.
- It does not treat a kept secret as a defect. A purchase key absent from a public repository is
  correct; that is RISK with an explanation, and BLOCK only when a built bundle is missing it.
- It does not apply one number to every device. Wear OS, TV and Automotive have their own required
  API levels, and the finding names the form factor it decided for.
- It does not imply coverage it lacks: every unimplemented rule is listed by id.
- It runs no code from the project, imports nothing from it, and makes no network request.

## The number it prints about itself

```
{{FILL: the decidability line from a real run}}
```

Decided, undecidable, not applicable, not implemented — on every run, in every output format. Run
it twice on the same tree and the four numbers are identical.

## Verified, not asserted

{{FILL: tests, interpreters, corpus results, public repositories scanned}}

## Built with IBM Bob 2.0

Everything under `src/` was written inside Bob IDE during the hackathon; the session summaries are
in `bob_sessions/`. The specification in `prep/` was written before the event and committed with
dates, so the split is checkable. Bob reviewed that specification before writing any code and found
three contradictions in it — see `prep/task1-architecture.md`.

## Licence

MIT.
