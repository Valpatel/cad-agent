**Changed**
- Website: on docs pages the "On this page" column and the wider page start at 1400 px instead of 1500 px, so a 1440 px laptop reaches a page's outline without scrolling the tree; other pages keep the 1240 px shell until 1500 px, and a docs page with no outline no longer keeps an empty column beside the article (#807).
- Web kit `ui/appnav.js`: on a page that loads the kit's theme (`ui/theme.css`), the top bar takes its colours and follows the page's light or dark theme; other pages keep the dark bar (#807).

**Fixed**
- Web kit `documents/nav.css`: no half-cut tree row shows above a `<cad-nav>` panel's sticky controls (#807).
- Website: Back, Forward or a reload to an install address (`/docs/agent-workflow#install-…`) keeps the reader's place instead of jumping back to the block (#807).
- `cad-agent site --serve`: the kit's file viewer starts right under the injected top bar (it was a bar's height lower), `nav=0` in an address keeps the injected bar off, and the bar in the site's own pages gets the same 44 px phone targets as `ui/appnav.js` (#807).
- `cadagent.publish.guides`: a packed model whose part is not an object is refused with `CadConfigError`, like every other fault, not an `AttributeError` (#807).
