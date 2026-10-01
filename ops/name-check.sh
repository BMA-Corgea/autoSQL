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
#   --commits [<base>..<tip>]   check every commit a push would send: added lines AND commit
#              messages (both are published). Default range: @{u}..HEAD, else origin/main..HEAD.
#              T-53: the tree can be clean while history carries the name (added in one unpushed
#              commit, removed in the next). The landing protocol runs both:
#                  ops/name-check.sh && ops/name-check.sh --commits origin/main..HEAD && git push …
#
# EXIT CODES. 0: looked, and the name is not there. 1: the name is there (REFUSING).
#   2: COULD NOT TELL: not at the top of a git work tree (outside any, or inside one that is not this
#      script's own checkout), git missing or failing, git reporting an error, or an unexpected
#      argument. Never "clean".
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
range=""
case "$mode" in
  tree|--staged) [ "$#" -le 1 ] || could_not_tell "unexpected arguments: $* (pass nothing, --staged, or --commits [range])" ;;
  --commits) [ "$#" -le 2 ] || could_not_tell "unexpected arguments: $* (--commits takes one optional range)"; range="${2:-}" ;;
  *) could_not_tell "unknown argument '$mode' (pass nothing, --staged, or --commits [range])" ;;
esac
[ "$(git rev-parse --is-inside-work-tree 2>/dev/null)" = "true" ] \
  || could_not_tell "$(pwd) is not inside a git work tree, or git is not available"
[ -z "$(git rev-parse --show-prefix 2>/dev/null)" ] \
  || could_not_tell "$(pwd) is inside some work tree but is not its top level, so this is not its checkout"

# Each step's status is taken on its own, and git's stderr counts too: git grep exits 1 ("no
# match") even when it could not read a tracked file. Tree mode searches the work tree AND the
# index (what a commit sends), so a tracked file that is unreadable, deleted locally, or outside a
# sparse checkout is still searched. --staged reads the diff with every user setting that can hide
# a line turned off (colour, an external diff tool, textconv, binary detection).
if [ "$mode" = "--commits" ]; then
  if [ -z "$range" ]; then
    if up="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)" && [ -n "$up" ]; then range="$up..HEAD"
    elif git rev-parse --verify -q 'origin/main^{commit}' >/dev/null; then range="origin/main..HEAD"
    else could_not_tell "no upstream and no origin/main to compare HEAD with (pass --commits <base>..<tip>)"; fi
  fi
  case "$range" in *..*) ;; *) could_not_tell "'$range' is not a range (<base>..<tip>)" ;; esac
  for end in "${range%%..*}" "${range##*..}"; do
    git rev-parse --verify -q "${end:-HEAD}^{commit}" >/dev/null || could_not_tell "'$end' in '$range' names no commit"
  done
  commits="$(git rev-list "$range")" || could_not_tell "git rev-list $range failed"
  hits=""
  for c in $commits; do
    title="$(git log -1 --format='%h %s' "$c" | cut -c1-80)" || could_not_tell "git log $c failed"
    msg="$(git log -1 --format=%B "$c")" || could_not_tell "git log $c failed"
    in_msg="$(printf '%s\n' "$msg" | grep -inE "$NAMES")"; rc=$?
    [ "$rc" -le 1 ] || could_not_tell "grep failed on the message of $c"
    diff="$(git show --no-color --no-ext-diff --no-textconv --text --format= -U0 "$c")" || could_not_tell "git show $c failed"
    in_diff="$(printf '%s\n' "$diff" | grep -inE "^\+.*$NAMES")"; rc=$?
    [ "$rc" -le 1 ] || could_not_tell "grep failed on the diff of $c"
    [ -n "$in_msg" ] && hits="$hits${hits:+$'\n'}commit $title, in its MESSAGE:"$'\n'"$in_msg"
    [ -n "$in_diff" ] && hits="$hits${hits:+$'\n'}commit $title, in its DIFF:"$'\n'"$in_diff"
  done
  where="the commits in $range ($(printf '%s\n' "$commits" | grep -c .) commit(s))"
elif [ "$mode" = "--staged" ]; then
  staged="$(git diff --cached --no-color --no-ext-diff --no-textconv --text -U0)" || could_not_tell "git diff --cached failed"
  hits="$(printf '%s\n' "$staged" | grep -inE "^\+.*$NAMES")"; rc=$?
  [ "$rc" -le 1 ] || could_not_tell "grep failed on the staged diff (exit $rc)"
  where="the staged diff"
else
  errf="$(mktemp)" || could_not_tell "mktemp failed"
  wt="$(git grep -inE "$NAMES" -- . 2>"$errf")"; rc1=$?
  ix="$(git grep --cached -inE "$NAMES" -- . 2>>"$errf")"; rc2=$?
  err="$(cat "$errf")"; rm -f "$errf"
  hits="$wt${wt:+${ix:+$'\n'}}$ix"
  if [ -z "$hits" ]; then
    { [ "$rc1" -le 1 ] && [ "$rc2" -le 1 ]; } || could_not_tell "git grep failed (exit $rc1/$rc2)"
    [ -z "$err" ] || could_not_tell "git grep reported: ${err%%$'\n'*}"
  fi
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
