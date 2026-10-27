# Check each report's declared evidence rather than assuming one report schema

2026-10-26 browser review showed `STALE` for current CAN-routing and fabrication reports. The workbench had applied the PCB bundle checker to every `source_sha256` record; the bundle checker also requires `report_sha256`, which the independent measurements intentionally do not contain. The standalone report had the opposite gap: it trusted `pass: true` without checking source or exported-solid hashes.

Correction: shared cad-agent now verifies declared source, report, mechanical-source and artifact hash maps in one helper. Empty or invalid declared maps fail. Generic reports without a PCB bundle retain their proper state; changing a referenced source or STEP makes the result stale/failing. The PCB bundle still retains its additional contract. Regression tests exercise current and changed bytes in the workbench and standalone report.

Native KiCad `--save-board` writes the board after its DRC JSON. A second DRC on the saved bytes (without saving again) supplies a fresh report; touching a report timestamp would not establish that evidence. The project export sequence now encodes that order.

Limits: current hashes establish which bytes were reviewed, not the validity of a physical claim. Geometry evidence hashes the actual geometry helpers, keeping unrelated site/report code updates from invalidating otherwise unchanged solids.
