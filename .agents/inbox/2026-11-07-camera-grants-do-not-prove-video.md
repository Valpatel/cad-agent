# Camera grants do not prove printer readiness or decoded video

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
