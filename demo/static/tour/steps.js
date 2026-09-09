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
  var KEY = "autosql_demo_tour_v1";

  /* Step 6 drives the host rather than asking the visitor to perform eight actions: it sets
     the pick to the EdgeCase / max($.m) shape and runs it, so they arrive at the payload. */
  function byText(re) {
    return Array.prototype.find.call(document.querySelectorAll("button"),
      function (el) { return re.test(el.textContent || ""); });
  }

  /* Drive the host to demo walkthrough step 11 via the demo's OWN preset rail — clicking
     what a visitor would click, rather than reaching into the app's state.

     The preset is "4 Reconciled". An earlier draft searched for a control matching /edge/i
     and there is no such control: the source is a <select> whose option is noun:EdgeCase,
     and the rail is numbered by scenario, not by collection. That draft silently did
     nothing, and step 6 showed Heartbeat rows under a bubble talking about fullwidth
     digits — caught by driving it in a browser, invisible from the source. */
  function driveToStepEleven(api) {
    var preset = byText(/Reconciled/);
    if (!preset) return;
    preset.click();
    return api.wait(350).then(function () {
      var run = byText(/Run this pick/);
      if (run) run.click();
      return api.wait(1200);
    });
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
  function withGnomeRule(step) {
    var own = step.beforeShow;
    var wanted = step.gnome ? "on" : "off";
    step.beforeShow = function (api) {
      var root = document.querySelector(".tour-root");
      if (root) root.setAttribute("data-tour-gnome", wanted);
      return own ? own(api) : undefined;
    };
    return step;
  }

  function config(force) {
    return {
      storageKey: force ? null : KEY,
      narrator: { image: GNOME, name: "GIMS" },
      steps: STEPS.map(function (s) { return withGnomeRule(Object.assign({}, s)); }),
      finishLabel: "Done"
    };
  }

  function boot() {
    if (!window.Tour) return;
    if (!document.querySelector('[data-tour="screen"]')) {
      // The React app has not mounted yet; the engine's own retry cannot help before the
      // root exists, so wait for it rather than starting against an empty page.
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
