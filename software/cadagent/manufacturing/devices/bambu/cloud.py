"""Reuse a private session and observe an explicitly selected owned printer.

No login prompt, token refresh, camera, motion, settings or job submission is performed.
The two MQTT publications are the standard pushall/get_version observations. Their
source is BambuStudio 355d71eee5a9ebc794693fe57e63674806019770, DeviceManager.cpp
lines 1299–1401. A fresh status is not evidence of an empty build plate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import importlib
import json
import math
import os
from pathlib import Path
import re
import ssl
import stat
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener
import uuid

_ORIGIN = "https://api.bambulab.com"
_PROFILE = "/v1/design-user-service/my/preference"
_DEVICES = "/v1/iot-service/api/user/bind"
_MAX_BYTES = 2_000_000
_SERIAL = re.compile(r"[A-Za-z0-9_-]{5,64}\Z")
_UID = re.compile(r"[0-9]{1,30}\Z")
_NUMERIC_STATUS = (
    "mc_percent", "mc_remaining_time", "layer_num", "total_layer_num",
    "bed_temper", "bed_target_temper", "nozzle_temper", "nozzle_target_temper",
    "chamber_temper",
)


class CloudError(RuntimeError):
    """A sanitized local, authentication or transport failure; never a raw response."""


@dataclass(frozen=True)
class CloudSession:
    """An existing global-cloud session. Secrets and account identity have no repr."""

    access_token: str = field(repr=False)
    user_id: str = field(repr=False)
    expires_at: datetime

    def validate(self) -> None:
        if (not isinstance(self.access_token, str) or not self.access_token
                or len(self.access_token) > 32_768
                or any(ord(c) < 33 or ord(c) > 126 for c in self.access_token)):
            raise CloudError("invalid access token")
        if not isinstance(self.user_id, str) or not _UID.fullmatch(self.user_id):
            raise CloudError("invalid account identity")
        if (not isinstance(self.expires_at, datetime) or self.expires_at.tzinfo is None
                or self.expires_at <= datetime.now(timezone.utc)):
            raise CloudError("cached session expired; use normal account sign-in")


@dataclass(frozen=True)
class OwnedPrinter:
    device_id: str = field(repr=False)
    model: str


def load_session(path: Path | None = None) -> CloudSession:
    """Read our existing owner-only POSIX cache; never read a slicer's profile.

    The final directory and file are opened without following their own symlinks;
    their descriptors bind the ownership/mode checks to the objects read. Earlier
    ancestors use normal OS path resolution and may include symlinks. The cache
    is not rewritten/refreshed and passwords are neither needed nor read.
    Windows ACL-based storage needs its own implementation; it is not inferred
    from POSIX mode bits.
    """
    if os.name != "posix":
        raise CloudError("private session-file loading currently requires POSIX")
    if path is None:
        root = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
        path = root / "cad-agent/manufacturing/bambu/session.json"
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise CloudError("session path must be absolute without parent traversal")
    parent_fd = file_fd = None
    try:
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        parent = os.fstat(parent_fd)
        if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) & 0o077:
            raise CloudError("session directory must be owned by this user and private")
        file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
        info = os.fstat(file_fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > _MAX_BYTES):
            raise CloudError("session file must be a private owned regular file within size limit")
        with os.fdopen(file_fd, "rb") as handle:
            file_fd = None
            raw = handle.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            raise CloudError("session file exceeds size limit")
        data = json.loads(raw)
        if (not isinstance(data, dict) or data.get("format") != "cad-agent.bambu-session/1"
                or data.get("api_origin") != _ORIGIN or data.get("region") != "global"):
            raise CloudError("unsupported session format or cloud region")
        tokens, profile = data["tokens"], data["profile"]
        duration = tokens["expiresIn"]
        if type(duration) is not int or not 0 < duration <= 366 * 86400:
            raise CloudError("invalid session expiry")
        received = datetime.fromisoformat(data["received_at_utc"])
        if received.tzinfo is None or received > datetime.now(timezone.utc):
            raise CloudError("invalid session receipt time")
        session = CloudSession(tokens["accessToken"], profile["uidStr"], received + timedelta(seconds=duration))
        session.validate()
        return session
    except CloudError:
        raise
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        raise CloudError("cannot read a valid private cached session") from None
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if parent_fd is not None:
            os.close(parent_fd)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CloudError("cloud redirect refused")


def _get(session: CloudSession, path: str) -> dict:
    session.validate()
    if path not in {_PROFILE, _DEVICES}:
        raise CloudError("unsupported cloud observation endpoint")
    request = Request(_ORIGIN + path, headers={
        "Authorization": "Bearer " + session.access_token,
        "User-Agent": "cad-agent (owned-printer observation)", "Accept": "application/json",
    })
    opener = build_opener(_NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(request, timeout=10) as response:
            if response.status != 200:
                raise CloudError("cloud observation did not return HTTP 200")
            raw = response.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            raise CloudError("cloud response exceeds size limit")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise CloudError("cloud response is not an object")
        return value
    except HTTPError as exc:
        raise CloudError(f"cloud observation returned HTTP {exc.code}") from None
    except (URLError, OSError, ValueError):
        raise CloudError("cloud observation failed; no automatic retry") from None


def owned_printers(session: CloudSession) -> tuple[OwnedPrinter, ...]:
    """One identity GET and one owned-device GET; cached ownership is not trusted."""
    profile = _get(session, _PROFILE)
    uid = profile.get("uid")
    if isinstance(uid, bool) or not isinstance(uid, (int, str)) or str(uid) != session.user_id:
        raise CloudError("cloud account does not match the cached session")
    devices = _get(session, _DEVICES).get("devices")
    if not isinstance(devices, list) or len(devices) > 1000:
        raise CloudError("invalid owned-printer list")
    result, seen = [], set()
    for item in devices:
        if not isinstance(item, dict):
            raise CloudError("invalid owned-printer entry")
        serial, model = item.get("dev_id"), item.get("dev_product_name")
        if (not isinstance(serial, str) or not _SERIAL.fullmatch(serial) or serial in seen
                or not isinstance(model, str) or not 0 < len(model) <= 128):
            raise CloudError("invalid or duplicate owned-printer identity")
        seen.add(serial)
        result.append(OwnedPrinter(serial, model))
    return tuple(result)


def status_fields(value: object) -> dict:
    """Keep observed status fields, including official chamber V2 packed temperatures."""
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in _NUMERIC_STATUS:
        number = value.get(key)
        try:
            if type(number) in (int, float) and math.isfinite(number):
                result[key] = number
        except OverflowError:
            continue
    state = value.get("gcode_state")
    if isinstance(state, str) and state.strip() and len(state) <= 32:
        result["gcode_state"] = state
    device = value.get("device")
    ctc = device.get("ctc") if isinstance(device, dict) else None
    info = ctc.get("info") if isinstance(ctc, dict) else None
    packed = info.get("temp") if isinstance(info, dict) else None
    if type(packed) is int and 0 <= packed <= 0xffffffff:
        for key, number in (("chamber_temper", packed & 0xffff),
                            ("chamber_target_temper", packed >> 16)):
            if number != 0xffff:
                result[key] = number
    return result


def observe(session: CloudSession, device_id: str, *, wait_seconds: float = 30) -> dict:
    """Read fresh status and a correlated firmware reply for one owned device.

    Uses optional paho-mqtt 2.x, with verified TLS, no reconnect, no background
    thread and no application retry. ``wait_seconds`` bounds the MQTT event wait
    after connection; HTTPS and connection each have their own socket timeouts.
    DNS resolution is OS-managed. Callers needing a hard wall deadline should
    supervise the process. Failure/timeout raises a sanitized CloudError.
    """
    if (type(wait_seconds) not in (int, float) or not math.isfinite(wait_seconds)
            or not 0 < wait_seconds <= 60):
        raise CloudError("MQTT wait must be finite and between 0 and 60 seconds")
    if not isinstance(device_id, str) or not _SERIAL.fullmatch(device_id):
        raise CloudError("invalid requested printer identity")
    session.validate()
    try:
        mqtt = importlib.import_module("paho.mqtt.client")
        api = mqtt.CallbackAPIVersion.VERSION2
    except (ImportError, AttributeError):
        raise CloudError("status observation needs paho-mqtt 2.x (cad-agent[bambu])") from None
    printers = owned_printers(session)
    printer = next((p for p in printers if p.device_id == device_id), None)
    if printer is None:
        raise CloudError("requested printer is not owned by this account")
    report_topic = f"device/{device_id}/report"
    sequence = str(uuid.uuid4().int % 1_000_000_000)
    result = {"model": printer.model, "status": {}, "firmware_modules": [],
              "fresh_state_received": False, "version_reply_matched": False,
              "publish_count": 0, "received_at_utc": None}
    started = connected = False
    subscription_mid = None
    client = mqtt.Client(api, client_id="cad-agent-observe-" + uuid.uuid4().hex[:16],
                         clean_session=True, reconnect_on_failure=False)

    def on_connect(c, userdata, flags, reason, properties):
        nonlocal connected, subscription_mid
        if connected or reason.is_failure:
            raise CloudError("MQTT connection refused or unexpectedly repeated")
        connected = True
        rc, subscription_mid = c.subscribe(report_topic, qos=0)
        if rc != mqtt.MQTT_ERR_SUCCESS:
            raise CloudError("MQTT subscription could not be sent")

    def on_subscribe(c, userdata, mid, reasons, properties):
        nonlocal started
        if (not connected or started or mid != subscription_mid or len(reasons) != 1
                or any(reason.is_failure for reason in reasons)):
            raise CloudError("MQTT subscription acknowledgement invalid or repeated")
        started = True
        queries = (
            {"pushing": {"sequence_id": str(int(sequence) + 1), "command": "pushall",
                         "version": 1, "push_target": 1}},
            {"info": {"sequence_id": sequence, "command": "get_version"}},
        )
        for query in queries:
            result["publish_count"] += 1
            published = c.publish(f"device/{device_id}/request", json.dumps(query), qos=0, retain=False)
            if published.rc != mqtt.MQTT_ERR_SUCCESS:
                raise CloudError("status query could not be sent; no retry")

    def on_message(c, userdata, message):
        if (not started or message.topic != report_topic or message.retain
                or len(message.payload) > _MAX_BYTES):
            return
        try:
            value = json.loads(message.payload)
        except (ValueError, UnicodeError):
            return
        if not isinstance(value, dict):
            return
        status = status_fields(value.get("print"))
        if status:
            result["status"].update(status)
            result["received_at_utc"] = datetime.now(timezone.utc).isoformat()
            if "gcode_state" in status:
                result["fresh_state_received"] = True
        info = value.get("info")
        if (not isinstance(info, dict) or info.get("command") != "get_version"
                or info.get("sequence_id") != sequence
                or ("result" in info and info["result"] != "success")
                or ("err_code" in info and (type(info["err_code"]) is not int or info["err_code"] != 0))):
            return
        modules = info.get("module")
        if not isinstance(modules, list) or not modules:
            return
        cleaned = []
        for module in modules:
            if (not isinstance(module, dict) or not isinstance(module.get("name"), str)
                    or not 0 < len(module["name"]) <= 128 or not isinstance(module.get("sw_ver"), str)
                    or not 0 < len(module["sw_ver"]) <= 128):
                return
            cleaned.append({k: module[k] for k in ("name", "sw_ver", "hw_ver")
                            if isinstance(module.get(k), str) and len(module[k]) <= 128})
        result["firmware_modules"] = cleaned
        result["version_reply_matched"] = True

    try:
        client.connect_timeout = 8
        client.username_pw_set("u_" + session.user_id, session.access_token)
        client.tls_set_context(ssl.create_default_context())
        client.on_connect, client.on_subscribe, client.on_message = on_connect, on_subscribe, on_message
        if client.connect("us.mqtt.bambulab.com", 8883, keepalive=30) != mqtt.MQTT_ERR_SUCCESS:
            raise CloudError("MQTT connection failed")
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            if client.loop(timeout=min(1.0, max(0.001, deadline - time.monotonic()))) != mqtt.MQTT_ERR_SUCCESS:
                raise CloudError("MQTT observation disconnected; no retry")
            if result["fresh_state_received"] and result["version_reply_matched"]:
                return result
        raise CloudError("timed out waiting for fresh state and a matched firmware reply")
    except CloudError:
        raise
    except Exception:
        raise CloudError("MQTT observation failed; no automatic retry") from None
    finally:
        try:
            client.disconnect()
        except Exception:
            pass
