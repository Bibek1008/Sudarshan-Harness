# Live product build preparation

Correction phase is complete; no live build was started. Artisan Coffee,
Taskman and Viper remain incomplete until built and independently verified.

1. Configure SUDARSHAN_API_KEY locally (legacy ODYSSEUS_API_KEY, then
   GEMINI_API_KEY remain fallbacks). Check presence without printing its value.
   Confirm the requested model is available; this was not live-verified.
2. Use a fresh projects root. Existing project directories and run evidence
   are refused. Parent sessions remain separate for each project; repair and
   review resume the original session.
3. Choose OS isolation appropriate for generated Python tests. The fleet's
   restricted safe approvals and credential allowlist are not a sandbox.
4. Run python -m unittest discover -v in an environment that can launch the
   installed browser. The correction environment needed command-sandbox
   escalation for Edge; it did not disable the browser's own sandbox.
5. To start builds when authorized, use demos.product_fleet.main or
   run_products with an explicit root. This document does not start a build.
6. Independently inspect the generated page selectors and behavior. Configure
   demos.browser_probe.ChromiumProbe with reviewer-selected mappings, rather
   than trusting selectors or success reports supplied by the generated app.
7. Run verify_product on each existing product. Do not rerun the fresh-root
   fleet to reverify existing outputs. Configure browser_probe for website
   checks; inspect Taskman's actual test quality and terminal output as well.
8. Record only real manual observations using record_manual_verification.
   Evidence belongs outside the agent workspace and is bound to artifact bytes.
   Changed files require renewed evidence. Final acceptance still requires all
   automated and manual checks; missing observations stay manual_pending.

## Browser adapter contract

ChromiumProbe(config, executable=None) discovers Chromium on PATH or installed
Windows Edge/Chrome locations. It uses a temporary browser profile, local HTTP
server and exact-width iframe viewports. Browser sandboxing remains enabled.
Request routing rejects resolved paths outside the project, but this adapter
is not a security boundary for hostile page code or external network access.

For Artisan Coffee, config.product is artisan-coffee. config.interactions maps
subscription_toggle, brew_tabs and faq to button/target selectors and optionally
an attribute to observe. A dark interaction toggles the theme; config.dark
specifies key (localStorage), target and attribute. The adapter verifies changed
state and checks persisted theme state in a newly loaded same-origin document.
The reviewer must choose observable outputs that reflect actual user behavior;
a changing attribute alone cannot establish design quality or accessibility.

For Viper, config.product is viper. config.snapshot is a reviewer-supplied
read-only JavaScript expression yielding head, foods, score, interval, paused
and highScore. Provide move_key, food_keys (a real path collecting at least five
foods), step_ms, pause_key and a restart selector. The adapter never sets food,
score or game state: it dispatches DOM keydown events and observes snapshots.
It tests movement, food/score growth, reduced interval, paused movement, restart
and persisted high score in a newly loaded document. Synthetic DOM key events
are not trusted native OS input. Native keyboard, collision correctness, game
over, rendering and full gameplay still require independent human checks.

The fixture test game is a deterministic test double, not the Viper product.
Fixture success proves the observation mechanism, not that a future product
meets these requirements. Browser metrics are computed-style/geometry
heuristics, not proof of unobscured pixels; overlays, clipping and conditional
states still require visual inspection. Manual evidence remains mandatory.

## Actual correction results

Python 3.12.10, Windows 11 build 26200, Edge 156.0.4314.50.
99 discovered, 98 passed, 0 failures, 1 Windows symlink privilege skip.
Coffee fixture browser checks passed at exact 360, 768 and 1280 CSS pixels;
Viper-style positive and missing-keyboard negative fixtures executed in Edge.
Compilation, CLI help and Git whitespace checks passed. No live products ran.
