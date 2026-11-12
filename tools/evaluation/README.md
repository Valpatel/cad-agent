# Evaluation controllers

`standard_eval.py` prepares and grades the versioned analytical starter corpus. It does not run subject code while grading. See [design and testing](../../docs/practice/standard-evaluation.md).

```mermaid
flowchart LR
    J[tests/fixtures/evaluation/jobs] --> P[prepare]
    P --> W[fresh project directory]
    W --> G[grade / ingest-run]
    J --> G
```

## File ownership

| File | Purpose |
|---|---|
| [standard_eval.py](standard_eval.py) | Validate the corpus, prepare subject inputs, independently grade artifacts and ingest run metadata. |
| [runner.py](runner.py) | Start fresh Codex or Claude CLI conversations with version-bound context controls, collect transcripts and settle the owned process group before grading. |
