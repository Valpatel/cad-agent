**Fixed**
- The file-viewer browser check measures the two-second Cancel deadline from the user's pointer input to both the cancelled state and worker termination, so a slow test runner can still verify a responsive viewer (#802).
