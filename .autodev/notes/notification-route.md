# How a stopped ticket reaches Evan

Answering Evan's Q35 — *"Send it to Slack or Telegram. Check what's going on in the
GUTS-bridge. I already get telegram messages when you have a question. You might be able
to print it into the terminal."*

He was right on both counts. The Telegram path already exists, and AutoDev already has a
console channel. Nothing new was authenticated and no secret moved.

**Status: wired and proven, except the trigger.** A real test ping landed on his phone
(`ops/notify-telegram.sh --test` → `sent: test ping (1 part(s)) → telegram`, exit 0).
The one open item is what *runs* the drain — see "The gap" at the bottom.

---

## 1. What sends him a Telegram message today

Nothing in AutoDev. It is the **GUTS bridge**, and the actual sender is the **`openclaw`
CLI** — not a bot library, not an HTTP call.

| | |
|---|---|
| Sender | `/home/corgea/.nvm/versions/node/v22.22.2/bin/openclaw` — OpenClaw 2026.6.1 (2e08f0f) |
| Caller | `GUTS/spine/L0-runtime/guts-bridge/src/notify.js` → `buildSendArgs()` → `execFile` |
| Contract | `openclaw message send --channel telegram --target <chat id> --message <text> [--reply-to <id>] [--json]` |
| Trigger | the bridge's tmux watcher: an agent **asks a question** or **finishes a turn** (`BRIDGE_NOTIFY_EVENTS`, default `question,finished`) |
| Live? | yes — `openclaw channels status` → `Telegram default: enabled, configured, running, connected, mode:polling, token:config` |

**Where the credentials live (referenced, never read or copied):**

- **Telegram bot token** — inside openclaw's own store, `~/.openclaw/` (`openclaw.json` and
  `credentials/`, both mode 0600). `channels status` reports `token:config`. The bridge never
  sees it; neither does this repo.
- **Recipient chat id** — `BRIDGE_NOTIFY_TARGET` in
  `GUTS/spine/L0-runtime/guts-bridge/.env` (mode 0600). Also set there:
  `BRIDGE_NOTIFY_CHANNEL`, `BRIDGE_NOTIFY_EVENTS`, `BRIDGE_ANSWER_TOKEN`.

Two details from `src/notify.js` worth copying rather than rediscovering: the message body is
passed as **one argv element** (it is untrusted agent output — never through a shell), and
**Telegram rejects a message over 4096 characters outright** rather than truncating it, so a
long body must be split or it is silently lost.

The bridge proposals (`bridge_ping_signal_to_noise.md`, `bridge_coordination_api.md`,
`bridge_html_mode.md`, `bridge_to_gons_hq_transfer.md`) are about *tuning* that path — which
events earn a ping, how long a stop must hold, how a chat reply is typed back into a live
agent. They do not define a second transport. `openclaw message send` is the whole contract.

---

## 2. What AutoDev will actually call

Read from `plugin/scripts/notify.mjs` (v0.53.0), not guessed.

**The config file is `.autodev/notify.json`** — *not* `connect.json`. Shape, from
`loadConfig()` + `createTransports()` + `feedSettings()`:

```json
{ "transports": ["console", "file"],
  "rules":      [ { "on": "stage.loopback", "where": {"stage": "verify"},
                    "min_attempts": 2, "notify": "human:lead", "note": "QA failed twice" } ],
  "feed":       { "enabled": false, "transports": ["file"], "batch_seconds": 5,
                  "since": "1h", "max_lines": 20 } }
```

**Transport names, and which ones are real:**

| name | real? | what it does |
|---|---|---|
| `console` | **yes** | prints the packet to stdout — *this is the "print it into the terminal" he asked about* |
| `file` | **yes** | writes the packet to `.autodev/outbox/<key>.md`; the docstring says "any channel bridge (or the human) can pick outbox files up" |
| `telegram` | **no — adapter slot** | every send fails closed |
| `slack` | **no — adapter slot** | every send fails closed |

That fourth row is the important one, and it is measured, not assumed:

```
$ node scripts/notify.mjs process --root <scratch> --shop autosql --transports telegram
notify: telegram send failed for T-2|accept|gate_waiting|2026-08-21T12:00:00Z
  — telegram transport is an adapter slot — connect it during onboarding
    (no credentials are stored here) (recorded failed, will retry)
{"paged":0,"alerts":0,"feed":0}
```

An adapter can only be supplied **in-process**, via
`createTransports({ extraAdapters: { telegram: {name, send({text, packet})} } })`. There is no
config key and no CLI flag that hands AutoDev a Telegram credential. So putting `"telegram"`
in `notify.json` would not page him — it would fail every send forever. The `file` transport
is the supported seam, and that is what we used.

**`.autodev/connect.json` does not route anything.** Grepping every reader: `setup.mjs`
creates it, `install-id.mjs` reads it for an install id, and `onboard.mjs` uses
`deadChannels()` — `channels.filter(c => c.test_send !== "ok")`. It is an onboarding **proof
record**, shape `{ "channels": [ { "name": ..., "test_send": "ok" | "failed" } ] }`. It is
where you record that a channel was *tested*, not where you configure one.

**What gets sent.** `buildDecisionPacket()` — a self-contained decision packet: the gate's
question verbatim, keyholder + how long it has waited, the evidence and ticket path, the
passport, the intent chain, any named-feature descopes, and how to clear or send back. He can
decide from the message alone, which is the whole point. Pageable events are `gate_waiting`,
`stalled`, and `review.waiting`; an occurrence stops being live once a
`stage.advanced` / `gate.cleared` / `stage.loopback` / `ticket.unblocked` lands for that ticket.

---

## 3. What is wired now

```
tracker.mjs writes gate_waiting to .autodev/events.jsonl   (ticket stops and waits)
        │
        ├─ console transport ─────────────► the terminal, immediately
        │
        └─ file transport ───────────────► .autodev/outbox/<key>.md
                    │
                    └─ ops/notify-telegram.sh ──► openclaw message send
                                                  --channel telegram --target <chat id>
                                                        │
                                                        └──► Evan's phone
```

**Files added / changed**

- `.autodev/notify.json` — `transports: ["console", "file"]`. Console is his terminal ask;
  file is the Telegram feed. `telegram` deliberately absent (see above).
- `.autodev/notify-telegram.json` — where the drain finds the recipient. Holds a **path**, not
  a chat id: `target_file` points at the guts-bridge `.env` that already has one.
- `ops/notify-telegram.sh` — the channel bridge. Drains `.autodev/outbox/*.md` through
  `openclaw`, moves each sent packet to `.autodev/outbox/sent/`, leaves failures in place to
  retry. Chunks at 3500 chars (the 4096 rejection). Body passed as one argv element. Fails
  closed with instructions when no recipient resolves. `--test` and `--dry-run` included; the
  chat id is redacted in all output and openclaw's own stdout is swallowed because it echoes it.
- `.autodev/connect.json` — records both channels with `test_send: "ok"`, now that both were
  actually tested. `deadChannels()` returns `[]`.
- `.gitignore` — `.autodev/outbox/` and `.autodev/notify/` (per-machine delivery state).

**No secret was copied, printed, or moved.** The bot token stays in `~/.openclaw`. The chat id
stays in the guts-bridge `.env` and is read at send time into a shell variable that is never
echoed. This repo stores one filesystem path.

**Proof**

```
$ ops/notify-telegram.sh --test
sent: test ping (1 part(s)) → telegram
exit=0

$ node scripts/notify.mjs process --root <scratch copy> --shop autosql
[AutoDev] DECISION NEEDED — T-2 (demo-the-autosql-ui-...) held at gate accept
... full decision packet, question + evidence + passport + how to clear ...
{"paged":1,"alerts":0,"feed":0}

$ AUTODEV_ROOT=<scratch copy> ops/notify-telegram.sh --dry-run
--- would send part 1/1 to channel=telegram target=<redacted; from BRIDGE_NOTIFY_TARGET in .../guts-bridge/.env> ---
[AutoDev] DECISION NEEDED — T-2 ...

$ node scripts/doctor.mjs --root .
doctor: PASS 18✓ 1⚠        (the ⚠ is a pre-existing unrelated role gap in feature-regulated@v1)
```

The end-to-end rehearsal ran against a **scratch copy** of `.autodev/` with a synthetic
`gate_waiting` appended. The real `events.jsonl` was never written to, and the packet above is
generated from the real T-2 ticket — that is the actual message he will get.

---

## 4. The gap — nothing runs the drain yet

**AutoDev never invokes `notify.mjs` by itself.** Grepped the whole plugin: the only callers
are the tests and its own CLI. There is no hook, no cron, no sidecar path.
`setup.mjs` says why, deliberately: *"NO alarm clock — the clock was removed 2026-07-21
(session-driven architecture). Nothing runs on a timer pushing work."* The monitoring sidecar
observes only and never touches notify.

So the transport is proven but nothing pulls the trigger. One command does both legs:

```bash
node "$CLAUDE_PLUGIN_ROOT/scripts/notify.mjs" process --root . --shop autosql \
  && ops/notify-telegram.sh
```

Three ways to fire it, cheapest first:

1. **By hand / by the driving session.** Run it whenever a ticket goes to a gate. Zero
   config, zero risk, but it depends on someone remembering — which is exactly the failure
   mode the plugin's own sidecar comments complain about.
2. **A `Stop` hook** in `.claude/settings.json` — fires when a session finishes its turn,
   which is precisely when a gate hold exists and Evan has walked away. Drafted below,
   **not applied**: it adds a shell command that runs automatically in this repo, and that is
   a harness-config change for Evan or the driving session to make, not a subagent.

   ```json
   { "hooks": { "Stop": [ { "hooks": [ { "type": "command",
       "command": "cd \"$CLAUDE_PROJECT_DIR\" && node \"$CLAUDE_PLUGIN_ROOT/scripts/notify.mjs\" process --root . --shop autosql >/dev/null 2>&1; ops/notify-telegram.sh >/dev/null 2>&1 || true" } ] } ] } }
   ```

3. **Let the GUTS bridge cover it.** The bridge already pings on `question` and `finished` for
   any Claude session in tmux. If AutoDev work runs there, he already gets *a* ping when a
   session stops — just not the decision packet, and not the gate's question. Option 1 or 2
   is what upgrades that nudge into something he can answer.

## 5. Also available, left off on purpose

`notify.json` → `"feed": {"enabled": true}` (or `AUTODEV_FEED_NOTIFY=1`) delivers one
plain-English line per ledger event, batched. That is the informational firehose, not the
"something is waiting on you" signal Q35 asked for, so it stays off. Flip it on if he wants
ambient progress; `batch_seconds` and `max_lines` keep a burst to one message.
