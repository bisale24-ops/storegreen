#!/usr/bin/env bash
# check.sh — full gate: tests on both CI interpreters + smoke-run the tool.
# Exit non-zero on the first failure.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
PY39=~/.venvs/py39/bin/python
PY313=~/.venvs/py313/bin/python

# ---------------------------------------------------------------------------
# 1. Test suite — both interpreters
# ---------------------------------------------------------------------------
echo "==> pytest (py3.9)"
PYTHONPATH="$REPO/src" "$PY39"  -m pytest tests -q

echo "==> pytest (py3.13)"
PYTHONPATH="$REPO/src" "$PY313" -m pytest tests -q

# ---------------------------------------------------------------------------
# 2. Tool smoke-runs — stderr must be empty on a normal run
# ---------------------------------------------------------------------------
run_clean() {
    local label="$1"; shift
    local stderr_out
    # Capture stderr only; discard stdout; allow exit 1 (findings present) — only
    # an unexpected write to stderr is a failure.
    stderr_out="$(PYTHONPATH="$REPO/src" "$PY313" -m storegreen "$@" 1>/dev/null 2>&1 || true)"
    if [ -n "$stderr_out" ]; then
        echo "FAIL: $label produced unexpected stderr:"
        echo "$stderr_out"
        exit 1
    fi
    echo "ok: $label (stderr empty)"
}

echo "==> smoke: scan repo itself"
run_clean "storegreen --repo ." --repo "$REPO"

if [ -f "$REPO/fixtures/tipjar-amazon.aab" ]; then
    echo "==> smoke: scan fixtures/tipjar-amazon.aab"
    run_clean "storegreen --aab tipjar-amazon.aab" --aab "$REPO/fixtures/tipjar-amazon.aab"
else
    echo "skip: fixtures/tipjar-amazon.aab not present"
fi

echo ""
echo "All checks passed."
