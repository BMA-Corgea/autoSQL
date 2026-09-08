#!/usr/bin/env bash
# ops/run-tests.sh — the ops/ suite.
#
# `node --test ops/tests/` does NOT work on Node 22: it tries to load the directory as a
# module and dies with MODULE_NOT_FOUND. Test files must be named individually, which is
# exactly the sort of thing that gets a suite quietly stopped from running. This script is
# the one command to type, and it globs so a new test file is picked up without editing it.
#
# The repo's other suites are pytest (demo/, runtime/, compiler/); this covers ops/ only.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
shopt -s nullglob
files=(ops/tests/test_*.mjs)
if [ ${#files[@]} -eq 0 ]; then echo "ops: no test files found" >&2; exit 1; fi
echo "ops: running ${#files[@]} test file(s)"
exec node --test "${files[@]}"
