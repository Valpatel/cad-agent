## What and why

## How it was checked
- [ ] `python -m pytest -q` passes locally (with the extras this change touches)
- [ ] Tried on a real project (name it), with the evidence (render, report or JSON) linked or attached
- [ ] New docs or research pages, `cad-agent` commands, skills and agents have their line in `docs/areas.yaml` (or there are none)
- [ ] A CHANGELOG fragment in `changelog.d/` (see its README), or none needed: say why

## Effect on projects that use cad-agent
<!-- API or output changes that J501, Gyropup, the CAN boards or any other user project must follow. "None" is an answer. -->

## Supply chain
<!-- Adds a dependency, vendored file or catalogue entry? Paste the rows from
     python3 tools/resource_audit.py rows --base origin/dev --online
     (CI's supply-chain job looks for each added item's `id` here), plus a "can we drop it?" note for each new
     dependency. See skills/cad-supply-chain. "None" is an answer. -->

## Review
- [ ] Reviewed (by a person or a separate review agent) and every comment resolved
