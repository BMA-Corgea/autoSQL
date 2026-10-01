#!/usr/bin/env bash
# ops/checks/neighbour-ports.sh — proves the demo disturbs nothing else on
# this machine (T-2-plan.md W4; spec §11.2, AC-4).
#
# WHY THIS LIVES HERE AND NOT IN demo/
#   "The demo tree" (T-2.md §11.1) is `demo/` plus `./run-demo`, nothing
#   else — and AC-3's grep test forbids the string `55433` (the owner's LIVE
#   database, glp-strong-db) anywhere inside that tree. This check's whole
#   job is to name port numbers and watch them, so it has to live outside
#   the tree it would otherwise be caught by its own neighbour's rule. It is
#   deliberately NOT run by `./run-demo test` (AC-4).
#
# WHAT IT DOES
#   0. Takes `./run-demo`'s host-wide lock for the demo stack (T-62) and
#      holds it to the end, then refuses to go on if the demo's container or
#      its volume already exists (defect (3) below).
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
# EXIT CODES
#   0  PASS — nothing outside 55440/8787 vanished or changed.
#   1  FAIL — something did; listed by port number.
#   2  COULD NOT TELL — no verdict either way: a snapshot could not be
#      taken, the demo stack was already here, the lock could not be had, or
#      the cycle itself failed. Never read it as a PASS.
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
# TWO MORE FIXED 2026-10-01 (T-55), both of the opposite kind: the check
# could destroy what it stood on, or say PASS without having looked.
#
#   (3) The cycle's `./run-demo down` is `docker compose down --volumes`: it
#       removes the demo's container AND its named volume. Over a demo stack
#       somebody had kept — stopped, its database on that volume — the
#       cycle started it, then deleted it, data and all, on the way out. It
#       now refuses (exit 2, nothing touched) when the container or the
#       volume that demo/compose.yaml names exists before the cycle, so
#       everything the cycle removes, the cycle created. That look is made
#       under run-demo's lock, held through the last snapshot, so no
#       `./run-demo` (`test`, `up` and `down` all take it) can create, start
#       or tear down the stack in between.
#
#   (4) Each snapshot command ended in `|| true`, so a `docker ps` that
#       failed, or an `ss` that was missing or failed, gave an EMPTY half —
#       and two empty halves compare clean: PASS, from a check that had
#       looked at nothing. Each command's status is now read on its own,
#       and a snapshot that could not be taken is exit 2, never a PASS. The
#       comparison's two `comm`s had the same `|| true`, and lost it too.
#
#   It asserts on port numbers, never on a container name — which is what
#   lets this check and AC-3's forbidden-string grep both hold at once
#   (locate §11.2). (Defect (3)'s refusal reads the demo's OWN names from
#   demo/compose.yaml; it names no other container.)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_DEMO="$REPO_ROOT/run-demo"
COMPOSE_FILE="$REPO_ROOT/demo/compose.yaml"
DEMO_PORTS_PATTERN=':(55440|8787)'

# Exit 2: this run has no verdict, and says so rather than print one.
could_not_tell() {
  echo "neighbour-ports: COULD NOT TELL — $*" >&2
  exit 2
}

# Is $1 one whole line of $2?  (run-demo's own test, for the same reasons.)
is_line_of() {
  [[ $'\n'"$2"$'\n' == *$'\n'"$1"$'\n'* ]]
}

# One snapshot, sorted. Defect (4): each command's exit status is read on its
# own, and a half that could not be read returns 1, naming the command —
# never an empty half that compares clean.
snapshot() {
  local containers listeners
  if ! containers="$(docker ps --format $'{{.ID}}\t{{.Ports}}\t{{.State}}')"; then
    echo "neighbour-ports: \`docker ps\` failed — the containers could not be seen" >&2
    return 1
  fi
  if ! command -v ss >/dev/null 2>&1; then
    echo "neighbour-ports: \`ss\` is not installed (iproute2) — the listeners could not be seen" >&2
    return 1
  fi
  if ! listeners="$(ss -ltn)"; then
    echo "neighbour-ports: \`ss -ltn\` failed — the listeners could not be seen" >&2
    return 1
  fi
  if [[ "$listeners" != State* ]]; then
    echo "neighbour-ports: \`ss -ltn\` printed no header, so what it printed is not its listing" >&2
    return 1
  fi
  {
    printf '%s\n' "$containers" | awk -v demo="${DEMO_PORTS_PATTERN}->" 'NF && $0 !~ demo'
    printf '%s\n' "$listeners" | awk -v demo="${DEMO_PORTS_PATTERN}\$" 'NR > 1 && $4 !~ demo {print $4}'
  } | sort
}

# Defect (3): the demo stack's own names, from the file that creates it —
# one "container <name>" or "volume <name>" per line.
demo_stack() {
  docker compose -f "$COMPOSE_FILE" config --format json | python3 -c '
import json
import sys

cfg = json.load(sys.stdin)
for service in (cfg.get("services") or {}).values():
    print("container", service.get("container_name") or "")
for key, spec in (cfg.get("volumes") or {}).items():
    print("volume", (spec or {}).get("name") or key)
'
}

stack="$(demo_stack)" \
  || could_not_tell "could not read the demo stack's names from demo/compose.yaml (\`docker compose config\`); nothing was cycled"
demo_containers=()
demo_volumes=()
while read -r kind name; do
  [[ -n "$kind" ]] || continue
  [[ -n "$name" ]] \
    || could_not_tell "a service in demo/compose.yaml has no container_name, so this run cannot look for it; nothing was cycled"
  case "$kind" in
    container) demo_containers+=("$name") ;;
    volume) demo_volumes+=("$name") ;;
  esac
done < <(printf '%s\n' "$stack")
[[ ${#demo_containers[@]} -eq 1 ]] \
  || could_not_tell "demo/compose.yaml names ${#demo_containers[@]} containers, not the one ./run-demo is built around; nothing was cycled"
DEMO_CONTAINER="${demo_containers[0]}"

# Defect (3), the window: run-demo's own host-wide lock (T-62), held from the
# look below to the last snapshot. The run-demo this check calls is told it
# is held (RUN_DEMO_LOCK_HELD), as run-demo tells its own children, or it
# would wait on its parent. An inherited RUN_DEMO_LOCK_HELD is NOT honoured
# here: nothing that holds the lock runs this check (AC-4 keeps it out of
# `./run-demo test`), and a stale export must not let it in unlocked. An flock
# on a descriptor this shell holds, so the kernel lets go on any exit.
LOCKFILE="/tmp/run-demo.${DEMO_CONTAINER}.lock"
command -v flock >/dev/null 2>&1 \
  || could_not_tell "flock (util-linux) is not installed, so no run-demo could be kept out of the cycle; nothing was cycled"
if [[ ! -e "$LOCKFILE" ]]; then
  ( umask 000; : >>"$LOCKFILE" ) 2>/dev/null || true
fi
exec {LOCK_FD}<"$LOCKFILE" \
  || could_not_tell "could not open the lock file $LOCKFILE; nothing was cycled"
if ! flock -n "$LOCK_FD"; then
  echo "neighbour-ports: a run-demo is working on $DEMO_CONTAINER ($LOCKFILE) — waiting for it to finish (up to 30 minutes)"
  flock -w 1800 "$LOCK_FD" \
    || could_not_tell "$LOCKFILE was still locked after 30 minutes; nothing was cycled"
fi
export RUN_DEMO_LOCK_HELD="$DEMO_CONTAINER"
echo "neighbour-ports: holding the host-wide lock for $DEMO_CONTAINER ($LOCKFILE)"

# Defect (3): refuse where the stack already exists, so that nothing the
# cycle's `down` removes was here before it.
containers_now="$(docker ps -a --format '{{.Names}}')" \
  || could_not_tell "\`docker ps -a\` failed, so this run could not tell whether $DEMO_CONTAINER exists; nothing was cycled"
volumes_now="$(docker volume ls -q)" \
  || could_not_tell "\`docker volume ls\` failed, so this run could not tell whether the demo's volume exists; nothing was cycled"
found=()
for name in "${demo_containers[@]}"; do
  if is_line_of "$name" "$containers_now"; then found+=("container $name"); fi
done
for name in "${demo_volumes[@]}"; do
  if is_line_of "$name" "$volumes_now"; then found+=("volume $name"); fi
done
if [[ ${#found[@]} -gt 0 ]]; then
  echo "neighbour-ports: COULD NOT RUN SAFELY — the demo stack is already here: ${found[*]}." >&2
  echo "neighbour-ports: the cycle's \`./run-demo down\` removes the container AND its volume, so it would delete what was kept. Nothing was touched." >&2
  echo "neighbour-ports: run this check where the demo stack is absent (\`./run-demo down\` first only if that stack's data is disposable)." >&2
  exit 2
fi

echo "neighbour-ports: snapshotting every listener but 55440/8787, before the cycle"
before="$(snapshot)" \
  || could_not_tell "the snapshot before the cycle could not be taken; nothing was cycled"

# The lock's descriptor is closed for run-demo: it is told the lock is held,
# and nothing it starts (the app, above all) may hold the lock past this check.
echo "neighbour-ports: running ./run-demo up"
"$RUN_DEMO" up {LOCK_FD}>&- \
  || could_not_tell "./run-demo up failed (exit $?), so there was no cycle to judge. Nothing of the demo stack existed before it (looked under the lock), so \`./run-demo down\` removes only what it started"

echo "neighbour-ports: running ./run-demo down"
"$RUN_DEMO" down {LOCK_FD}>&- \
  || could_not_tell "./run-demo down failed (exit $?), so the cycle did not complete; see its output above"

echo "neighbour-ports: snapshotting again, after the cycle"
after="$(snapshot)" \
  || could_not_tell "the snapshot after the cycle could not be taken"

# Nothing that was there before may have vanished or changed. Anything NEW is
# someone else's business — see defect (1) above.
vanished="$(comm -23 <(echo "$before") <(echo "$after"))" \
  || could_not_tell "comm failed comparing the two snapshots"
appeared="$(comm -13 <(echo "$before") <(echo "$after"))" \
  || could_not_tell "comm failed comparing the two snapshots"

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
