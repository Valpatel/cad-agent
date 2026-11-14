**New**
- SCADA equipment can expose a declared valve or motor toggle directly on the diagram, using the same adapter and inspector controls. Missing readings disable the action and read-only observers cannot command equipment.
- Wastewater, winery and brewery examples now include connected plant overviews, measurement taps, branch valves, PLC/remote I/O and focused views of the same model. Their documented normalized assumptions remain editable; valve isolation and PLC loss have tested downstream effects.

**Projects must change**
- Direct diagram controls are optional; existing system definitions retain their inspectors. Saved sessions for the previous wastewater, winery and brewery topologies are rejected without changing the current session. Start a new session for those expanded examples; no compatibility model or runtime alias is added.
