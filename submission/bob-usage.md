Bob 2.0 wrote StoreGreen. I wrote the specification before the hackathon opened — the rules, the
evidence model, the acceptance table — and published it with dated commits so the split is
checkable. Everything under `src/` was produced inside Bob IDE across six tasks costing 38 of the
40 Bobcoins, and each task's session summary is in `bob_sessions/`.

**Plan mode, before any code.** The first task gave Bob the specification and forbade it from
writing anything: read this, propose the architecture, and tell me what is wrong with the spec. It
returned a module layout I adopted unchanged, a type I had not thought of — `NotApplicable`,
distinct from `Undecided`, so a rule whose precondition is absent does not count against the
decidability score — and **ten problems in my specification**. Three were real contradictions I had
introduced: a table dated a Play Billing deadline to 2027 while the source list below still said
2028; a rule was promised in bundle mode by one section and dropped by another; and a row implied a
BLOCK for a missing Amazon key in a source tree, which another section forbids, because the key is a
secret and a public repository is right not to contain it. My own verification suite had missed the
date contradiction — it searched for one exact sentence and the stale claim was worded differently.
Bob's review caught what my tests did not. That task cost 0.093 Bobcoins.

**Agent mode, and it reasoned about causes rather than fitting to green.** Bob diagnosed all seven
of its own first test failures without help, naming four distinct causes. Later a test demanded that
`--fix` modify a manifest; Bob's implementation was right and the test was wrong, because in source
mode those rules are undecidable and repairing what you cannot read is the guessing the whole design
forbids. Earlier, the opposite: a fixture looked broken and the rule was.

**The bug I care about most was Bob's own, and Bob found the class.** Our defective fixture came
back clean: a ProGuard keep rule written inside a comment was matching, so any project where someone
had commented those lines out while debugging would have received a clean verdict immediately before
uploading. Bob then audited every rule that searched raw text and listed them, rather than fixing
only the one I pointed at.

**Document understanding.** `--explain-rejection` reads the real Amazon e-mail from 11 September.
That e-mail names no cause — only a symptom. So Bob maps the symptom to the rules that could produce
it, intersects that with what the scan actually found, and reports three groups: violated here,
clean here, and sentences that map to nothing.

Parallel subagents were launched for the four rule families; a connection failure to Bob's backend
killed them mid-flight and it completed the work directly. That is in the transcript, and I would
rather say so.

What I did by hand: the specification, the adversarial corpus of 35 malformed inputs, the crash
hunter, and the video.
