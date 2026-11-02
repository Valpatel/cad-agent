**Fixed**
- `cadagent.manufacturing.fit_coupons`: an `insert` fit's sweep centres on the hole `inserts.hole_design` draws: the maker's hole plus 0.2 mm, 4.2 mm for a 4.0 mm M3 hole. It used to centre on 4.25 mm. CNC Kitchen's M3 held best at 4.2 mm in CAD, and the 0.2-0.3 mm offset already includes the printed hole's undersize, so the `insert` allowance is now -0.05 mm (#290).

**Projects must change**
- An insert coupon printed before this has its holes 0.05 mm larger than a new one. Pick the hole that fitted by its CAD size, not by its place in the row (#290).
