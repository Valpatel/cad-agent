**Fixed**

- Audit the separate maintainer-only Mermaid security build context with the same source, integrity, advisory, install-script and PR-row checks as the site dependency context. Production site installation remains separate.
- Rebuild the existing Mermaid11 core with fixed DOMPurify3.4.17 and non-deprecated KaTeX0.18.10, with reproducible inputs, original upstream hash and full emitted dependency notices. Preserve the strict browser API and verify real math labels in both browser engines; no Mermaid12/ELK migration is introduced.
