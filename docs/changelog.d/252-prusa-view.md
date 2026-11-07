**New**
- `cad-agent prusa-view MODEL`: opens a 3MF or STL in PrusaSlicer's window with a private copy of the profile folder,
  so your own PrusaSlicer configuration is never read or written. Start-up has no dialogs (system info, updates,
  hints, the flatpak's certificate store), the window is large and the model is sliced as it loads, with the
  `cad.slicer` presets or `--config INI`. `--screenshot PNG` saves the window (X11/XWayland, ImageMagick `import`);
  `--close` or a later `--stop` stops only that view's own process, by PID, never other PrusaSlicer windows.
  `--view-bed WxD` shows a model larger than the printer on a viewing bed with no wipe tower, for looking at only
  (#252).
