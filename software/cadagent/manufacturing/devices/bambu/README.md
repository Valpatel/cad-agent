# Bambu observations

Reuse a normal account session to list owned printers or ask one printer for current status and firmware.
No background service, login prompt, automatic refresh/retry, camera reader or physical control is started.

```bash
cad-agent bambu-status
cad-agent bambu-status --device DEVICE_ID
```

The first command makes two HTTPS GETs and prints local device identifiers. The second repeats the ownership
check, subscribes to the selected printer, then sends exactly one `pushall` and one `get_version` request. A
retained heartbeat or unmatched firmware reply cannot complete the observation. Output is local account data;
do not paste device identifiers into public issues.

The adapter reads the existing owner-only POSIX session at
`$XDG_STATE_HOME/cad-agent/manufacturing/bambu/session.json` (default `~/.local/state/...`), or `--session`.
It requires the `cad-agent.bambu-session/1` format with the genuine access-token expiry, global-cloud origin,
and account identity. It never reads Bambu Studio's profile. Missing or expired sessions need normal sign-in;
this command does not implement account login or Windows credential storage.

MQTT requires the optional `bambu` extra (Paho MQTT 2.1 or newer). HTTPS listing uses the standard library.
Imports do not connect, install dependencies, or load credentials. Both transports verify TLS. The default
MQTT response wait is 30 seconds after connection; socket connections/HTTP have separate timeouts and OS DNS
resolution is outside that wait. Use a supervising process if a hard overall deadline is required.

The [dated connection evidence](../../../../../docs/research/manufacturing/bambu-cloud.md) distinguishes
the earlier actual printer observations from this adapter's tests. State/firmware do not establish a clean
bed, usable camera or successful printing. Other regions and hardware controls are not implemented.

| File | Purpose |
|---|---|
| [cloud.py](cloud.py) | Session loading, fresh ownership checks, and one selected printer's status/version query. |
| [__init__.py](__init__.py) | Package namespace. |
