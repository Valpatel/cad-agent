**New**
- `python3 tools/resource_audit.py references`: the reference registry's link health, with no AI. It sends conditional requests (ETag, Last-Modified), hashes each page's normalised visible text, finds soft-404s by rule, reads GitHub repository metadata (gone, renamed, archived, last push, licence, default-branch head), sends at most one request a second to any host, leaves a host that answers 401 or 403 alone for 30 days, and rotates through the records (400 a run, the longest unchecked first) (#323).
- The weekly supply-chain workflow runs it on `dev`, with lychee for every link in the published Markdown (anchors and files included). It keeps one issue, "Reference health: open findings", and opens one bot PR into `dev` with the evidence changes its rules allow (`tools/references_health_apply.py`) (#323).
- Link health stays out of git (#323, Q5). It lives in the workflow's `references-health` artifact. A site build given that file (`CAD_AGENT_REFERENCES_HEALTH`) adds each record's `health` to `catalog/references/*.json` (#323).

**Changed**
- Registry records may carry `evidence.lowered` (`from`, `date`, `why`). The weekly bot PR writes it when a record's link stays dead for two checks and its evidence class falls one rung. `--check` validates it (#323).
