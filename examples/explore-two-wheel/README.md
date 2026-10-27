# Example: comparing two-wheel-legged robot configurations

A worked example of cad-agent's design-exploration framework ([`docs/explore.md`](../../docs/explore.md)). A small
robot that balances on two wheels and crouches on two legs is put together from a catalogue: wheel motors, leg
actuators, a battery, a computer, an optional camera. Four designs are compared on cost, mass and runtime, under two
constraints (top speed and the lean the wheels can still catch), and a search looks for better combinations.

```bash
pip install -e "../..[dev]"          # in this folder; optuna too for the nsga2 sampler: pip install -e "../..[explore]"
cad-agent catalogue                  # 12 parts, 0 errors, 1 warning (the depth camera has no price)
cad-agent compare --swaps --open     # exports/explore/compare.html
cad-agent optimise                   # 60 random trials: exports/explore/search/leaderboard.html
cad-agent optimise --sampler grid --fresh    # all 270 combinations
```

![The comparison page: the trade-off chart of cost against mass with the Pareto front, and the leaderboard](compare.png)

| File | What it is |
|---|---|
| `cad-agent.yaml` | the `explore:` section: catalogue, slots, objectives, constraints, the evaluator and the search space |
| `catalogue/*.json`, `*.yaml` | the parts, in two JSON files (with per-file `defaults`) and one YAML file |
| `designs/standard.json` | the middle of the range; `light`, `long-range` and `strong` extend it |
| `tools/evaluate.py` | the evaluator: textbook estimates of top speed, catchable lean, leg torque margin and runtime, voltage checks, and a BOM line for the printed parts |

What it shows:

- **Light** and **Standard** are the Pareto front: Light is the cheapest and lightest, Standard runs longest.
- **Strong** is feasible but dominated: Standard costs less, weighs less and runs longer.
- **Long range** fails: its 13S pack charges to 54.6 V, more than its wheel motors (48 V), leg actuators (52 V) and
  computer (48 V) accept. Its cost is shown as `≥` because the depth camera has no price. Its swap table shows that
  the 10S pack fixes it, at the price of some runtime.

## The numbers

Every part in this example is **illustrative**: made-up but plausible numbers for generic parts, not the specs or
prices of real products, so every item is marked `"confidence": "estimate"` and the price-age check is turned off.
The evaluator's formulas are rules of thumb, not a robot model. A real project lists real parts with their datasheets
and shops in `sources` and `buy`, the date each price was checked, and its own evaluator.
