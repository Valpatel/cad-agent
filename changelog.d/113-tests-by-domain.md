**Changed**
- `tests/` is grouped by domain: each test sits in `tests/<domain>/`, the folder named after the
  `src/cadagent/<domain>/` package it tests, or in `tests/cli/`, `tests/site/` (the website and its build) or
  `tests/repo/` (the repo's own rules and tooling); design exploration's are in `tests/simulation/explore/`. File
  names are unchanged, and `git log --follow` keeps each file's history. The same tests are collected and pass. Every folder has a README with a map, and `tests/README.md` lists
  them (#113).
- `tests/repo/test_layout.py` checks where files go. It fails on a test file directly in `tests/`, a `tests/` folder
  that is neither a package nor a listed area, a new top-level folder in the repo, a new file at the top of `src/` or
  `src/cadagent/`, and a folder newly over 20 files. Each failure names the folder the file belongs in. The folders
  over 20 files today (`docs/`, `tools/`, `src/cadagent/webkit/`) are on a list that may only shrink (#113).
- `AGENTS.md` has a "Repo structure and where files go" section with the growth rule: split a folder when it gets
  cluttered, not before, with a README and map for each new folder. `CONTRIBUTING.md` has a "Where files go" table.
  The `cad-pr-reviewer` agent and the `cad-pr-review` skill check structure and sprawl, so projects that install the
  kit get the same check against their own map (#113).

**Projects must change**
- If a project or CI job runs cad-agent's tests by file path, add the domain folder:
  `tests/test_fea.py` is now `tests/simulation/test_fea.py`, and `tests/webkit-*.test.mjs` is now
  `tests/webkit/webkit-*.test.mjs`. `tests/README.md` lists every folder. Running `pytest tests` or `npm run test:*`
  works as before.
- Code that imports a test module as a helper takes the new module path: `tests.test_report` is now
  `tests.publish.test_report` (#113).
