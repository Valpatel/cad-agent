**Fixed**
- `pcb-check` explains that reports missing severity metadata need regeneration with KiCad CLI 10 or newer and `--severity-all`, rather than asking KiCad 9 users to repeat a flag that cannot add the metadata. Incomplete reports still fail closed (#672).
