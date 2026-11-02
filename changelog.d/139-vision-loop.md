**Changed**
- `docs/vision.md` now opens with the long-term loop (#139). Agents using cad-agent on real projects send evidence.
  Maintainer agents review it, fit it to the structure and credit the author. Releases rebuild the site and indexes
  by themselves. Two measures, the fewest tool calls and tested knowledge rather than trained knowledge, show whether
  the loop is working.
- CONTRIBUTING.md: the `main` "gate" legend now says that `ci_gates.py all` checks only the three `cad-gates` rows, so
  confirm the browser runs with `gh pr checks` (#112).
