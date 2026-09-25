# Setup state, checked 24.09.2026 22:4x Bishkek

| Item | State |
|---|---|
| lablab registration | **approved** 12.09.2026 (mail "You've been approved") |
| Bob Shell | **installed**, `/opt/homebrew/bin/bob`, v2.0.4, headless `bob run` available |
| Bob IDE | **installed**, `/Applications/IBM Bob.app`, **v2.2.0** (checked in Settings 25.09 20:52; requirement is ≥ 2.0.2) |
| Bob IDE bundled CLI | `/Applications/IBM Bob.app/Contents/Resources/app/bin/bobide` — opens a folder in the IDE |
| IBMid | his to confirm by logging into Bob |
| Hackathon account `ibm-coding-challenge-uat` (us-east) | invite arrives at kick-off; must be selected in Settings |

Bob IDE is a VS Code fork, so the workspace concept is the ordinary one and I can open the project
folder for him with `bobide <path>` — I still cannot type into it, which is why the prompts in
`PROMPTS.md` are written to be pasted.

## Remaining before 21:00 on 25.09

1. He signs into Bob IDE with the IBMid on `bisale24@gmail.com`.
2. At kick-off, accept the invite to `ibm-hackathon-xxxx` and switch the account in
   **Settings → General** to `ibm-coding-challenge-uat`, region `us-east`, before the first task —
   otherwise personal Bobcoins are spent instead of the free 40.
3. First command of the event, before anything is built: `bob --version` and a look at the Bobcoin
   balance, so we know what the budget actually is rather than assuming 40.

## Checked again 25.09.2026 18:0x, three hours before kick-off

- **IBMid exists.** Google's own notice, 24.09 22:09 Bishkek: signed in to "IBMid Prod" with
  bisale24@gmail.com. Nothing to create; the hackathon account invite is the only thing that
  waits, and the guide says it arrives at the start ("check your spam, search *IBM Bob*").
- **lablab team exists at last:** lablab.ai/ai-hackathons/ibm-bob-2-hackathon/khlab, Closed, UTC+6.
  Before it, "Submit Project" pointed at `/undefined/submission` — the CrewVoice blocker again.
- **Bob Shell 2.0.4**, `/opt/homebrew/bin/bob`; no credentials on disk yet (`~/.bob/` holds only
  settings), so the first login really is his, at kick-off. **Bob IDE 2.1.0.**
- **The deck builder runs**, but *not* on the system python: `playwright` lives in the video venv.
  Use `~/.venvs/video/bin/python build.py --draft`. It rendered the 10-slide draft PDF and the
  cover, with 11 TODO markers still visible. Found now rather than at 14:00 on Sunday.
- Deadline confirmed by the platform: **27.09 21:00 Bishkek** (15:00 UTC). 15 725 registered,
  3 113 teams.

## The first five minutes at 21:00

```bash
mkdir -p ~/Desktop/KHLab/storegreen && cd ~/Desktop/KHLab/storegreen
git init && mkdir -p bob_sessions prep runs
cp -R ~/Desktop/KHLab/ibm-bob-hackathon/prep/. prep/
"/Applications/IBM Bob.app/Contents/Resources/app/bin/bobide" ~/Desktop/KHLab/storegreen
```

`bobide` is **not on PATH** — checked, it is not; use the full path above, or just open the folder
from the IDE's File menu. Worth knowing at 21:05 rather than discovering it then.

`bob_sessions/` is created empty on purpose: it is the required deliverable, and an empty folder
in the tree is a standing reminder to screenshot after every task.


## Confirmed in the IDE at 20:52 on 25.09, before the start

Bob Settings → General, read directly: account `bisale24@gmail.com`, plan **enterprise**, add-ons
"allocated by your admin", **budget 40.00 (100% remaining)**, usage 0.0000. Forty is exactly the
hackathon allocation, and there is no personal Bob account to confuse it with — `~/.bob/` held no
credentials earlier today. **Nothing to switch.** The blue `100%` badge in the Bob panel is the
same budget indicator.

The org name and region are not shown on that page, so the conclusion rests on the plan type, the
exact budget and the zero usage rather than on seeing `ibm-coding-challenge-uat` written down.
