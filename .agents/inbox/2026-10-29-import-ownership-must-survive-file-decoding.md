# A delayed file import must not outlive its controls or replace a newer choice

On 2026-10-29 UTC, independent PR63 review deferred a real `File.text()` call after native file selection. Disposing the progress controls did not prevent the completed file from changing the tracker and localStorage. A second reproduction selected a newer false status, then released the older true import; the older result overwrote the newer choice. Existing synchronous import and browser tests had passed.

```text
before fix: stale selected file -> checklist false to true, saved state false to true
after fix: disposal/newer import -> checklist false, saved state false after old file resolves
author: Chromium and WebKit part-table browser suites PASS
reviewer: unchanged delayed-import probe PASS for disposal and newer selection
```

The correction owns each import with a generation and an explicit disposed flag. Recheck ownership after asynchronous file decoding and before touching the tracker, receipt or input reset. Dispose invalidates pending work. The permanent browser regression uses native file selection with deferred decoding, then checks both visible state and persisted state.

This covers the component's import lifecycle, not multi-user reconciliation or arbitrary storage corruption. See [part-state ownership](../domains/web-part-state.md).
