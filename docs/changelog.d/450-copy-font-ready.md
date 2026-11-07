**Fixed**
- Copy buttons defer font-ready measurement to the next frame, avoiding geometry writes during resize delivery. Browser checks now observe window ErrorEvents as well as Playwright errors and exercise the font-ready scheduling boundary (#450).
- Full CI reports active test IDs and dumps threads for a slow test, preserving its complete test selection and 30-minute job cap (#463).
