**New**
- Validate finite ordered assembly-guide paths through the existing insertion engine, with captured guide/mesh hashes and a BREP export binding. Reports retain blocked and undecided pairs and explicitly leave support, retention and physical assembly unverified (#512).

**Fixed**
- Assembly insertion sweeps retain an explicitly unchecked geometry relation as an unchecked failure, including at the final pose (#512).
