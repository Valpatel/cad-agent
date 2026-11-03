**Changed**
- The README hero (`docs/img/hero/gyropup-leg.svg`) is transparent on GitHub's page instead of a dark green panel. Its words get a halo in the page colour (`anim.svg.HALO`: white or `#0d1117`), so they stand out whichever colour scheme the SVG picks. `anim.svg.document(background=False)` makes any figure transparent; the FEA and snap-fit figures keep their panels.
