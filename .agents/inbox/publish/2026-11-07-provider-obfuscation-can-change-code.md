# Compare delivered code literals before accepting a publication

## Evidence — 2026-11-07 UTC

The independently reviewed ordinary-public campaign for #113 ran once against released main
`be4923818c4e2dc4c76ada4a869cdb11e724cfe1`:

```text
python3 /tmp/cad113-public-folders-owner.py \
  /tmp/cad113-public-folders-be492-manifest.json \
  240b1da7c8aa74e2b566a6d319214be7c342aa6b26814d875431cb7201ebfa3a \
  /tmp/cad113-public-folders-owner-be492-once /tmp/cad113-public-folders-be492-once
FAIL: authored main content/source/labels differ:
/repo/folders/d-software/d-cadagent/d-webkit/README
146 HTTP readbacks; 67 complete folder pages; 0 browser contexts.
Owned process reaped, cgroup quiescent; source/main unchanged; cleanup errors: [].
```

The first host's failing response was HTTP 200, `text/html`, `cf-cache-status: DYNAMIC`.
Three actual inline-code literals from the committed README—`three@0.160.0`, `mermaid@11.17.2`, and
`fflate@0.8.3`—were replaced with `/cdn-cgi/l/email-protection` links carrying `__cf_email__` and
`data-cfemail` attributes. Their visible text was `[email protected]`. The normalized diagram sources,
drawn labels and widths matched. The Markdown twin of the failed page, remaining pages and second host
were not reached; do not turn the partial read into a completed campaign.

- Failed receipt SHA256: `76792af750577b33ead52828bd225507975e6d55dc9e7994057ff2ad8b3e3df2`.
- Actual response `0145.body`: `7eb15021cca7ea200378ebfe299745cef0e7bbad8b66a9b240c99a3cf6024ea5`.
- Owner result: `3b4eb66ea499fd25a740c98c6211fc391b71e7c71c6f04bbfbb063496758158c`.
- [Independent actual failure classification](https://github.com/Valpatel/cad-agent/issues/113#issuecomment-6713683541).
- [Recoverable checker and retained preflights](https://github.com/Valpatel/cad-agent/issues/113#issuecomment-6713544801).

## Cause and corrective rule

The delivered transformation matches Cloudflare's documented email obfuscation format. Its account/zone
configuration was not inspected, so the raw response does not establish who enabled it or when.
[Cloudflare documents](https://developers.cloudflare.com/waf/tools/scrape-shield/email-address-obfuscation/)
the `<!--email_off-->` / `<!--/email_off-->` region exclusion. The shared page frame places this pair
around its complete authored body, outside the individual main/header/footer elements. This keeps the
fix in the versioned publisher and leaves compression, caching, CSP and other sites' settings alone.

The existing build consumer checks the pair on every generated owned HTML page, verifies the real
source package identifiers remain present, and rejects missing, duplicate, late or early guards. This
is a protocol-contract test, not a simulated Cloudflare service. Ordinary deployed readbacks still
decide whether the provider honors the exclusion.

Do not normalize altered code text away in a publication checker. A successful response, correct
revision footer or readable drawing cannot substitute for preserved authored instructions. Keep the
failed run immutable, review the changed publisher, and bind the next campaign to its actual release.

## Limits

The initial failure did not exercise application JavaScript, the provider's decode script or a second
host. No general browser failure, malicious interference, zone-setting diagnosis or broader cache-policy
acceptance follows from it. A locally present exclusion comment is not proof of a corrected public page.

[Publication incidents](README.md) · [Symptom index](../../SYMPTOM-INDEX.md)
