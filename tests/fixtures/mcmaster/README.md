# McMaster-Carr page fixtures

Hand-written pages for `tests/mechanical/test_mcmaster.py`, so the tests never fetch McMaster-Carr. Neither page is copied
from mcmaster.com; each holds only the text the code looks for.

```mermaid
flowchart TD
    F["login-gate.html<br/>not-a-product.html"] --> E["mcmaster.page_error<br/>the text a reader sees"]
    E -->|"login prompt"| L["LoginRequired<br/>the part number may be fine"]
    E -->|"no prompt"| N["RuntimeError<br/>no specification table"]
    classDef here fill:#fffdf5,stroke:#173d3c,color:#173d3c
    classDef out fill:#ffe1cc,stroke:#bd3a12,color:#173d3c
    class F,E here
    class L,N out
```

| File | What it is |
|---|---|
| `login-gate.html` | The prompt McMaster showed in place of a product page on 2026-10-31 ("Log in to view Product Detail"), split across tags and spaces, with a header "Log in" link and a script string |
| `not-a-product.html` | No specification table and no prompt a reader sees: the header "Log in" link, and the phrase only in a script, a hidden login dialog, `aria-hidden` and `display: none` elements and a textarea, none of which may count |
