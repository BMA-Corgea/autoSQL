/**
 * T-47 — ops/name-check.sh's exit codes, every one of them driven.
 *
 *   0  looked, and the owner's name is not there
 *   1  the name is there (REFUSING)
 *   2  COULD NOT TELL: not inside a git work tree, git missing, git failing, or an unknown
 *      argument. Never "clean".
 *
 * Until T-47 there was no 2. `git grep … || true` folded git's own failure into "no hits", so a
 * copy of the script run outside a checkout, with the name planted beside it, printed "clean" and
 * exited 0. Each case below runs the REAL script in a throwaway directory; the real tree is never
 * touched. demo/tests/test_owner_name_absent.py keeps covering 0 and 1 from the demo suite.
 *
 * The name is assembled at run time ("ev" + "an"), never written literally: this file is itself in
 * the tracked tree the check scans.
 *
 * run: node --test ops/tests/test_name_check.mjs      (or: ops/run-tests.sh)
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync, execFileSync } from "node:child_process";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const SCRIPT = path.join(REPO, "ops", "name-check.sh");
const NAME = "ev" + "an";
const BASH = execFileSync("bash", ["-c", "command -v bash"], { encoding: "utf8" }).trim();

/** A throwaway directory holding <sub>/ops/name-check.sh; a git repo unless git:false. With sub,
 *  the script's own root is a SUBFOLDER of the repo, i.e. not the top of its checkout. */
function sandbox({ git = true, files = {}, commit = true, sub = "" } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "t47-"));
  const root = path.join(dir, sub);
  fs.mkdirSync(path.join(root, "ops"), { recursive: true });
  fs.copyFileSync(SCRIPT, path.join(root, "ops", "name-check.sh"));
  fs.chmodSync(path.join(root, "ops", "name-check.sh"), 0o755);
  for (const [rel, body] of Object.entries(files)) fs.writeFileSync(path.join(dir, rel), body);
  if (git) {
    const g = (...a) => execFileSync("git", a, { cwd: dir, stdio: "pipe" });
    g("init", "-q", ".");
    g("add", "-A");
    if (commit) g("-c", "user.name=t", "-c", "user.email=t@invalid", "commit", "-qm", "x");
  }
  return dir;
}

function run(dir, args = [], env = process.env, sub = "") {
  const r = spawnSync(BASH, [path.join(dir, sub, "ops", "name-check.sh"), ...args], { cwd: dir, env, encoding: "utf8" });
  fs.chmodSync(dir, 0o755);
  fs.rmSync(dir, { recursive: true, force: true });
  return { code: r.status, stdout: r.stdout || "", stderr: r.stderr || "", out: (r.stdout || "") + (r.stderr || "") };
}

const couldNotTell = (r, why) => {
  assert.equal(r.code, 2, `${why}: expected exit 2 (could not tell), got ${r.code}\n${r.out}`);
  assert.match(r.stderr, /COULD NOT TELL/, `${why}: the reason belongs on stderr`);
  assert.doesNotMatch(r.out, /name-check: clean/, `${why}: printed "clean" though it could not look`);
};

test("0 — a git repo without the name: clean, in both modes", () => {
  const tree = run(sandbox({ files: { "notes.md": "nothing to see\n" } }));
  assert.equal(tree.code, 0, tree.out);
  assert.match(tree.out, /clean \(the tracked tree\)/);
  const staged = run(sandbox({ files: { "notes.md": "still nothing\n" }, commit: false }), ["--staged"]);
  assert.equal(staged.code, 0, staged.out);
  assert.match(staged.out, /clean \(the staged diff\)/);
});

test("1 — the name in a git repo: REFUSING, in both modes", () => {
  const tree = run(sandbox({ files: { "probe.md": `human:${NAME}\n` } }));
  assert.equal(tree.code, 1, tree.out);
  assert.match(tree.out, /REFUSING/);
  const staged = run(sandbox({ files: { "probe.md": `human:${NAME}\n` }, commit: false }), ["--staged"]);
  assert.equal(staged.code, 1, staged.out);
  assert.match(staged.out, /REFUSING/);
});

test("2 — outside any git work tree, with the name planted: could not tell, never clean", () => {
  couldNotTell(run(sandbox({ git: false, files: { "probe.md": `human:${NAME}\n` } })), "tree mode outside a repo");
  couldNotTell(run(sandbox({ git: false, files: { "probe.md": `human:${NAME}\n` } }), ["--staged"]), "--staged outside a repo");
});

test("2 — git not on PATH: could not tell", () => {
  const bin = fs.mkdtempSync(path.join(os.tmpdir(), "t47-bin-"));
  for (const tool of ["dirname", "grep", "sed"]) {
    const real = execFileSync("bash", ["-c", `command -v ${tool}`], { encoding: "utf8" }).trim();
    fs.symlinkSync(real, path.join(bin, tool));
  }
  try {
    couldNotTell(run(sandbox({ files: { "probe.md": `human:${NAME}\n` } }), [], { ...process.env, PATH: bin }),
      "git missing");
  } finally {
    fs.rmSync(bin, { recursive: true, force: true });
  }
});

test("2 — git failing inside a repo (a corrupt index): could not tell, in both modes", () => {
  for (const args of [[], ["--staged"]]) {
    const dir = sandbox({ files: { "probe.md": `human:${NAME}\n` } });
    fs.writeFileSync(path.join(dir, ".git", "index"), "not an index");
    couldNotTell(run(dir, args), `corrupt index, ${args[0] ?? "tree"} mode`);
  }
});

test("2 — an unknown argument is refused rather than silently checking something else", () => {
  couldNotTell(run(sandbox({ files: { "notes.md": "x\n" } }), ["--stagd"]), "a typo of --staged");
});

test("2 — a bare repository (no work tree), in --staged mode: could not tell", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "t47-bare-"));
  execFileSync("git", ["init", "-q", "--bare", dir]);
  fs.mkdirSync(path.join(dir, "ops"));
  fs.copyFileSync(SCRIPT, path.join(dir, "ops", "name-check.sh"));
  couldNotTell(run(dir, ["--staged"]), "a bare repository");
});

test("2 — the script inside ANOTHER work tree (not the top of its own checkout): could not tell", () => {
  // The review's must-fix: a copy under some other repo used to search that repo's tracked files
  // from a subfolder, find none of its own, and say clean.
  for (const ignored of [false, true]) {
    const files = { "probe.md": `human:${NAME}\n` };
    if (ignored) files[".gitignore"] = "sub/\n";
    const dir = sandbox({ files, sub: "sub" });
    fs.writeFileSync(path.join(dir, "sub", "probe.md"), `human:${NAME}\n`);
    couldNotTell(run(dir, [], process.env, "sub"), `nested in another work tree${ignored ? ", git-ignored" : ""}`);
  }
});

test("1 — a tracked file the work tree cannot show still refuses: unreadable, or deleted locally (the index is searched)", () => {
  const unreadable = sandbox({ files: { "probe.md": `human:${NAME}\n` } });
  fs.chmodSync(path.join(unreadable, "probe.md"), 0o000);
  const r1 = run(unreadable);
  assert.equal(r1.code, 1, r1.out);
  assert.match(r1.out, /REFUSING/);
  const deleted = sandbox({ files: { "probe.md": `human:${NAME}\n` } });
  fs.rmSync(path.join(deleted, "probe.md"));
  const r2 = run(deleted);
  assert.equal(r2.code, 1, r2.out);
  assert.match(r2.out, /REFUSING/);
});

test("2 — extra arguments are refused, not silently dropped", () => {
  couldNotTell(run(sandbox({ files: { "notes.md": "x\n" } }), ["--staged", "extra"]), "--staged extra");
});

test("--staged ignores user diff settings that can hide a line (colour, an external diff tool)", () => {
  for (const env of [{ GIT_CONFIG_COUNT: "1", GIT_CONFIG_KEY_0: "color.ui", GIT_CONFIG_VALUE_0: "always" },
                     { GIT_EXTERNAL_DIFF: "true" }]) {
    const r = run(sandbox({ files: { "probe.md": `human:${NAME}\n` }, commit: false }), ["--staged"], { ...process.env, ...env });
    assert.equal(r.code, 1, `${JSON.stringify(env)}: ${r.out}`);
  }
});
