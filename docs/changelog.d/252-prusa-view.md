**New**
- `cad-agent prusa-view MODEL`: opens a 3MF or STL in PrusaSlicer's window with a private copy of the profile folder,
  so your own PrusaSlicer configuration is never read or written. Start-up has no dialogs (system info, updates,
  hints, the flatpak's certificate store), the window is large and the model is sliced as it loads, with the
  `cad.slicer` presets or `--config INI`. `--screenshot PNG` saves the window (X11/XWayland, ImageMagick `import`);
  `--close` or a later `--stop` stops only that view's own process, by PID, never other PrusaSlicer windows.
  `--view-bed WxD` shows a model larger than the printer on a viewing bed with no wipe tower, for looking at only
  (#252).
- Maintainer intake preserves the contributor's command and GUI evidence, folds its long reference, and binds
  shutdown to actual Prusa argv/start time with Linux pidfds instead of command-text substring matches (#252).
- Reject a work folder containing the model/config before cleanup, and honor requested shutdown after screenshot
  errors while retaining the original failure and separate cleanup diagnostics (#252).
