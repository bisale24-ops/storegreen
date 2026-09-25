# IBM Bob Usage Statement

*(target: 500 words or less)*

Bob 2.0 wrote StoreGreen. I wrote the specification before the hackathon opened — the rules, the
evidence model, the acceptance table — and published it with dated commits so the split is
checkable. Everything in `src/` was produced inside Bob IDE, and every task's session summary is in
`bob_sessions/`.

**Plan mode, before any code.** The first task gave Bob the three specification files and forbade
it from writing anything: read this, propose the architecture, and say what is wrong with the spec.
It came back with a module layout I adopted unchanged, a type I had not thought of — `NotApplicable`,
distinct from `Undecided`, so a rule whose precondition is absent does not count against the
decidability score — and **ten problems in my specification**. Three were real contradictions I had
introduced: one table dated a Play Billing deadline to 2027 while the source list three lines below
still said 2028; a rule was promised in bundle mode by one section and dropped by another; and a
row implied a BLOCK for a missing Amazon key in a source tree, which section 7 of the same document
forbids because the key is a secret and a public repository is right not to contain it. My own
verification suite had missed the date contradiction, because it searched for one exact sentence
and the stale claim was worded differently. Bob's review caught what my tests did not. That task
cost 0.093 Bobcoins.

**Parallel subagents for the rule families.** The eight shipping rules divide into four
independent families — Amazon in-app purchasing, the dated Play requirements, native library
alignment, and cross-store leakage — over the same repository. Bob ran one subagent per family
concurrently, each writing its rules and the unit tests that pin them to the acceptance table.
[fill: what that produced, and how long it took]

**Agent mode for the repairs.** `--fix` is not a suggestion list. Bob applies the deterministic
repairs to the manifest, the ProGuard rules and the Gradle files, shows the diff, and re-runs the
scan so the before and after are both in the report. What it cannot invent — the purchase key
itself — it refuses to fake, and prints the console path to download it instead.

**Document understanding on a real rejection.** `--explain-rejection` takes the actual e-mail
Amazon sent me on 11 September and maps its sentences to rule ids and to the lines that caused
them, saying plainly which sentences map to nothing rather than inventing a match.

[fill: total tasks, total Bobcoins, files written by Bob]

What I did by hand was the specification, the adversarial corpus of 35 malformed inputs, the crash
hunter that runs the tool over all of them in three output modes and fails on any traceback, empty
output or stray byte on stderr, and the video. What Bob did was the product.
