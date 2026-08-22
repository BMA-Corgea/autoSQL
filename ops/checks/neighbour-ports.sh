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
#        - `docker ps` (port mapping + container uptime string)
#        - `ss -ltn`   (every bound listen socket, container or not)
#      excluding only the demo's own two ports, 55440 and 8787.
#   2. Runs a full `./run-demo up` then `./run-demo down` cycle.
#   3. Snapshots again the same way.
#   4. Diffs the two snapshots. Any difference — a new listener, a missing
#      one, a changed port mapping, or a container whose uptime reset
#      (i.e. it got restarted) — is a FAIL, reported by port number only.
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
    docker ps --format '{{.Ports}}	{{.Status}}' | grep -v -E "${DEMO_PORTS_PATTERN}->" || true
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

if [[ "$before" == "$after" ]]; then
  echo "neighbour-ports: PASS — no change on any port but 55440/8787 across the up/down cycle"
  exit 0
else
  echo "neighbour-ports: FAIL — a listener outside 55440/8787 changed. Reported by port number; look up what is on it." >&2
  diff <(echo "$before") <(echo "$after") >&2 || true
  exit 1
fi
