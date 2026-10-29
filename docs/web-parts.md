# Shared parts browser and build tracking

Implementation in progress for [issue 62](https://github.com/Valpatel/cad-agent/issues/62).

The webkit will provide reusable sortable part tables, browser-local build status, and direct interactive viewing of STL, STEP and 3MF files. Projects supply their own catalogs, images, engineering context and downloads. Checking a status box never places an order.

The table must preserve stable part identities through sorting and filtering, sort numbers numerically, retain unknown values, support keyboard and touch use, and explain whether state was saved. Exported state must identify its project and schema; invalid or unrelated imports must not overwrite current progress.

The viewer must display geometry from the selected original file, fit its bounds, support fine wheel/pinch zoom and orbit/pan, and retain an original-download link. Loading and parse failures must remain readable and recoverable. CAD parsing must not freeze the interface. Format, units and triangulation limitations belong in the integration documentation and evidence.

Acceptance evidence includes generic fixtures, actual project files, narrow/landscape layouts, numeric/text sorting, persistence and import/export, malformed/stalled responses, invalid geometry, and the existing viewer/packaging checks. CAD display does not certify fit, manufacturability or physical safety.

This feature is developed on `feat/web-parts`, targeting `dev`. Gyropup may test the feature worktree while its PR is open, following CONTRIBUTING.md. Toolkit integration and release still follow the repository's review and explicit merge-instruction rules.
