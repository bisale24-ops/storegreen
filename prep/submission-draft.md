# Submission draft (lablab form fields)

Final numbers (findings, minutes saved) get filled in on Sunday from real runs — no invented metrics.

## Project title
StoreGreen — catch store rejections before you submit

## Short description (≤ 255 chars)
StoreGreen scans an Android repo against Amazon Appstore and Google Play rules and tells you why the store would
reject the build — with file and line evidence — then lets IBM Bob apply the fixes. Built with IBM Bob 2.0.

## Long description (outline)
1. **Problem.** A store rejection costs a resubmit and days in the review queue. Most rejections are mechanical:
   a missing IAP key, a manifest receiver, an outdated target API. Emulators don't catch them — a failed purchase
   on a device without the store looks normal.
2. **Our own case.** Real Amazon rejection "IAP displays error" on our CrewSheet app, 11.09.2026, fixed after
   the fact. StoreGreen flags all causes of that rejection statically.
3. **What it does.** Rule catalog (Amazon IAP, Play platform deadlines of 31.08.2026, Play policy signals,
   cross-store), evidence per finding, verdict READY / RISK / REJECT, `--fix` via IBM Bob agent mode, GitHub Action.
4. **How IBM Bob 2.0 built it.** Plan mode for architecture from the rules spec; parallel subagents, one per rule
   family; agent mode for fixes; document understanding to map a pasted rejection e-mail to rule IDs.
   Task summaries in `bob-reports/`.
5. **Impact.** Before/after runs on fixtures and 2 open-source apps (numbers from real runs).
6. **What's next.** More stores (Galaxy, Huawei AppGallery), iOS App Store Review Guidelines.

## Tags
IBM Bob, Android, DevOps, Release engineering, Developer tools

## Slides (8)
1. Title + one-line promise
2. The rejection e-mail (real) + cost in days
3. Why emulators and linters miss it
4. How it works: rules catalog → evidence → verdict → Bob fixes
5. Demo screenshots: red report → green report
6. How IBM Bob built it (modes, subagents, task summary screenshot)
7. Impact numbers from real runs
8. Roadmap + repo link

## Cover image
Split frame: left — red "REJECTED" stamp over an app listing; right — green "READY TO SUBMIT" report. KHLab logo small.

## Video (≤ 3 min) — follows "Demo story" in build-plan.md

## After Submit — not optional

The 20 × $100 are a **random draw**, not a payment: lablab's own words are "you're in the draw,
twenty winners, picked at random", among everyone who both submitted a qualified project **and**
completed the post-hackathon feedback form. The denominator is the number of submitters, which is
unknown until the deadline passes. So this is a free ticket taken on the way past — never a number
to plan around. It costs ten minutes and it is the thing that gets forgotten at midnight on Sunday.

- [ ] Submit the project on lablab (team KHLab).
- [ ] Screenshot the submitted state.
- [ ] **Find and complete the feedback form.** It is not on the team page: it arrives by e-mail
      from `no-reply@lablab.ai` after submissions close, and is usually also posted in the
      hackathon Discord and in the event's Updates. If it has not arrived within an hour of the
      deadline, ask in Discord rather than waiting.
- [ ] Screenshot the completed form too, so there is proof if the draw is disputed.
- [ ] Only then write the result into memory.
