#!/usr/bin/env bash
# ops/name-check.sh — T-14's rule, as a check that GATES rather than one that prints.
#
# T-14 took the owner's name out of this public repo. The rule since: check before any push.
#
# WHY THIS IS A SCRIPT AND NOT A GREP YOU TYPE. On 2026-09-08 a session ran the grep
# inline, it FIRED with two hits, and the push went ahead anyway — the command was chained
# `git grep … ; echo … && git add …`, so the grep's exit status gated nothing. The check
# ran, reported, and was ignored by its own harness. kb/wiki/lessons.md names that class:
# a check whose result nothing consumes is a check that did not run.
#
# This one EXITS NON-ZERO. Use it as the thing a push depends on:
#     ops/name-check.sh && git push
#
#   --staged   check what is about to be committed, not the whole tree
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# .autodev/ is gitignored and is where the true actor grammar belongs, so it is not scanned.
NAMES='\bevan\b'
mode="${1:-tree}"

if [ "$mode" = "--staged" ]; then
  hits="$(git diff --cached -U0 | grep -inE "^\+.*$NAMES" || true)"
  where="the staged diff"
else
  hits="$(git grep -inE "$NAMES" -- . || true)"
  where="the tracked tree"
fi

if [ -n "$hits" ]; then
  echo "name-check: REFUSING — the owner's name is in $where (T-14)." >&2
  echo "$hits" | sed 's/^/  /' >&2
  echo >&2
  echo "name-check: this repo is public. The actor grammar belongs in .autodev/ (gitignored)" >&2
  echo "name-check: and the ledger, not in tracked files. Use human:<his id> in examples." >&2
  exit 1
fi
echo "name-check: clean ($where)"
