**Fixed**
- Diagram browser checks retain route, viewport, theme and pending-resource evidence when navigation fails, and release their owned contexts without disrupting another test lane. Real held-resource controls verify the diagnostics and cleanup; normal navigation limits are unchanged (#371).
