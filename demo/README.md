# The autoSQL demo

This is a small, self-contained screen that lets you build a handful of
read-only queries against a made-up dataset, and shows two independent
answers for each one — computed two completely different ways — side by
side. It exists so the SQL query-builder idea can be looked at and driven by
hand, end to end, before it goes anywhere near GIMS or any real data.

Every row behind this screen is invented. Nothing here describes anything
real, and none of it should be read as though it does.

## Running it

From a clean checkout, one command:

```
./run-demo up
```

That brings up this demo's own Postgres database, loads it with the seeded
rows if it's empty, and serves the screen. When you're done:

```
./run-demo down
```

which tears the demo's stack back down and touches nothing else on the
machine. There's also:

```
./run-demo test        # the demo's own test suite
./run-demo build-ui     # rebuilds the screen's front-end bundles
```

`build-ui` is the only one of the four that needs Node — `up` and `test`
both work with Node removed from `PATH`, and with the network switched off:
this demo's Python dependencies are pinned, committed wheel files, installed
straight from this repository rather than fetched from anywhere.

## What it owns, and what it never touches

This demo has exactly two ports: its own Postgres, on `127.0.0.1:55440`, and
its own app, on `127.0.0.1:8787`. It refuses to start if either one is
already taken by something else, rather than guessing. It does not use, and
cannot be pointed at, any other database on this machine, under any
environment variable, by any route — that includes the live database this
project's other work depends on, which lives on a different port entirely
and which this demo is never allowed to dial.

## What's in it

Three made-up collections, `10,410` rows in total:

| Collection | Rows | What it's for |
|---|---|---|
| `noun:Heartbeat` | 8,400 | Most of the walkthrough — 50 senders, one row an hour, for a week |
| `noun:Sample` | 2,000 | A second, differently-shaped collection, used to show the same controls behaving the same way on different data |
| `noun:EdgeCase` | 10 | Ten specific, deliberately unusual rows, used to show what happens at the edges — very large numbers, values of the wrong shape, and so on |

## The walkthrough

[`WALKTHROUGH.md`](./WALKTHROUGH.md) is the same 14 steps described in
order, with the specific number each one is supposed to produce, and a short
glossary of the handful of technical terms it can't avoid using along the
way.

One step in it (step 11) is worth calling out here too, because it looks
like a bug and isn't one: the two answers are supposed to come out
different. One collection carries a piece of text whose digits are the
wide, full-width kind rather than the ordinary `0`–`9`. Python's
number-reading recognises digits from any writing system and reads it as
`123`; the SQL side's rule only recognises the ordinary characters, so to
it the text is not a number at all and drops out of the calculation. Two
plausible answers, silently different — a real, measured gap between the
two engines, not something staged. When that happens, the screen says so
out loud — a marked, visible disagreement, never two quiet numbers sitting
side by side as if they matched.

## What this is not

There is no performance information anywhere on this screen or in this
document — no measurement, no comparison, no indication of how long
anything here takes to run. That question hasn't been asked yet, belongs to
a separate piece of work, and nothing here should be read as answering it
either way.
