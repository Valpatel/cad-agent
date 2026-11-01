**Fixed**
- `<cad-cantilever>` and `<cad-fourbar>` (`kit/cantilever.js`, `kit/fourbar.js`): Pause works in WebKit. The demos
  rewrote the button's label on every animation frame, and WebKit drops the click of a press that started on the old
  text, so a press of a few frames never paused them. In Playwright's WebKit it failed on every one of 20 presses.
  Safari uses the same engine; it was not tried on a Mac. The label is now written only when it changes (#154).

**Projects must change**
- Projects with a copied kit: rerun `cad-agent webkit <dir>` (and rebuild sites made with `cad-agent site`) to ship the
  fixed `cantilever.js` and `fourbar.js` (#154).
