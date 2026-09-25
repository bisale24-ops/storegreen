#!/usr/bin/env bash
# run.sh — run storegreen without installing it
# Usage: ./run.sh [--repo PATH] [--aab FILE] [OPTIONS]
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHONPATH="${SCRIPT_DIR}/src" python3 -m storegreen "$@"
