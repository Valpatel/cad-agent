**Changed**
- SCADA equipment displays its stable unique ID in the diagram and equipment pickers, and inspection no longer leaves a persistent pressed selection fill (#729).
- Equipment inspection opens compact screen-space quick controls beside the equipment. Detailed readings and host model settings are an explicit second level, preserving the diagram for routine operation (#729).

**New**
- Explorer equipment settings show the actual active equation provider or built-in kernel implementation, contract units and accepted configuration beside editable parameters (#729).

**Projects must change**
- `ScadaViewer.openInspector()` now opens nonmodal quick controls; use `openDetails()` for the complete native inspector, or supply `onDetails` to open host-owned model settings (#729).
