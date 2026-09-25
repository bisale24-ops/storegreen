# Who drives what during the 48 hours

## What I cannot do — revised 25.09 20:55, and the answer is: less than I thought

The assumption below was wrong and it shaped the whole plan. Access to Bob IDE was granted at full
tier, so I can click **and** type in it, and `screencapture -l <window_id> -x -o file.png` writes a
clean 2400×1560 PNG of the window straight into `bob_sessions/` without taking the screen over.

So the IDE is not his hands. I drive the whole loop: paste the task, wait, open Tasks, expand the
session consumption summary, save the screenshot. He decides things and presses Submit.

*(Previous assumption, kept because it explains the shape of the prompts: "I may see and click an
IDE window but not type into it, so the IDE is his hands, always.")*

## What I can do

**Bob Shell is a command line**, and it runs non-interactively — which means I drive it exactly
like any other CLI:

```bash
bob run "prompt"                                  # prompt as an argument
cat notes.md | bob run "summarise this"           # or piped
bob run "Review @src/rules.py"                    # @ references a file
bob run --format json "…" > result.json           # json or stream-json
bob run --max-cost 2 --max-turns 6 "…"            # hard cap in Bobcoins
bob run --accept-license --team-id <id> "…"       # for the hackathon account
```

`--max-cost` is the important one: with 40 Bobcoins for the whole event and no top-ups, every call
I make gets an explicit cap, and I log what each one spent.

## The split

| Work | Who |
|---|---|
| Bob IDE sessions, and the `bob_sessions` screenshots | me — full-tier access, verified |
| IBMid, installs, account switch to `ibm-coding-challenge-uat` | him |
| Architecture, code, tests, data, fixtures | me |
| Bob Shell calls, under an explicit `--max-cost` each | me |
| Video, README, submission text, feedback form draft | me |

## The trap to avoid

Bob IDE and Bob Shell draw on the **same 40 Bobcoins**. If I burn them from the terminal, he has
none left for the IDE sessions that are the required evidence. So: the IDE sessions come first and
get the budget; Bob Shell is for what genuinely needs it, capped, and only after the evidence
sessions are safe.
