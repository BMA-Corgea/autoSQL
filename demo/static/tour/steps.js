/* ══════════════════════════════════════════════════════════════════════════════════════════
   steps.js — the tour's CONTENT. The engine (tour.js) is generic and unforked; everything
   specific to this screen lives here.

   Seven steps, arriving at demo walkthrough step 11 — his ruling (GA-32). The tour teaches
   the SCREEN, not the expression language: demo/README.md's walkthrough already teaches the
   language, better and at the reader's own pace. A tour that walked all fourteen evenly
   would spend its attention budget before reaching the only step whose result a visitor
   could not have predicted.

   THE NARRATOR IS NOT IN EVERY STEP. The GIMS gnome appears at 1, 6 and 7 and is absent
   from the working steps 2-5. He introduces, gets out of the way while the visitor is
   reading numbers, returns for the point, and signs off. That is the answer to the one real
   tonal risk: pixel art is native on Classic and JRPG, and the sober default (System, which
   follows the OS) is where a smiling character beside "is this number wrong" could grate.
   Step 6, where he does appear, is the RECONCILED moment — both panes read 123 — so the one
   place he stands over a number is the place the number is right.

   No inline script: index.html's CSP is script-src 'self'.
   ══════════════════════════════════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  var GNOME = "/vendor/tour/gnome-tour.png";
  var NARRATOR_NAME = "GIMS";
  var KEY = "autosql_demo_tour_v1";

  /* Step 6 drives the host rather than asking the visitor to perform eight actions: it sets
     the pick to the EdgeCase / max($.m) shape and runs it, so they arrive at the payload. */
  /* Scoped to the demo's own tab rail (`.tabs[role="tablist"]`, app.jsx), NOT to every
     button on the page. An unscoped search also sweeps the tour's own controls — Skip,
     Back, Next, View page, Replay — and would become a real defect the moment a step's
     pattern happened to match one of them. Nothing here derives its text from data, so the
     rail's labels are the app's own words and are safe to match on. */
  function byTabText(re) {
    return Array.prototype.find.call(
      document.querySelectorAll('.tabs [role="tab"]'),
      function (el) { return re.test(el.textContent || ""); }
    );
  }

  /* Drive the host to demo walkthrough step 11 via the demo's OWN preset rail — clicking
     what a visitor would click, rather than reaching into the app's state.

     The preset is "4 Reconciled". An earlier draft searched for a control matching /edge/i
     and there is no such control: the source is a <select> whose option is noun:EdgeCase,
     and the rail is numbered by scenario, not by collection. That draft silently did
     nothing, and step 6 showed Heartbeat rows under a bubble talking about fullwidth
     digits — caught by driving it in a browser, invisible from the source. */
  /* THE PRESET CLICK ALREADY RUNS THE PICK, and a second run was actively damaging.

     app.jsx's `show(i)` ends with `run(p, st)` — the rail's own onClick does the whole job.
     An earlier draft followed it, after a wait, with a click on "Run this pick", and that
     click has two outcomes and no third:

       still in flight  the button reads "Running…" and is disabled, byText finds nothing,
                        the line does nothing — and looks exactly like a line that worked;
       already returned the button matches and fires `run(pick, null)`, which sets
                        `ranFrom = null`, so `preset = !dirty && ranFrom ? ranFrom : null`
                        becomes null and verdict.jsx STOPS RENDERING `.verdict-ref` —
                        the "walkthrough step 11 · §5 the correctness control · the value
                        that used to be wrong" line — at the exact step whose bubble is
                        about that value. Plus a duplicate POST /api/pick.

     Which one you got depended on whether Postgres answered inside the wait. Measured in a
     browser on 2026-09-09: at step 6, `.verdict-ref` was ABSENT. The comment above about a
     selector that silently did nothing was written one screen up; the replacement reproduced
     the shape underneath it. So: click the preset, wait for the run the preset started, and
     do not press a button the app has already pressed. */
  function driveToStepEleven(api) {
    var preset = byTabText(/Reconciled/);
    if (!preset) return;
    preset.click();
    return api.wait(1400);
  }

  var STEPS = [
    {
      target: '[data-tour="screen"]',
      title: "Two panes, one question",
      text: "Postgres on the left, Python on the right, both answering the same pick. " +
            "When they agree the number is boring — and boring is the point. " +
            "When they disagree, something is wrong and the screen says so.",
      gnome: true
    },
    {
      target: '[data-tour="pick"]',
      title: "This is where you ask",
      text: "Pick a source, add a computed column, filter, sort — the same shapes a real " +
            "dashboard offers. Nothing here is free text that reaches the database."
    },
    {
      target: '[data-tour="run"]',
      title: "Run it",
      text: "Go ahead and press it. The pick runs down both paths at once.",
      advanceOn: "target-click",
      advanceDelay: 700
    },
    {
      target: '[data-tour="panes"]',
      title: "They agree, and that is the normal case",
      text: "Value for value, column for column. Agreement is what 11,367 tested expressions " +
            "bought — on data written by this Python process. Rows written by anything " +
            "else can still diverge; the README says where."
    },
    {
      target: '[data-tour="gate"]',
      title: "Compile → Gate → Execute",
      text: "Not every expression is allowed through. The gate refuses the ones that cannot " +
            "be answered identically on both sides, rather than guessing and being wrong quietly."
    },
    {
      target: '[data-tour="panes"]',
      title: "The cell that used to be silently wrong",
      text: "Those are not ASCII digits. １２３ is three FULLWIDTH code points, and " +
            "Python's float() reads them as 123. So, now, does the SQL — the same 670-digit " +
            "mapping on both sides. Both panes read 123. This is the value that used to come " +
            "back wrong with nothing on screen to say so.",
      gnome: true,
      beforeShow: driveToStepEleven
    },
    {
      target: '[data-tour="screen"]',
      /* This step is ABOUT the switcher, and tour-tokens.css drops #skin-picker below the dim
         for the whole tour (it intercepted Next — see that file). `.wrap` is max-width:1520px
         and centred, so on a wide screen the spotlight hole does not even reach the picker,
         which is fixed to the viewport corner. `raise` is the engine's own answer: it sets an
         inline z-index above the dim for this step and restores it on the next change. */
      raise: "#skin-picker",
      title: "Seven looks, and this tour again whenever you want it",
      text: "The skin switcher is bottom-right. Everything you just saw is invented data — " +
            "no real sender, no real customer, nothing that happened anywhere.",
      gnome: true
    }
  ];

  /* The engine has no global per-step callback — `beforeShow` is the per-step hook it
     actually exposes, so the gnome's presence is set there. Checked against tour.js rather
     than assumed: beforeShow / afterShow / advanceOn / advanceDelay / finishLabel exist;
     an `onShow` option does not, and an earlier draft of this file invented one. */
  /* THE BYLINE, and why it is here rather than in the engine's config.

     `narrator: { image, name }` is what the engine's own usage comment documents, and I
     passed `name: "GIMS"` — then recorded in demo/EVIDENCE.md that a browser run had
     CONFIRMED a bubble "bylined GIMS". It had not, and could not have: tour.js reads
     `narrator.image` at line 135 and reads `name` NOWHERE. The string was inert config, the
     bubble had no byline element at all, and I wrote an observation of something that does
     not exist into an append-only evidence file. A config key the library accepts and
     ignores looks exactly like a config key that worked.

     The byline is a design decision, not decoration — autoSQL is a GIMS component, not a
     standalone product, so the narrator speaks AS GIMS rather than as an invented identity.
     So it is built here, in this repo's own code, appending to the bubble the same way the
     engine builds its own DOM. The engine is still not forked. */
  function ensureByline(name) {
    var bubble = document.querySelector(".tour-bubble");
    if (!bubble || bubble.querySelector(".tour-byline")) return;
    var el = document.createElement("div");
    el.className = "tour-byline";
    el.textContent = name;
    bubble.insertBefore(el, bubble.firstChild);
  }

  /* NEVER TRAP THE VISITOR.

     On an `advanceOn: "target-click"` step the engine hides Next (tour.js:224) because the
     visitor is meant to click the real control. Step 3's real control is
     `<button data-tour="run" disabled={busy}>`, and A DISABLED BUTTON FIRES NO CLICK EVENT —
     so the engine's capture listener never runs, and its keyboard fallback (`curTarget.click()`)
     is equally inert. Arrive at step 3 while a pick is still running, or with the target
     unresolved, and the only ways out are Skip and Escape: the tour looks like it has hung.

     `isVisible()` does not consider `disabled`, so the engine cannot know. This does: after
     each step is shown, if it advances on a target click and that target is missing or
     disabled, Next comes back. Both routes then advance and neither is a dead end. */
  function revealNextIfTargetCannotBeClicked(step) {
    if (step.advanceOn !== "target-click") return;
    var el = document.querySelector(step.target);
    if (el && !el.disabled) return;
    var next = document.querySelector(".tour-btn.tour-primary");
    if (next) next.style.display = "";
  }

  function withGnomeRule(step) {
    var ownBefore = step.beforeShow;
    var ownAfter = step.afterShow;
    var wanted = step.gnome ? "on" : "off";
    step.beforeShow = function (api) {
      var root = document.querySelector(".tour-root");
      if (root) root.setAttribute("data-tour-gnome", wanted);
      ensureByline(NARRATOR_NAME);
      return ownBefore ? ownBefore(api) : undefined;
    };
    step.afterShow = function (api) {
      revealNextIfTargetCannotBeClicked(step);
      return ownAfter ? ownAfter(api) : undefined;
    };
    return step;
  }

  /* REPLAY LANDS ON WHATEVER THE VISITOR WAS LOOKING AT, and the narration does not.
     Tour.replay restarts at step 1 without touching app state, so a visitor sitting on
     "Refused: the expression" who presses Replay hears step 4's "They agree, and that is the
     normal case" over a refusal and sees step 5's rail showing a stop. Only step 6 drives the
     host. So a replay first returns the demo to its own opening state — the same first tab
     the app loads with — and the narration matches the screen again. */
  function resetToFirstState() {
    var first = document.querySelector('.tabs [role="tab"]');
    if (first && first.getAttribute("aria-selected") !== "true") first.click();
  }

  function config(force) {
    return {
      storageKey: force ? null : KEY,
      narrator: { image: GNOME, name: NARRATOR_NAME },
      steps: STEPS.map(function (s, i) {
        var step = withGnomeRule(Object.assign({}, s));
        if (force && i === 0) {
          var own = step.beforeShow;
          step.beforeShow = function (api) {
            resetToFirstState();
            return own ? own(api) : undefined;
          };
        }
        return step;
      }),
      finishLabel: "Done"
    };
  }

  // The React app has not mounted yet; the engine's own retry cannot help before the root
  // exists, so wait for it rather than starting against an empty page. BOUNDED, because an
  // app that never mounts would otherwise leave a timer re-arming for the life of the tab,
  // and would do it in silence. Forty tries is far longer than the app has ever taken to
  // mount; giving up says so in the console rather than waiting forever with nothing to see.
  // The interval is not written out in words anywhere here: AC-37 sweeps this tree for timing
  // vocabulary and it is right to. The numbers live in the code.
  var bootTries = 40;

  function boot() {
    if (!window.Tour) return;
    if (!document.querySelector('[data-tour="screen"]')) {
      if (--bootTries <= 0) {
        return void console.warn(
          'tour: [data-tour="screen"] never appeared — either the app did not ' +
          "mount, or the anchor was renamed in the .jsx without updating steps.js. " +
          "Tour not started."
        );
      }
      return void setTimeout(boot, 150);
    }
    window.Tour.start(config(false));

    var replay = document.createElement("button");
    replay.type = "button";
    replay.className = "tour-replay";
    replay.textContent = "Replay the tour";
    replay.addEventListener("click", function () { window.Tour.replay(config(true)); });
    document.body.appendChild(replay);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
