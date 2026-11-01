**New**
- `cad-agent optimise`: `search.confirm` evaluates the first `top` feasible trials again at a higher fidelity once the
  trials are done, with `args` appended to the evaluator's command (`[--mesh, "3"]`) or its own `evaluator`. The
  leaderboard ranks each confirmed trial on its confirmed values and keeps the screening values beside them (`confirm`
  in `leaderboard.json`, a Confirmed column on the page). It flags a change of more than `tolerance_pct` (default 5 %)
  in an objective or constraint, a trial that becomes feasible or infeasible, and a confirmation that fails.
  Confirmations are kept in `confirm.jsonl` and reused while the confirm evaluator is unchanged; `--no-confirm` skips
  the stage for one run (#144, [docs/explore.md](docs/explore.md#confirm-the-leaders)).
- Command evaluators: `{result}` in the argv is a file path the evaluator writes its JSON reply to, read after the
  command exits, so output that native code writes to fd 1 (gmsh, from C) can no longer corrupt the reply. Without
  `{result}`, stdout is read as before (#144).

**Changed**
- `cad-agent catalogue`, `compare` and `optimise` run without a catalogue when no slots are declared: a search that
  changes only parameters needs none, and each design's BOM is empty. With slots and no catalogue it is still an error,
  which now names the slots. When no design has a BOM line, the always-0 cost and mass are left out of the comparison's
  columns unless they are objectives or constraints (#144).

**Projects must change**
- Nothing is required. A command evaluator that runs gmsh, OpenCASCADE or a solver should take `{result}` and write its
  JSON there in place of an `os.dup2` workaround, and a parameter-only project can delete the empty catalogue file it
  kept only to satisfy `cad-agent` (#144).
