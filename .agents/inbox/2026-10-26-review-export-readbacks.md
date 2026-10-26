# Render the exported assembly readback to check the deliverable

2026-10-26: the direct in-memory lid render displayed adjacent CAN0/CAN1 text despite 42 mm label centers. STEP readback listed first-label letter bounds X21.04…29.93 and second-label bounds X63.04…71.85; rendering that readback restored the expected separated labels. Exported enclosure solids were not changed by this presentation correction.

Cause is limited to observed rendering/triangulation state; the exact upstream defect was not reproduced conclusively. Corrective rule: use exported STEP readbacks for final review images and compare visible placement to model coordinates. `tools/render_review.py` imports fresh STEP geometry for each scene and uses the shared cad-agent Renderer. Limits: image correctness does not prove physical fit, and this observation does not establish a general CadQuery or OCCT failure.
