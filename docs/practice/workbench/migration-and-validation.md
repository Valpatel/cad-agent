# Migration and acceptance plan

**Design review.** Start with shared runtime distribution and contained-viewer
lifetime using current consumers. Then transfer SCADA into cad-agent with its
models, swappable equations, assets, examples, tools, tests and agent procedures.
No maintained file may rely on the old repository being online or installed.

Each implementation slice must have a bounded issue, independent review, portable
consumer evidence and a rollback path. Existing imports and frozen assembly
releases remain supported. The future PCB, electrical and harness viewers will
enter through the same tested boundaries without being presented as implemented.

[Design map](README.md)
