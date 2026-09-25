"""Run the tool over every adversarial input and fail on anything that is not a clean answer.

    python3 prep/crash-hunt.py ./run.sh
    python3 prep/crash-hunt.py --corpus /tmp/corpus -- ./run.sh --strict

A run is acceptable when it exits 0 or 1 (clean / findings), writes nothing to stderr, does not
print a traceback, finishes inside the timeout, and — in JSON mode — prints JSON that parses.
Anything else is a crash we hand back rather than ship. Written before the event so it is ready
the moment Bob's first version exists.
"""
import argparse
import json
import pathlib
import subprocess
import sys
import time

FORMS = [([], "plain"), (["--json"], "json"), (["--quiet"], "quiet")]


def run_one(command, repo, form, timeout, html_dir=None):
    args = list(command) + ["--repo", str(repo)] + form
    if html_dir is not None:
        args += ["--html", str(html_dir / ("%s.html" % repo.name))]
    started = time.time()
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return ["did not finish within %ss" % timeout], time.time() - started
    except OSError as error:
        return ["could not be started: %s" % error], time.time() - started
    problems = []
    if done.returncode not in (0, 1):
        problems.append("exit %s" % done.returncode)
    if done.stderr.strip():
        problems.append("stderr: %s" % done.stderr.strip().splitlines()[0][:120])
    if "Traceback (most recent call last)" in (done.stdout + done.stderr):
        problems.append("traceback")
    if "--json" in form and done.stdout.strip():
        try:
            json.loads(done.stdout)
        except ValueError as error:
            problems.append("stdout is not JSON: %s" % error)
    return problems, time.time() - started


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default="/tmp/storegreen-corpus")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--html", action="store_true", help="also exercise the HTML writer")
    parser.add_argument("--limit", type=int, default=0,
                        help="only the first N inputs — for a fast self-test, never for acceptance")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="the tool, e.g. ./run.sh  (put it after --)")
    args = parser.parse_args(argv)
    command = [a for a in args.command if a != "--"]
    if not command:
        parser.error("give the command to run, e.g. crash-hunt.py ./run.sh")

    corpus = pathlib.Path(args.corpus)
    cases = sorted(p for p in corpus.iterdir() if p.is_dir()) if corpus.is_dir() else []
    if not cases:
        print("no corpus at %s — run prep/crash-corpus.py first" % corpus, file=sys.stderr)
        return 2

    html_dir = None
    if args.html:
        html_dir = corpus / "_html"
        html_dir.mkdir(exist_ok=True)

    if args.limit:
        cases = cases[:args.limit]
    bad, checked, slowest = [], 0, (0.0, "")
    for repo in cases:
        if repo.name.startswith("_"):
            continue
        for form, label in FORMS:
            problems, seconds = run_one(command, repo, form, args.timeout,
                                        html_dir if (args.html and label == "plain") else None)
            checked += 1
            if seconds > slowest[0]:
                slowest = (seconds, "%s [%s]" % (repo.name, label))
            for problem in problems:
                bad.append("%-24s %-6s %s" % (repo.name, label, problem))
                print("CRASH  %-24s %-6s %s" % (repo.name, label, problem))
    print()
    print("%d runs over %d inputs, %d bad" % (checked, len(cases), len(bad)))
    print("slowest: %s at %.1fs" % (slowest[1], slowest[0]))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
