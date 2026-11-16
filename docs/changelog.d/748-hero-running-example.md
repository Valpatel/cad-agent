**New**
- `<cad-model loading="scroll">`: the viewer keeps its look-ahead but starts nothing (no three.js, no model data) until the reader scrolls the page, or focuses or presses inside the element; the element joins the tab order so a keyboard reader can start it without scrolling. Other viewers load as before (#748).

**Changed**
- Home page: the first screen now shows a real running example. The headline, a shorter lede and the actions sit beside (on phones, above) Gyropup's turret playground recording, with its limits in one line (a work-in-progress prototype, not physics validation) and a link to the live playground. The page loads its 9 KB still first and swaps in the 324 KB animation after the page has loaded; under reduced motion, with Save-Data, or without script, the still stays (#748).
- Home page: the pixel-art workshop is a slim cropped band between the hero and "See it run", which now leads with the two interactive 3D viewers. They use `loading="scroll"`, so a visitor who does not scroll downloads no 3D model at any screen size (#748).
- `llms.txt` lists the home page's running examples under "See it run", and `index.md` follows the new hero order (#748).
