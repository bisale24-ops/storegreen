# Prompts for the Bob IDE sessions

These are his to paste, one per task, in order. Every one of them produces a Bob **task**, and every
task gets a session-summary screenshot into `bob_sessions/` before moving on. They are written in
English because the submission must be.

**Rules that shaped them.** Few and large, not many and small: 40 Bobcoins, no top-ups. Each prompt
points Bob at a file in `prep/` instead of restating the spec, so the tokens go into work rather
than into re-reading requirements. Each one also ends by asking for a short written summary — that
is what makes the session summary legible in the screenshot.

After each task: **Tasks → select the task → click the task header → screenshot the session
consumption summary → save as PNG** into `bob_sessions/`, named
`khlab_taskNN_<slug>_summary.png`.

---

## Task 1 — architecture (plan mode, cheapest)

> Read `@prep/rules-catalog.md` — **including the section "Implementation decisions, verified
> against real artifacts" at the end, which is settled and must not be redesigned** — and
> `@prep/demo-fixtures.md`. They specify a command-line tool,
> StoreGreen, that scans an Android repository and its built artifacts and reports why the Amazon
> Appstore or Google Play would reject the submission.
>
> Do not write code yet. Propose the architecture: the module layout, the shape of a rule, how a
> rule reports evidence (file, line, what was found, what the store requires), the JSON report
> schema, and how the HTML report is produced from it. Say explicitly which rules can be decided
> from source files alone and which need the built AAB.
>
> Three things are already decided and are not open questions: the bundle manifest is protobuf so
> no AXML parser is written; the source-mode manifest merge is main → flavor → build type with
> library manifests excluded; and any rule that cannot be decided reports `cannot be determined`
> with the reason and the line it gave up on, never a pass.
>
> Finish with a numbered build order for the next tasks, and flag anything in the spec that is
> ambiguous or that you think is wrong.

## Task 2 — skeleton and parsers (agent mode)

> Using the architecture you proposed, create the project. **`@prep/interface.md` fixes the command
> line, the JSON shape and the exit codes — implement exactly that, do not improve on it**, because
> the report, the page and the demo are being written against it in parallel. Build the CLI entry
> point, the Android manifest and Gradle parsers, the rule interface, the JSON report writer, and
> the HTML renderer.
> No rules implemented yet beyond one trivial example that proves the pipeline end to end.
>
> Add unit tests for the parsers against the fixtures described in `@prep/demo-fixtures.md`, and
> make `pytest` pass. MIT licence, no network calls anywhere in the tool.
>
> Then run the example end to end and show me the JSON and the HTML it produced.

## Task 3 — the rule families (agent mode, subagents)

> Implement **only the eight tier-one rules** listed in section 10 of `@prep/rules-catalog.md`.
> Do not implement tier two; instead, make the report list every tier-two rule by id as
> `not implemented`, so coverage is never implied. Eight finished rules beat twenty-one started.
> Use one subagent per family so they run in parallel: **A** Amazon Appstore IAP (four rules),
> **B** Google Play dated requirements (two), **C** the native-library rule, **D** cross-store. Each rule must carry its id, severity, the evidence it found, and the
> exact fix.
>
> The expected verdicts are already written down in `@prep/corpus-expectations.md`, including the
> cases that must come back **clean** — a Wear OS app at targetSdk 35 is correct, not a violation,
> and correctly scoped per-store dependencies are not a leak. Encode that table as tests.
>
> Every rule needs a unit test that fails on a defective fixture and passes on a clean one. A rule
> that cannot be decided from the repository must report `cannot be determined` with the reason —
> never a pass. Make the whole suite green, then print a table of rule id, family, severity and
> whether it is covered by a test.

## Task 4 — the defective demo app, and the real bundles (agent mode)

> Build the demo fixture described in `@prep/demo-fixtures.md`: a small but real Android project
> that contains the seeded defects, each one traceable to a rule id. Keep it minimal — it exists to
> be scanned, not to be shipped.
>
> Run StoreGreen against it and show the report. I expect every seeded defect to be found; list any
> that were missed and why.
>
> Then run the bundle mode against four real, shipping Amazon bundles in `~/Desktop/KHLab/`:
> `numsly-amazon-v7.aab`, `lockly-amazon-v3.aab`, `scanly-amazon-v5.aab`, `smeta-amazon-v3.aab`.
> The expected result is known and is the acceptance test for this task. All four carry
> `base/assets/AppstoreAuthenticationKey.pem`, with four different SHA-256 fingerprints. Of the
> fifteen 64-bit native libraries exactly one fails the 16 KB rule — `libsqlcipher.so` in Numsly,
> `p_align 0x1000`. And exactly one bundle fires X-FLAVOR-01: **Scanly**, which ships
> `com.android.vending.BILLING` in its manifest and `com/android/billingclient` in `classes.dex`
> inside an Amazon build; Numsly is the clean control. If your implementation reports anything
> else, it is your implementation that is wrong, not the bundles.

## Task 5 — `--fix`, and proving it worked (agent mode)

> Add `--fix`: apply the safe fixes for the findings that have a deterministic repair, leave the
> rest reported. Show a diff of everything you change, and never touch a file outside the scanned
> repository.
>
> Then run the scan again on the fixed fixture and show before-and-after: findings by severity,
> what remains, and why each remaining item cannot be fixed automatically.

## Task 6 — the rejection e-mail (document understanding)

> Here is a real Amazon Appstore rejection e-mail for one of my apps. Read it and map it to the
> rules in `@prep/rules-catalog.md`: which rule ids does it correspond to, which lines in the
> scanned repository are the cause, and what is the fix for each.
>
> Then add a `--explain-rejection <file>` flag that does this mapping from a pasted rejection text,
> with a test that uses this e-mail as the fixture. If a sentence in the e-mail maps to no rule, say
> so instead of guessing.

*(He pastes the rejection text under the prompt. It is his own e-mail about his own app — his data,
which the rules allow; no client data, no personal information beyond his own.)*

---

## What I do around these, in Bob Shell

Under an explicit cap each time, and only after the task above has its screenshot:

```bash
bob run --max-cost 2 --max-turns 8 --format json "…" > runs/taskNN.json
```

Review of every diff, the test runs, the fixtures, the HTML report polish, the README, the video,
the slides, the form — those are mine and cost no Bobcoins at all.

---

## If the Bobcoins start running out

40 for everything, no top-ups, and the IDE and the Shell draw on the same pot. Check the balance in
**Settings → General** after every task and write it down — a number per task tells us the burn rate
while there is still time to act on it.

Sacrifice in this order, because the challenge rewards specific things and some of these tasks are
the evidence for them:

1. **Task 4 first.** Fixtures are test data, not the product. I can write the defective Android
   project by hand for zero coins; nothing in the judging asks who typed the fixture.
2. **Then the polish passes.** README, the HTML report's styling, the GitHub Action wrapper — all
   mine, all free.
3. **Never Task 5 or Task 6.** `--fix` is the Agent-mode evidence and the rejection e-mail is the
   document-understanding evidence; those two are named criteria, and a submission without them is
   a report generator competing against agents.
4. **Never the session screenshots.** A task whose summary was not captured may as well not have
   happened: `bob_sessions/` is what makes any of this count.

If the balance falls below roughly a quarter with Tasks 5 and 6 still unstarted, stop building
features and spend what is left on those two.
