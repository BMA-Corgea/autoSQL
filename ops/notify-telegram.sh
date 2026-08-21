#!/usr/bin/env bash
# notify-telegram.sh — drain AutoDev's outbox to the Telegram path Evan already has.
#
# WHY THIS FILE EXISTS
#   AutoDev ships two REAL notification transports (console, file) and two ADAPTER
#   SLOTS ("slack", "telegram") that fail closed — see
#   plugin scripts/notify.mjs → createTransports(). The slots can only be filled
#   in-process via createTransports({extraAdapters}); there is NO config key that
#   gives AutoDev a Telegram credential, and declaring "telegram" in notify.json
#   makes every send fail with "adapter slot — connect it during onboarding".
#   The documented seam is the file transport: notify.mjs drops one packet per
#   occurrence at .autodev/outbox/<key>.md and says, verbatim, "any channel bridge
#   (or the human) can pick outbox files up". This IS that channel bridge.
#
# WHAT IT SENDS THROUGH
#   `openclaw message send` — the same CLI the GUTS bridge's src/notify.js already
#   uses to put Claude's questions on Evan's phone. Nothing new is authenticated:
#   the Telegram bot token lives in openclaw's own store (~/.openclaw, mode 0600)
#   and is never read, copied or printed by this script.
#
# SECRETS
#   The recipient chat id is never echoed. It is resolved at send time from, in order:
#     1. $AUTODEV_NOTIFY_TARGET
#     2. BRIDGE_NOTIFY_TARGET inside the file named by .autodev/notify-telegram.json
#        → "target_file_candidates" (tried in order; the GUTS bridge .env holds it)
#   Nothing is copied into this repo. If neither resolves, the script fails closed
#   and says which one to set — it never sends to a guessed recipient.
#
# USAGE
#   ops/notify-telegram.sh              # drain the outbox (idempotent; safe to re-run)
#   ops/notify-telegram.sh --test       # send one test ping, prove the wiring
#   ops/notify-telegram.sh --dry-run    # show what WOULD be sent; sends nothing
#
# IDEMPOTENCE
#   A packet that sends is moved to .autodev/outbox/sent/ and never sent again.
#   A packet that fails STAYS in the outbox and is retried on the next run. (Note:
#   AutoDev's own .autodev/notify/sent.jsonl marks the occurrence "sent" as soon as
#   the FILE was written, so the outbox — not sent.jsonl — is the retry queue for
#   the Telegram leg.)
set -uo pipefail

ROOT="${AUTODEV_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OUTBOX="$ROOT/.autodev/outbox"
SENTDIR="$OUTBOX/sent"
CONF="$ROOT/.autodev/notify-telegram.json"
MAX_CHARS=3500          # Telegram REJECTS >4096 outright; leave room for the part marker.

# MODE is what to do; DRY is whether to actually send. They are SEPARATE on purpose:
# --dry-run must never be silently swallowed by another flag. (It was, on 2026-08-21, and
# a "dry run" delivered a real message.)
MODE="drain"
DRY=0
# Parse ALL arguments, not just the first. The original only inspected "$1", so
# `--test --dry-run` silently discarded --dry-run and sent for real.
while [ $# -gt 0 ]; do
  case "$1" in
    --test)    MODE="test" ;;
    --dry-run) DRY=1 ;;
    -h|--help) echo "usage: $(basename "$0") [--test] [--dry-run]"; exit 0 ;;
    "")        ;;
    *) echo "usage: $(basename "$0") [--test] [--dry-run]" >&2; exit 2 ;;
  esac
  shift
done

jqget() { [ -f "$CONF" ] && command -v jq >/dev/null 2>&1 && jq -r "$1 // empty" "$CONF" 2>/dev/null || true; }

CHANNEL="${AUTODEV_NOTIFY_CHANNEL:-$(jqget .channel)}"
CHANNEL="${CHANNEL:-telegram}"
BIN="${AUTODEV_NOTIFY_BIN:-$(jqget .bin)}"
BIN="${BIN:-openclaw}"

# ---- recipient, resolved but never printed -------------------------------
TARGET="${AUTODEV_NOTIFY_TARGET:-}"
TARGET_SRC="\$AUTODEV_NOTIFY_TARGET"
if [ -z "$TARGET" ]; then
  TVAR="$(jqget .target_var)"; TVAR="${TVAR:-BRIDGE_NOTIFY_TARGET}"
  # Candidates are tried in order; the first readable one wins. This is a LIST rather than a
  # single path so the same config resolves on Linux and on the Windows machine (Evan runs both).
  CANDS="$(jq -r '.target_file_candidates[]? // empty' "$CONF" 2>/dev/null)"
  [ -n "$CANDS" ] || CANDS="/home/corgea/Desktop/Coding Projects/GUTS/spine/L0-runtime/guts-bridge/.env"
  while IFS= read -r RAW; do
    [ -n "$RAW" ] || continue
    TFILE="$(eval printf '%s' "\"$RAW\"" 2>/dev/null)"   # expand ${HOME} / ${USERPROFILE} / ${GUTS_BRIDGE_ENV}
    case "$TFILE" in *'${'*|'') continue ;; esac          # unset variable -> skip this candidate
    if [ -r "$TFILE" ]; then
      TARGET="$(grep -m1 -E "^${TVAR}=" "$TFILE" | cut -d= -f2- | tr -d '"'"'"'' | tr -d '\r' | xargs)"
      [ -n "$TARGET" ] && { TARGET_SRC="${TVAR} in ${TFILE}"; break; }
    fi
  done <<EOF
$CANDS
EOF
fi
if [ -z "$TARGET" ]; then
  echo "notify-telegram: FAIL CLOSED — no recipient." >&2
  echo "  Set AUTODEV_NOTIFY_TARGET=<your telegram chat id>, or point" >&2
  echo "  $CONF → target_file_candidates at a file holding BRIDGE_NOTIFY_TARGET." >&2
  echo "  Nothing was sent. (No chat id is stored in this repo, by design.)" >&2
  exit 1
fi

command -v "$BIN" >/dev/null 2>&1 || { echo "notify-telegram: '$BIN' not on PATH — nothing sent." >&2; exit 1; }

# ---- send one body, chunked if long -------------------------------------
send_body() {
  local body="$1" label="$2" rc=0 n i chunk
  n=$(( (${#body} + MAX_CHARS - 1) / MAX_CHARS )); [ "$n" -lt 1 ] && n=1
  for (( i=1; i<=n; i++ )); do
    chunk="${body:$(( (i-1) * MAX_CHARS )):$MAX_CHARS}"
    [ "$n" -gt 1 ] && chunk="($i/$n)
$chunk"
    if [ "$DRY" = "1" ]; then
      echo "--- would send part $i/$n to channel=$CHANNEL target=<redacted; from $TARGET_SRC> ---"
      printf '%s\n' "$chunk"
      continue
    fi
    # Body is passed as ONE argv element, never through a shell — same doctrine as
    # the GUTS bridge: packet text is untrusted and must stay inert bytes.
    # openclaw's own output can echo the chat id, so it is swallowed, not printed.
    if ! "$BIN" message send --channel "$CHANNEL" --target "$TARGET" --message "$chunk" >/dev/null 2>&1; then
      rc=1; break
    fi
  done
  if [ "$rc" -eq 0 ]; then
    if [ "$DRY" = "1" ]; then echo "would send: $label ($n part(s)) → $CHANNEL"; else echo "sent: $label ($n part(s)) → $CHANNEL"; fi
  else echo "FAILED: $label → $CHANNEL (left in outbox; retried next run)" >&2; fi
  return "$rc"
}

if [ "$MODE" = "test" ]; then
  send_body "[AutoDev] test ping from the autoSQL shop.

This is the wiring test for gate-hold notifications: when a ticket stops and
waits on you, the decision packet will arrive here, in this chat.

Nothing is waiting on you right now." "test ping"
  exit $?
fi

# ---- drain ---------------------------------------------------------------
shopt -s nullglob
files=( "$OUTBOX"/*.md )
if [ ${#files[@]} -eq 0 ]; then echo "notify-telegram: outbox empty — nothing to send."; exit 0; fi
[ "$DRY" = "1" ] || mkdir -p "$SENTDIR"
fail=0
for f in "${files[@]}"; do
  if send_body "$(cat "$f")" "$(basename "$f")"; then
    [ "$DRY" = "1" ] || mv "$f" "$SENTDIR/"
  else
    fail=1
  fi
done
exit "$fail"
