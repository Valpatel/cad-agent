# Reduced P1S included-template fixture

`profiles.json` preserves the real P1S 0.4 profile's parent/include graph from
installed Bambu Studio 02.08.04.57, inspected 2026-10-31. It contains only names,
dependency declarations and three relevant heater commands, extracted from the
original files. `source-hashes.json` identifies those original bytes. These are
test data, **not runnable printer profiles or a complete startup program**.

The inherited generic start waits at 205°C. The included P1S start template uses
the initial-layer bed and nozzle temperature variables. This catches the actual
regression without copying the full upstream G-code programs or requiring Bambu
Studio in core CI. Precedence tests add independently authored conflicting keys.
The optional installed-profile test separately checks the complete real template.

Source: Bambu Studio's `resources/profiles/BBL/machine` files and
[profile resolver](https://github.com/bambulab/BambuStudio/blob/79df7ae309be398ed30c9f397c13c9911c2edc57/src/libslic3r/PresetBundle.cpp#L4858-L4916).
