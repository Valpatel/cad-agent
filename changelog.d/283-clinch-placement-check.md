**New**
- `cadagent.mechanical.clinch` checks where a self-clinching (PEM-type) nut, stud or standoff may go in a sheet:
  - the sheet's hardness against the part's material, with no listed part allowed in stainless sheet;
  - the thickness for its shank;
  - the hole band (+0.08 mm / −0);
  - the edge distance;
  - the distance to a bend (BA/2 + E from the bend centre line, with the bend allowance from `sheet_metal.bend`);
  - the spacing to each neighbour;
  - push-out, torque and pull-through loads against PEM's averages.

  Each check names its `sm-clinch-*` rule or the PEM bulletin it uses. It holds a cited subset of PEM's common S, SS, CLS, CLSS, FH, SO and BSO parts, and `parts_for()` lists the ones that clinch into a given sheet (#283).
