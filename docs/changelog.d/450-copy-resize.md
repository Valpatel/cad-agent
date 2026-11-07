**Fixed**
- Copy-button layout updates coalesce outside ResizeObserver delivery, preventing the observer-loop error reproduced by the existing late-stylesheet consumer. Copy and navigation-resize checks now retain unfiltered runtime errors alongside their geometry checks (#450).
