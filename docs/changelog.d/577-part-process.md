**New**
- A per-part manufacturing process, so a project that mixes printed parts with welded, cut, machined, moulded or bought ones is checked honestly. A dossier card's `material.process` (free text, such as `welded steel tube` or `purchased`) or the new `cad: part_process: {<part>: <process>, "*": <default>}` in `cad-agent.yaml` says how a part is made (`cadagent.manufacturing.process.part_processes`; names `weldment`, `purchased`, `sheet-metal`, `cnc`, `injection-moulding`). A part that is not printed gets skip rows with the reason in the report's "Printed parts" and "Print files" (never a pass), and `export-3mf`, the default build plates, the default slice list, `cad-agent overhangs` and the report's download table leave it out, so `cad-agent all` finishes on a machine with no printed part. A skip means the print checks do not apply; it does not say the part can be made ([toolkit.md](../toolkit.md#parts-that-are-not-printed), #577).

**Changed**
- A dossier card whose `material.process` already names a non-additive process (for example `CNC` or `sheet metal`) now gets skip rows in "Printed parts" and "Print files" instead of print checks, and no 3MF, plate place or default slice row (#577).

**Fixed**
- A partial `overhangs PART` run discards old results for parts that are no longer printed, even when their STL bytes are unchanged. An explicitly named nonprinted part is still screened afresh; it is not silently carried into later partial runs (#577, #580).

**Projects must change**
- Nothing for a project that declares no process: every part is printed, as before. A project that wrote a non-additive `material.process` on a card and still prints that part corrects the card's process (the card is read before `cad: part_process:`) (#577).
