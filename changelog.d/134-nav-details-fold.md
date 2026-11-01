**Changed**
- Kit `<cad-nav>` (`webkit/nav.js`, `nav.css`): on narrow screens the "Pages and contents" toggle is a native `<details class="cad-nav-fold"><summary class="cad-nav-toggle">` around the panel, so the tree opens with a tap, Enter or Space even when `nav.js` is slow, blocked or fails, and without script. On wide screens the fold takes no box and its summary hides, so the panel stays a sticky column; `nav.js` keeps the fold open there for browsers without `::details-content`, and never closes a fold the reader opened (#134).
- The site's doc pages write that fold; phones without script now get it too, in place of the tree moved below the article (#134).

**Fixed**
- `<cad-nav>`: a wheel over the rail or the tree while an outline jump is still scrolling releases the jump again, so the section being read is marked, not the heading the reader turned away from; a wheel that only scrolls the tree still keeps it (#134, #123 review 4).
- `<cad-nav>`: a jump ends when the page shows its heading, not after 150 ms without a scroll, so a frame slow to paint no longer drops the mark to another section partway through (#134, #158).
- `<cad-nav>`: no link text shows in the corners beside the filter pill while the tree is scrolled (#134).

**Projects must change**
- Pages that write `<cad-nav>` markup with the old `<button class="cad-nav-toggle">` should write the `<details class="cad-nav-fold">` fold instead (the markup is in the `nav.js` header). The script wraps the old button into a fold when it runs, but until then, or without it, the button does nothing and the tree shows open on narrow screens (#134).
