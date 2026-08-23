// demo/frontend/icons.jsx — B17's two-sprite resolver.
//
// WHY THIS FILE EXISTS (and why locate §3.1's tree grows by one)
//   B17 rules that a name is resolved against TWO sprites, vendored
//   first. Every one of the six other frontend modules draws icons, so
//   the resolver cannot live inside any one of them without making the
//   other five import a sibling for a reason that has nothing to do with
//   what that sibling is. Locate §3.1 gave the resolver no home; this is
//   it. Nothing else is in here.
//
// THE RULE, RESTATED
//   demo/vendor/icons.svg    — GIMS's 54 symbols, byte-identical, never
//                              edited (D1, D2). Served at /static/icons.svg
//                              because vendor/ui.jsx's own Icon hardcodes
//                              that URL, and copying the file into
//                              demo/static/ would fork it.
//   demo/static/icons-demo.svg — exactly the 18 the approved mock draws
//                              that do not exist upstream.
//   The vendored sprite is checked FIRST. So i-play, i-plus and i-search
//   render GIMS's shapes, not the mock's: the three differences are
//   sub-pixel and D1 outranks a drawing detail nobody chose deliberately.
//
// THE INVARIANT
//   The two sprites share no id. demo/tests/test_ui.py asserts it against
//   the files themselves, so the list below cannot drift from the sprite
//   without a test failing.

import { Icon as GimsIcon } from "../vendor/ui.jsx";

//: The 54 ids in demo/vendor/icons.svg, without the `i-` prefix — the
//: form vendor/ui.jsx's Icon takes. Sorted; kept honest by the test.
export const VENDORED = [
  "adjective", "adverb", "archive", "arrow", "audit", "backup", "camera",
  "check", "chevron", "clock", "close", "compass", "compliance",
  "conjunction", "dots", "download", "edit", "external", "file", "filter",
  "flask", "folder", "grid", "help", "image", "info", "investigation",
  "key", "link", "lock", "logout", "mail", "menu", "noun", "palette",
  "parser", "play", "plus", "refresh", "robot", "rotate", "runlog", "save",
  "search", "sparkle", "tag", "template", "terminal", "trash", "upload",
  "user", "verb", "warning", "webcam",
];

const VENDORED_SET = new Set(VENDORED);

//: The 18 that live only in demo/static/icons-demo.svg.
export const DEMO_ONLY = [
  "ban", "cap", "caret", "code", "columns", "dash", "drop", "neq", "pin",
  "pulse", "python", "quote", "shield", "shield-stop", "sigma", "sort",
  "wave", "x",
];

const DEMO_SPRITE = "/static/icons-demo.svg";

/**
 * One icon, resolved to whichever sprite holds it — vendored first.
 *
 * `name` is given without the `i-` prefix, exactly as GIMS's own Icon
 * takes it, so a call site reads the same on either side of the split.
 */
export function Ic({ name, className }) {
  if (VENDORED_SET.has(name)) return <GimsIcon name={name} className={className} />;
  return (
    <svg className={"icon" + (className ? " " + className : "")} aria-hidden="true">
      <use href={DEMO_SPRITE + "#i-" + name} />
    </svg>
  );
}

/** Which sprite a name comes from — used by the contract test and by nothing else. */
export function spriteFor(name) {
  return VENDORED_SET.has(name) ? "vendor" : "demo";
}
