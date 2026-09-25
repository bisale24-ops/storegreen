"""Run StoreGreen over every cloned public repository and report what it found, honestly.

    PYTHONPATH=src ~/.venvs/py313/bin/python demo/scan.py /tmp/androidcorpus

Prints one line per repository and a summary. The summary is the number that goes in the
submission, so it counts four things separately and never rolls them together: repositories where
something is genuinely broken, repositories that came back clean, repositories where the tool
could not decide, and repositories that crashed it — because a crash is a defect in us, not a
finding about them.
"""
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]


def scan(repo, timeout=90):
    started = time.time()
    try:
        done = subprocess.run(
            [sys.executable, "-m", "storegreen", "--repo", str(repo), "--json"],
            capture_output=True, text=True, timeout=timeout,
            env=dict(__import__("os").environ, PYTHONPATH=str(ROOT / "src")))
    except subprocess.TimeoutExpired:
        return {"state": "timeout", "seconds": timeout}
    seconds = time.time() - started
    if done.returncode not in (0, 1):
        return {"state": "crash", "detail": (done.stderr or done.stdout)[-300:], "seconds": seconds}
    if done.stderr.strip():
        return {"state": "crash", "detail": "wrote to stderr: " + done.stderr.strip()[:200],
                "seconds": seconds}
    try:
        payload = json.loads(done.stdout)
    except ValueError as error:
        return {"state": "crash", "detail": "output is not JSON: %s" % error, "seconds": seconds}
    summary = payload.get("summary", {})
    payload["state"] = ("findings" if summary.get("block") or summary.get("risk")
                        else ("undecided" if summary.get("undecidable") else "clean"))
    payload["seconds"] = seconds
    return payload


def main(where):
    repos = sorted(p for p in pathlib.Path(where).iterdir()
                   if p.is_dir() and not p.name.startswith("."))
    tally, rows = {}, []
    for repo in repos:
        result = scan(repo)
        state = result["state"]
        tally[state] = tally.get(state, 0) + 1
        summary = result.get("summary", {})
        rows.append((repo.name, state, summary))
        print("%-9s %-46s %s" % (
            state, repo.name[:46],
            "" if state in ("crash", "timeout")
            else "block=%s risk=%s undecidable=%s passed=%s  %.2fs" % (
                summary.get("block", 0), summary.get("risk", 0),
                summary.get("undecidable", 0), summary.get("passed", 0), result["seconds"])))
        if state in ("crash", "timeout"):
            print("          %s" % result.get("detail", "")[:200])
    print()
    print("%d repositories: %s" % (len(repos), ", ".join(
        "%d %s" % (n, k) for k, n in sorted(tally.items()))))
    blocks = sum(r[2].get("block", 0) for r in rows)
    risks = sum(r[2].get("risk", 0) for r in rows)
    print("%d BLOCK findings, %d RISK findings" % (blocks, risks))
    print("crashes are ours, not theirs: %d" % (tally.get("crash", 0) + tally.get("timeout", 0)))
    return 1 if tally.get("crash") or tally.get("timeout") else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/androidcorpus"))
