# Build plan — 48 hours with IBM Bob 2.0

Tagline: "Know why the store will reject your build before the store does."
**Name: StoreGreen** (his choice, 22.09.2026). Earlier picks dropped: "Rejectless" (rejectless.app is taken) and
"RejectProof" (an iOS product with the same idea launched under that name on 18.09.2026, see competitors).

## Nearest competitors (checked 17.09.2026)
- `app-store-preflight-skills` (1.4k★) — iOS/macOS App Store only.
- `store-preflight-mcp` — iOS + Google Play policy (permissions, data safety, foreground services); no Amazon, no IAP,
  no billing-library / target-SDK deadlines.
- **`rejectproof` (rejectproof.com, npm, GitHub Action, launched 18.09.2026)** — scans an iOS `.ipa` for 43 App Store
  rejection causes, fixes sold as a $12 report. Same idea, iOS only, and it owns the name we had picked.
  Useful in the pitch: the iOS side is already a paid product; Android and Amazon have nothing equivalent.
- **App Store Reject (appstorereject.com)** — rejection database, appeal letters, OCR of a rejection screenshot matched
  to known rejection types, Apple + Google, no Amazon, no line-level checks, no fixing. It overlaps our
  "paste the rejection e-mail" step, so that step is supporting evidence in the demo, not the headline.
- Our edge: Amazon Appstore IAP integration (nobody covers it), dated Play deadlines, evidence per line,
  Bob applies fixes, rejection e-mail → rule mapping. Don't lead with permissions/data safety — that's their ground.

## Challenge fit

Challenge text: improve a specific developer workflow (… **release and deployment** …), define where time/effort/errors
are too high today, build a working prototype with Bob 2.0, use Agent mode, parallel tasks, subagents, document understanding.

| Challenge asks for | StoreGreen answer |
|---|---|
| Problem where time/errors are too high | one Amazon rejection = resubmit + days of review queue; CrewSheet: submitted 10.09 14:38 UTC, rejected 11.09 18:42 UTC, live 13.09 15:50 UTC with 1.0.2 — two days and two extra builds (dates from Amazon's e-mails) |
| Agent mode | Bob applies fixes to the Android repo, not just reports |
| Parallel tasks / subagents | one subagent per rule family (Amazon IAP, Play platform, Play policy, cross-store) over the same repo |
| Document understanding | Bob reads the store's rejection e-mail / policy page and maps it to rule IDs |
| Measurable impact | before/after: findings count, time to green, "would have been rejected" verdict |

## Submission requirements (lablab page, checked 22.09.2026)

Title, short and long description, tags; **cover image, video presentation, slide deck**; **demo application platform
and application URL**; code where Bob assisted; **screenshots of Bob task session summaries**. Code must be MIT.
No stated requirement for the presenter's face or voice, so the TTS video plan stands.
Application URL: the repo made public with an MIT licence, plus a GitHub Pages site that serves a real HTML report
from the demo run, so a judge sees the output without installing anything.
Registration closed 25.09 02:00 Bishkek; we are in — lablab sent "You've been approved" on 12.09.2026.

## Who does what

- **Aleksandr:** activates Bob on 25.09 21:00 (login, license), final export of Bob task summaries from the IDE
  (screenshots are mandatory), presses Submit. **No recording with his voice** (decision 22.09.2026).
- **Claude:** drives Bob Shell headless (`bob run --max-cost N --max-turns N`; there is no `--yolo` in 2.0.4), reviews every diff, runs tests, writes
  slides/cover/descriptions, fills the submission form, and **builds the video**: terminal/report screen captures
  via Playwright + edge-tts voiceover (en-US-AndrewNeural) + ffmpeg, same pipeline as
  `crewvoice/submission/video-build/` (record.py / edit.py / cards.html).
- Not a fallback but the plan: Bob **IDE** sessions are his, because the IDE cannot be typed into by me and its
  session summaries are the required evidence. Bob **Shell** (installed, v2.0.4) is mine, always under `--max-cost`.
  Both draw on the same 40 Bobcoins, so the evidence sessions get the budget first.

## Bob budget rule

Usage is limited. Few large, precise tasks instead of many small ones. Each prompt references
`prep/rules-catalog.md` by path so Bob reads the spec instead of us retyping it.

## Timeline (Bishkek time)

**Fri 25.09**
- 21:00 kick-off, access, `bob --version`, confirm headless mode and how task summaries are exported.
- 21:30 Task 1 (Bob, plan mode): read `rules-catalog.md`, propose architecture. We review.
- 22:30 Task 2 (Bob, agent mode): scaffold CLI + manifest/Gradle parsers + report format (JSON + HTML).

**Sat 26.09**
- Task 3 (Bob, parallel subagents): implement rule families A, B, C, D, each with unit tests on fixtures.
- Task 4 (Bob): generate the demo fixture app with seeded defects (see `demo-fixtures.md`).
- Task 5 (Bob, agent mode): `--fix` — apply safe fixes, re-run, show green.
- Task 6 (Bob, document understanding): paste the real Amazon rejection text → mapped to AMZ-IAP-01/03.
- Evening: HTML report polish (this is the visual for the video), GitHub Action wrapper.

**Sun 27.09**
- until 14:00 freeze features; README, run on 2 public open-source Android repos for credibility.
- 14:00–17:00 video (TTS voiceover, screen captures, no own voice) + slides + cover. Export Bob task session summaries as PNG into **`bob_sessions/`** — that exact folder name is the required deliverable (guide, 24.09); `bob-reports/` would not be looked for.
- 18:00 fill the form; 19:00 Submit (2 h buffer before 21:00).

## Demo story (3 min)

1. Hook: a real rejection e-mail on screen — "IAP displays error". Three days lost.
2. Run StoreGreen on that build state → red report: missing key, missing receiver, missing queries, R8 rule.
3. Paste the rejection e-mail → Bob maps it to the exact rules and lines.
4. `--fix` → Bob patches manifest, proguard, assets note → re-run → green, verdict "ready to submit".
5. Same run on a Play build: targetSdk 35 and Billing 7 → blocked since 31.08.2026.
6. Close: how Bob built it (subagents per rule family, task summaries), GitHub Action for every release.
