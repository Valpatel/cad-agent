# bd_warehouse e6ae6e7bae -> e6ae6e7bae (Apache-2.0)

Full scan of 124 files.
New findings (not in the reviewed baseline): HIGH 0, MEDIUM 10, LOW 0. Suppressed by baseline: 0.

## MEDIUM

| rule | file:line | text |
|---|---|---|
| dependency-file | `docs/requirements.txt:0` | `requirements.txt` |
| dependency-file | `pyproject.toml:0` | `pyproject.toml` |
| eval-exec | `src/bd_warehouse/fastener.py:162` | `# Before eval() is called the string, extracted from the csv file, is verified as safe` |
| eval-exec | `src/bd_warehouse/fastener.py:163` | `result = eval(measure)` |
| eval-exec | `src/bd_warehouse/flange.py:188` | `"""Evaluate if the given string is a fractional number safe for eval()"""` |
| eval-exec | `src/bd_warehouse/flange.py:196` | `# Before eval() is called the string extracted from the csv file is verified as safe` |
| eval-exec | `src/bd_warehouse/flange.py:197` | `result = eval(measure.strip().replace(" ", "+")) * IN` |
| eval-exec | `src/bd_warehouse/thread.py:60` | `"""Evaluate if the given string is a fractional number safe for eval()"""` |
| eval-exec | `src/bd_warehouse/thread.py:68` | `# Before eval() is called the string extracted from the csv file is verified as safe` |
| eval-exec | `src/bd_warehouse/thread.py:69` | `result = eval(measure.strip().replace(" ", "+")) * IN` |
