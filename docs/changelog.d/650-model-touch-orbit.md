**Fixed**
- `<cad-model>` (`kit/model/model.js`): on a touch screen a one-finger drag now turns the model up and down as well as sideways, without scrolling the page; two fingers still zoom the page. A viewer that leaves less than a quarter of the visible screen's height and width uncovered keeps vertical swipes for the page, so it can always be scrolled past (#650).
- `<cad-model>`: the turntable never steps backwards when a frame is stamped before the previous one.
