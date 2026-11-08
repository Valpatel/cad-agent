# Camera grants do not prove printer readiness or decoded video

## Reusable adapter observation, 2026-11-08 UTC

The adapter at `f822af4456a6f141584f675122367ea61535390c` completed one independently reviewed live trial,
01:22:08–01:22:12 UTC, using the existing owner-only cached session without a verification email. The bounded
invocation `python3 cad405-live-observer-f822.py <private-output>` used script SHA-256
`c254f86788b5c3fc2b2649c26e421986ddda03345f2b089ced099a17dd4abcf1`. P1S and X1E each returned fresh observed
state and a matching firmware reply after exactly two status/version publications. The owned unit exited 0;
source remained clean and the private cache-preservation check passed. The reviewer inspected filtered results,
not credentials ([actual acceptance](https://github.com/Valpatel/cad-agent/issues/405#issuecomment-6715577418)).

Keep this scope separate from a complete pushall snapshot, camera/bed assessment, motion or job submission.
There was no retry, camera or physical command. The earlier prototype results and failures below are preserved.

**Date:** 2026-11-07 UTC. **Tracking:** [#405](https://github.com/Valpatel/cad-agent/issues/405).

## Evidence

The following separately reviewed one-shot probes used normal account credentials, verified TLS and installed libraries. Commands refer to private experimental scripts, not shipped cad-agent commands. Credentials, owned-device identifiers, camera images and unredacted reports remain private; the public record contains outcomes only.

| Command / reviewed source SHA-256 prefix | Actual result |
|---|---|
| `python3 login_once.py` / `435e6730c1c6` | Normal login, email verification and owned-device GET each HTTP 200; two devices. |
| `python3 capabilities_once.py` / `f783255f4ad0` | 04:11: one pushall and one version request per device. Both fresh nonretained states and sequence-matched version replies received. |
| `python3 read_camera_grant_once.py` / `9565faa671f2` | 04:24: P1S native reader exited 0; actual JPEG independently verified and fully decoded, 1280 × 720, 72,570 bytes. |
| `python3 read_x1e_camera_grant_once.py` / `942c56253dbc` | 04:29: X1E open returned -90; zero samples and no decoded frame despite HTTP 200 grant. |
| `python3 observe_x1e_camera_once.py` / `31b98b3dfe6b` | 04:48: authenticated MQTT, one pushall, one HTTP 200 grant. Nonretained `liveview.prepare` reply exactly matched the private grant identifier: `result: fail`, `err_code: 84033543`. Baseline/final TUTK state disabled. Reader not started. |
| `python3 fresh_sdk_camera_once.py` / `96a93704d7a2` | 04:52: isolated installed SDK accepted `change_user` call (0), but `is_user_login` was false. Connect, subscription and camera APIs were never invoked. Unknown account and refresh-expiry fields were omitted, not invented. |

The P1S frame SHA-256 is `4c08ad870fba6d6d592033d409778d643e640c31e6350608cf764523bd553cb9`. A digest preserves identity without publishing the workspace image.

Two earlier passive-status probes remained partial: one parser missed nested X1E chamber data; the corrected parser then saw only empty X1E heartbeats. Neither was promoted to a complete state. The explicit snapshot/version operation established the stronger claim.

## Cause and corrective rule

Cloud authentication, owned-device discovery, telemetry, grant issuance, printer preparation and image decode are separate stages. Reusing the success flag from an earlier stage hides real failures. Match replies to the requested device and request identity, require nonempty fresh evidence, and keep incomplete outcomes visible.

The correlated camera observation isolates X1E failure at preparation. It does **not** establish the reason for rejection. Decimal error values alone are unsafe to interpret across model/command namespaces: the pinned official error tables do not provide a consistent camera-specific meaning for `84033543`. The owner's working official-app video also rules out a blanket claim that the camera is broken.

Run native SDK work in a bounded child with private output. A parent timeout must kill and reap the actual child. An independent no-network alarm control caught a nested-wrapper orphan risk before execution; using the reviewed reader in the same Python process removed that boundary. A successful local SDK setter is not successful authentication.

## Limits and reuse

No motion, heaters, settings, certificate installation or print-start commands were issued. The observations do not qualify autonomous printing or empty-bed detection. The SDK's earlier HTTP-0 / return--11 result had an unknown cause; it did not prove expired credentials. Later fresh-session failure likewise did not reach the cloud request stage.

The reusable method and inspected upstream skills are in [Bambu cloud research](../../docs/research/manufacturing/bambu-cloud.md); the general rule is in [verification and evidence](../../docs/lessons/review/verification-and-evidence.md#prove-each-stage-of-an-external-connection). Exact private scripts/results are retained outside the repository for the current account holder; another machine must use normal sign-in.

## An explicitly invalid selector must not become a broader observation

On 2026-11-08 UTC, independent review of [PR489](https://github.com/Valpatel/cad-agent/pull/489) at
`fbe3f5d54ec7c75103fbd344ac69ad995400bcf8` exercised `cad-agent bambu-status --device ''` with a synthetic
session and owned-device provider. It returned exit 0 and the printer list: `if args.device` treated an explicitly
supplied empty selector as though the option had been omitted. No live account request was needed to reproduce it.

The dispatcher now distinguishes absence with `args.device is not None`, leaving the actual observer's identity
validator to reject an empty value. `test_explicit_empty_selector_is_not_an_owned_printer_listing` runs the real
CLI/observer validation, requires exit 2 and no stdout, and fails if ownership listing is reached. The focused
consumer run after correction passed 40 tests with one optional Paho skip; installed-Paho setup was checked
separately without a connection. This establishes the selector boundary, not live transport or printer acceptance.

The same review also tested a synthetic cache at `link/sub/session.json`, with `link` an intermediate symlink.
It loaded successfully although the initial docstring broadly claimed symlinks were not followed. `O_NOFOLLOW`
on the opened parent protects that final parent entry, not every ancestor used to resolve it. The implementation
retains final-directory/file descriptor, ownership and mode checks; documentation now names that exact boundary,
and a regression distinguishes an allowed intermediate ancestor from a rejected final-parent link. No cross-user
read was demonstrated. Describe the actual credential-path contract rather than generalizing a flag's name.
