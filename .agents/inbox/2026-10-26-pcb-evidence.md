# Clean PCB connectivity does not establish schematic parity or product qualification

2026-10-26 evidence from the Thor breakout: first routed KiCad10 reports showed zero unconnected items but100/131 schematic parity warnings. PCB net names lacked the schematic's root `/` namespace; NC pads had no corresponding isolated net; footprint fields were missing. Netlist-based synchronization and board-only mount attributes closed parity. Later exact connector pad updates changed clearances, requiring fresh DRC despite the same nominal connector family.

Cause: treating routed connectivity as the complete electrical verification contract, and treating generic footprint names as sourcing evidence.

Rule: run ERC, all DRC severities, unconnected checks and schematic parity; bind reports to current source hashes; keep physical fit, protection and sourcing as separate gates. Never approve an exact replacement from pitch or category alone. Include manufacturer identity and full supplier code, audit drawings, then rerun electrical and mechanical checks.

Evidence adapters and regressions: `src/cadagent/pcb.py`, `tests/test_pcb.py`; site freshness regression in `tests/test_site.py`. The adapter cannot prove a report's generation history and does not replace a build orchestrator or independent electrical review.
