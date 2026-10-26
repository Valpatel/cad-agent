# Package the validated public manifest, not every file beside a design

2026-10-26: local versus clean-checkout ZIP comparison found only `hardware/2port/thor-2port.kicad_prl` and its four-port equivalent in local PCB packages. All published CI packages came from clean checkouts and excluded these local UI settings. Both contexts passed source validation because the settings were correctly Git-ignored; the package glob itself was too broad.

Cause: recursive folder globbing followed a suffix denylist that missed KiCad local state. Corrective rule: release membership must come from the validated public manifest. Filter package candidates through that allowlist and compare member hashes/whole-package hashes from a clean checkout. Limits: hashes establish byte identity, not hardware qualification or suitability for manufacture.
