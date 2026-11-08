# Validate cache settings against the actual plan, then check delivery

## Evidence, 2026-11-07 UTC

The existing-user Wrangler refresh succeeded, while the exact cache-setting read still returned HTTP403.
The owner completed MFA in the normal browser. Read-only dashboard inspection showed a four-hour Browser Cache
TTL on both zones and no Cache Rules, Cache Response Rules or Page Rules. Authentication, endpoint permission,
configuration and delivered policy were separate observations; no credentials or account UI were published.

The unchanged ordinary consumer ran against released main `be4923818c4e2dc4c76ada4a869cdb11e724cfe1`:

```sh
node /tmp/cad-public-cache-acceptance.mjs /path/to/owned-release-checkout be4923818c4e2dc4c76ada4a869cdb11e724cfe1
```

All 18 bodies matched committed source. Both custom hosts failed the strict revalidation check on `fonts.css`
and the two WOFF2 files: their four-hour freshness policies lacked bare `no-cache`. All six Pages-host assets
passed. The before/after revision markers stayed exact. This retained failure was not a stale-byte failure.

The first independently reviewed operation attempted one host-only Page Rule per zone, with sole Browser Cache
TTL=0. The Enterprise-zone rule saved and read back as **Respect Existing Headers**. The Free-zone form rejected
its single save with **“Your plan allows for a minimum TTL of 120”**; cancelling left zero Page Rules. Writes
stopped, the planned both-rules-saved follow-up did not run, and the temporary release hold was lifted.
[Actual partial result](https://github.com/Valpatel/cad-agent/issues/381#issuecomment-6714347882).

A separately reviewed replacement used one Cache Rule on the Free zone: HTTPS, the exact cad-agent host and
exactly those three static font paths, with required cache eligibility and **Respect origin TTL** for the browser.
The before responses already reported `REVALIDATED` for those paths. No Edge TTL or other optional action was
added. One deployment saved; the actual edit form, enabled list and rule ID were read back through the ordinary
UI. [Independent saved-state review](https://github.com/Valpatel/cad-agent/issues/381#issuecomment-6714419068).
Private screenshots and IDs remain private; the durable issue records contain sanitized scope and evidence hashes.

## Cause and corrective rule

The [generic Page Rules schema](https://developers.cloudflare.com/api/resources/page_rules/) describes value0 as
Respect Existing Headers, but it did not establish that this operation would be accepted on the actual zone's
plan. The [plan table](https://developers.cloudflare.com/cache/how-to/edge-browser-cache-ttl/) distinguishes Page
Rules' two-minute Free-plan minimum from modern Cache Rules. Review the actual plan and current form, then record
the actual save result. Neither a schema nor a successful operation on another zone proves acceptance here.

When the supported alternative requires cache eligibility, match only the demonstrated static resources; do not
silently turn an entire host into cache-everything. Preserve exact predicates and every optional setting in the
review and saved readback. A rejected operation is not permission to increase TTL, change zone-wide defaults,
purge, broaden credentials or keep retrying.

Keep four claims separate: reviewed source policy, saved provider configuration, ordinary delivered bytes/policy,
and browser behavior. The existing emitted-header test requires `max-age=0`; the public consumer additionally
requires whole-response bare `no-cache` and `must-revalidate`, even if a downstream freshness value is positive.
Its two positive and seven negative policy controls remain unchanged. Do not mock a provider save in CI and call
it a production check. A versioned source update cannot evict an earlier response from a reader's browser.

## Limits

These observations establish the stated saved configuration, not public acceptance, global propagation or eviction
of existing visitor caches. Follow [#381](https://github.com/Valpatel/cad-agent/issues/381) for the separate ordinary
asset and focused-browser results. The replacement predicate also matches query variants of those exact paths;
the acceptance requests use ordinary URLs without cache busting. No purge or zone-wide default changed.

[Reusable verification rule](../../../docs/lessons/process/verify-from-source.md#verify-released-asset-bytes-as-well-as-the-version-marker)
