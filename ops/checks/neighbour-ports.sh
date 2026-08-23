#!/usr/bin/env bash
# ops/checks/neighbour-ports.sh — proves the demo disturbs nothing else on
# this machine (T-2-plan.md W4; spec §11.2, AC-4).
#
# WHY THIS LIVES HERE AND NOT IN demo/
#   "The demo tree" (T-2.md §11.1) is `demo/` plus `./run-demo`, nothing
#   else — and AC-3's grep test forbids the string `55433` (Evan's LIVE
#   database, glp-strong-db) anywhere inside that tree. This check's whole
#   job is to name port numbers and watch them, so it has to live outside
#   the tree it would otherwise be caught by its own neighbour's rule. It is
#   deliberately NOT run by `./run-demo test` (AC-4).
#
# WHAT IT DOES
#   1. Snapshots every TCP listener on this machine, in two forms:
#        - `docker ps` (container id + port mapping + state — NO clock)
#        - `ss -ltn`   (every bound listen socket, container or not)
#      excluding only the demo's own two ports, 55440 and 8787.
#   2. Runs a full `./run-demo up` then `./run-demo down` cycle.
#   3. Snapshots again the same way.
#   4. Asserts that every line present BEFORE is still present AFTER.
#      A vanished listener, a changed port mapping, or a container that
#      stopped is a FAIL, reported by port number only.
#
# TWO DEFECTS FIXED 2026-08-22, both found by measuring rather than reading
# (they were caught while producing AC-4's evidence, and both would have
# reported FAIL for something this demo did not do):
#
#   (1) It compared the two snapshots for exact set EQUALITY, so any
#       UNRELATED process that happened to start a listener during the
#       window failed the check. Measured: a `next-server` dev server
#       (pid 1216205) appeared on *:8724 mid-window, nothing to do with
#       this demo. A new neighbour is not this demo disturbing anything —
#       the meaningful assertion is that nothing present BEFORE vanished
#       or changed. Additions are now reported for information and do not
#       fail. This is a subset check, not an equality check.
#
#   (2) Its docker snapshot included `{{.Status}}`, which is the coarse
#       uptime STRING ("Up 7 hours"). Any cycle straddling an hour
#       boundary changed that string for a container nobody touched, and
#       failed. Replaced with `{{.ID}} {{.Ports}} {{.State}}` — all three
#       are clock-free. A container that is recreated changes its id; one
#       that stops changes its state; a remapped port changes its ports.
#       Those are the three things worth catching, and none of them ticks
#       on its own.
#
#   It asserts on port numbers, never on a container name — which is what
#   lets this check and AC-3's forbidden-string grep both hold at once
#   (locate §11.2).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_DEMO="$REPO_ROOT/run-demo"
DEMO_PORTS_PATTERN=':(55440|8787)'

snapshot() {
  {
    docker ps --format '{{.ID}}	{{.Ports}}	{{.State}}' | grep -v -E "${DEMO_PORTS_PATTERN}->" || true
    ss -ltn | awk 'NR>1 {print $4}' | grep -v -E "${DEMO_PORTS_PATTERN}\$" || true
  } | sort
}

echo "neighbour-ports: snapshotting every listener but 55440/8787, before the cycle"
before="$(snapshot)"

echo "neighbour-ports: running ./run-demo up"
"$RUN_DEMO" up

echo "neighbour-ports: running ./run-demo down"
"$RUN_DEMO" down

echo "neighbour-ports: snapshotting again, after the cycle"
after="$(snapshot)"

# Nothing that was there before may have vanished or changed. Anything NEW is
# someone else's business — see defect (1) above.
vanished="$(comm -23 <(echo "$before") <(echo "$after") || true)"
appeared="$(comm -13 <(echo "$before") <(echo "$after") || true)"

if [[ -n "$appeared" ]]; then
  echo "neighbour-ports: note — listeners APPEARED during the window. Not a failure:"
  echo "$appeared" | sed 's/^/    + /'
  echo "neighbour-ports: (this demo owns 55440 and 8787 only; anything else that starts"
  echo "neighbour-ports:  mid-window belongs to another process on this machine)"
fi

if [[ -z "$vanished" ]]; then
  echo "neighbour-ports: PASS — nothing outside 55440/8787 vanished or changed across the up/down cycle"
  exit 0
else
  echo "neighbour-ports: FAIL — a listener outside 55440/8787 VANISHED or CHANGED. Reported by port number; look up what is on it." >&2
  echo "$vanished" | sed 's/^/    - /' >&2
  exit 1
fi
