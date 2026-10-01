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
#
# EXIT CODES. 0: looked, and the name is not there. 1: the name is there (REFUSING).
#   2: COULD NOT TELL: not inside a git work tree, or git itself failed. Never "clean".
#   Until T-47 there was no 2: `git grep … || true` folded git's own failure into "no hits",
#   so a copy of this script run outside a checkout, with the name planted beside it, printed
#   "clean" and exited 0. A check that could not look must never read as a check that passed.
set -uo pipefail
could_not_tell() {
  echo "name-check: COULD NOT TELL: $1. Nothing was checked, and this is not a pass (T-47)." >&2
  exit 2
}
cd "$(dirname "${BASH_SOURCE[0]}")/.." || could_not_tell "cannot enter the repository root"

# .autodev/ is gitignored and is where the true actor grammar belongs, so it is not scanned.
NAMES='\bevan\b'
mode="${1:-tree}"
case "$mode" in
  tree|--staged) ;;
  *) could_not_tell "unknown argument '$mode' (pass nothing, or --staged)" ;;
esac
[ "$(git rev-parse --is-inside-work-tree 2>/dev/null)" = "true" ] \
  || could_not_tell "$(pwd) is not inside a git work tree, or git is not available"

# Each step's status is taken on its own: git grep exits 0 on a match, 1 on none, and >1 when
# it failed; grep likewise. Only 0 and 1 are answers.
if [ "$mode" = "--staged" ]; then
  staged="$(git diff --cached -U0)" || could_not_tell "git diff --cached failed"
  hits="$(printf '%s\n' "$staged" | grep -inE "^\+.*$NAMES")"; rc=$?
  [ "$rc" -le 1 ] || could_not_tell "grep failed on the staged diff (exit $rc)"
  where="the staged diff"
else
  hits="$(git grep -inE "$NAMES" -- .)"; rc=$?
  [ "$rc" -le 1 ] || could_not_tell "git grep failed (exit $rc)"
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
