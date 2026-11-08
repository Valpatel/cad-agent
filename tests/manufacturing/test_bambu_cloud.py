"""Exercise the observation consumer with hostile/stale replies, never real credentials."""
from datetime import datetime, timedelta, timezone
import io
import json
import os
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from cadagent.manufacturing.devices.bambu import cloud


@pytest.fixture
def session():
    return cloud.CloudSession("TEST-TOKEN-DO-NOT-USE", "123", datetime.now(timezone.utc) + timedelta(hours=1))


def cache(tmp_path, **patch):
    folder = tmp_path / "private"
    folder.mkdir(mode=0o700, exist_ok=True)
    value = {"format": "cad-agent.bambu-session/1", "region": "global",
             "api_origin": "https://api.bambulab.com",
             "received_at_utc": datetime.now(timezone.utc).isoformat(),
             "tokens": {"accessToken": "TEST-TOKEN-DO-NOT-USE", "expiresIn": 3600},
             "profile": {"uidStr": "123"}}
    value.update(patch)
    path = folder / "session.json"
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    return path


@pytest.mark.skipif(os.name != "posix", reason="POSIX cache policy; Windows ACL storage not implemented")
def test_cache_reused_without_writes_or_secret_repr(tmp_path, monkeypatch):
    path = cache(tmp_path)
    before = path.read_bytes()
    monkeypatch.setattr(cloud, "_get", lambda *a: pytest.fail("cache loading must not connect"))
    loaded = cloud.load_session(path)
    assert loaded.access_token == "TEST-TOKEN-DO-NOT-USE" and loaded.user_id == "123"
    assert "TOKEN" not in repr(loaded) and "user_id" not in repr(loaded)
    assert path.read_bytes() == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX modes")
@pytest.mark.parametrize("fault", ["file-mode", "directory-mode", "symlink", "fifo", "expired", "future", "region", "header", "bool-expiry", "bad-json"])
def test_unsafe_or_unusable_cache_rejected(tmp_path, fault):
    path = cache(tmp_path)
    if fault == "file-mode":
        path.chmod(0o644)
    elif fault == "directory-mode":
        path.parent.chmod(0o755)
    elif fault == "symlink":
        target = path.with_name("real.json")
        path.rename(target)
        path.symlink_to(target)
    elif fault == "fifo":
        path.unlink()
        os.mkfifo(path, 0o600)
    elif fault == "bad-json":
        path.write_text('{"tokens": "TEST-TOKEN-DO-NOT-USE"')
    else:
        value = json.loads(path.read_text())
        if fault == "expired":
            value["received_at_utc"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        elif fault == "future":
            value["received_at_utc"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        elif fault == "region":
            value["region"] = "unverified-region"
        elif fault == "header":
            value["tokens"]["accessToken"] = "TEST-TOKEN-DO-NOT-USE\r\nX-Forged: yes"
        elif fault == "bool-expiry":
            value["tokens"]["expiresIn"] = True
        path.write_text(json.dumps(value))
    with pytest.raises(cloud.CloudError) as caught:
        cloud.load_session(path)
    assert "TEST-TOKEN" not in str(caught.value)


def test_http_uses_fixed_endpoint_tls_and_sanitizes_failures(monkeypatch, session):
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append((request, timeout))
            raise HTTPError(request.full_url, 401, "TEST-TOKEN-DO-NOT-USE", {}, None)
    def build(*handlers):
        assert any(isinstance(h, cloud._NoRedirect) for h in handlers)
        tls = next(h for h in handlers if isinstance(h, cloud.HTTPSHandler))._context
        assert tls.check_hostname and tls.verify_mode == cloud.ssl.CERT_REQUIRED
        return Opener()
    monkeypatch.setattr(cloud, "build_opener", build)
    with pytest.raises(cloud.CloudError, match="HTTP 401") as caught:
        cloud.owned_printers(session)
    assert "TOKEN" not in str(caught.value) and caught.value.__suppress_context__
    assert len(calls) == 1
    assert calls[0][0].full_url == "https://api.bambulab.com/v1/design-user-service/my/preference"
    assert calls[0][0].get_method() == "GET" and calls[0][1] == 10
    with pytest.raises(cloud.CloudError, match="redirect refused"):
        cloud._NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.invalid")


@pytest.mark.parametrize("body", [b"[]", b"not-json", b" " * 2_000_001])
def test_bad_http_body_rejected(monkeypatch, session, body):
    class Response(io.BytesIO):
        status = 200
    monkeypatch.setattr(cloud, "build_opener", lambda *a: SimpleNamespace(open=lambda *a, **k: Response(body)))
    with pytest.raises(cloud.CloudError):
        cloud.owned_printers(session)


@pytest.mark.parametrize("fault", ["wrong-account", "boolean-account", "duplicate", "wildcard", "missing-list"])
def test_fresh_ownership_rejected_before_mqtt(monkeypatch, session, fault):
    profile = {"uid": "999" if fault == "wrong-account" else True if fault == "boolean-account" else 123}
    device = {"dev_id": "DEVICE-123" if fault != "wildcard" else "device/+/request", "dev_product_name": "P1S"}
    devices = {} if fault == "missing-list" else {"devices": [device, device] if fault == "duplicate" else [device]}
    calls = []
    def get(s, path):
        calls.append(path)
        return profile if len(calls) == 1 else devices
    monkeypatch.setattr(cloud, "_get", get)
    with pytest.raises(cloud.CloudError):
        cloud.owned_printers(session)
    if "account" in fault:
        assert len(calls) == 1


class FakeClient:
    """Transport seam: drive the actual consumer callbacks and inspect publications."""
    def __init__(self, *args, **kwargs):
        assert kwargs["clean_session"] is True and kwargs["reconnect_on_failure"] is False
        self.calls, self.events, self.disconnected = [], [], False
    def username_pw_set(self, username, password):
        assert username == "u_123" and password == "TEST-TOKEN-DO-NOT-USE"
    def tls_set_context(self, context):
        assert context.check_hostname and context.verify_mode == cloud.ssl.CERT_REQUIRED
    def connect(self, host, port, keepalive):
        assert (host, port, keepalive) == ("us.mqtt.bambulab.com", 8883, 30)
        self.on_connect(self, None, None, SimpleNamespace(is_failure=False), None)
        return 0
    def subscribe(self, topic, qos):
        assert topic == "device/DEVICE-123/report" and qos == 0
        self.events.append(lambda: self.on_subscribe(self, None, 7, [SimpleNamespace(is_failure=False)], None))
        return 0, 7
    def publish(self, topic, payload, **kwargs):
        self.calls.append((topic, json.loads(payload), kwargs))
        return SimpleNamespace(rc=0)
    def message(self, value, *, retained=False, topic="device/DEVICE-123/report"):
        self.on_message(self, None, SimpleNamespace(topic=topic, retain=retained, payload=json.dumps(value).encode()))
    def version(self, **patch):
        info = {"command": "get_version", "sequence_id": self.calls[1][1]["info"]["sequence_id"],
                "module": [{"name": "ota", "sw_ver": "TEST-VERSION"}]}
        info.update(patch)
        return {"info": info}
    def loop(self, timeout):
        if self.events:
            self.events.pop(0)()
        else:
            return 7  # disconnect rather than busy-loop a mock timeout
        return 0
    def disconnect(self):
        self.disconnected = True


@pytest.fixture
def transport(monkeypatch):
    clients = []
    def factory(*a, **k):
        client = FakeClient(*a, **k)
        clients.append(client)
        return client
    module = SimpleNamespace(Client=factory, CallbackAPIVersion=SimpleNamespace(VERSION2=2), MQTT_ERR_SUCCESS=0)
    monkeypatch.setattr(cloud.importlib, "import_module", lambda name: module)
    monkeypatch.setattr(cloud, "owned_printers", lambda s: (cloud.OwnedPrinter("DEVICE-123", "P1S"),))
    return clients


def test_only_two_observations_and_fresh_correlated_result(monkeypatch, session, transport):
    original = FakeClient.subscribe
    def subscribe(self, *a, **k):
        rc = original(self, *a, **k)
        self.events.extend([
            lambda: self.message({"print": {"gcode_state": "IDLE", "bed_temper": 24}}),
            lambda: self.message({"print": {"device": {"ctc": {"info": {"temp": (45 << 16) | 25}}}}}),
            lambda: self.message(self.version()),
        ])
        return rc
    monkeypatch.setattr(FakeClient, "subscribe", subscribe)
    result = cloud.observe(session, "DEVICE-123")
    client = transport[0]
    assert result["fresh_state_received"] and result["version_reply_matched"]
    assert result["status"] == {"gcode_state": "IDLE", "bed_temper": 24, "chamber_temper": 25, "chamber_target_temper": 45}
    assert result["firmware_modules"] == [{"name": "ota", "sw_ver": "TEST-VERSION"}]
    assert result["publish_count"] == len(client.calls) == 2 and client.disconnected
    assert [next(iter(p.values()))["command"] for _, p, _ in client.calls] == ["pushall", "get_version"]
    assert all(t == "device/DEVICE-123/request" and k == {"qos": 0, "retain": False} for t, _, k in client.calls)
    assert "DEVICE-123" not in json.dumps(result) and "TOKEN" not in json.dumps(result)


@pytest.mark.parametrize("fault", ["wrong-id", "retained-version", "retained-state", "other-topic", "empty-heartbeat", "failed-version", "malformed-version", "duplicate-ack"])
def test_stale_or_misidentified_reply_does_not_pass_or_resend(monkeypatch, session, transport, fault):
    original = FakeClient.subscribe
    def subscribe(self, *a, **k):
        rc = original(self, *a, **k)
        def replies():
            state = {"print": {"gcode_state": "IDLE"}}
            if fault == "empty-heartbeat":
                state = {"print": {}}
            self.message(state, retained=fault == "retained-state")
            version = self.version()
            if fault == "wrong-id":
                version["info"]["sequence_id"] = "wrong"
            if fault == "failed-version":
                version["info"]["result"] = "fail"
            if fault == "malformed-version":
                version["info"]["module"] = ["not-a-module"]
            if fault == "duplicate-ack":
                self.on_subscribe(self, None, 7, [SimpleNamespace(is_failure=False)], None)
            self.message(version, retained=fault == "retained-version",
                         topic="device/OTHER-123/report" if fault == "other-topic" else "device/DEVICE-123/report")
        self.events.append(replies)
        return rc
    monkeypatch.setattr(FakeClient, "subscribe", subscribe)
    with pytest.raises(cloud.CloudError):
        cloud.observe(session, "DEVICE-123")
    assert transport[0].disconnected and len(transport[0].calls) == 2


def test_unowned_device_never_connects(session, transport):
    with pytest.raises(cloud.CloudError, match="not owned"):
        cloud.observe(session, "OTHER-123")
    assert transport == []


def test_temperature_decoder_ignores_sentinels_and_nonfinite_values():
    assert cloud.status_fields({"bed_temper": True, "nozzle_temper": float("nan"),
                                "mc_percent": 10 ** 400, "gcode_state": False}) == {}
    assert cloud.status_fields({"device": {"ctc": {"info": {"temp": 0xffffffff}}}}) == {}
    assert cloud.status_fields({"device": {"ctc": {"info": {"temp": (0xffff << 16) | 23}}}}) == {"chamber_temper": 23}


@pytest.mark.parametrize("fault", ["wrong-subscription-id", "refused-subscription", "publish-failure"])
def test_query_setup_failure_stops_without_repeat(monkeypatch, session, transport, fault):
    def subscribe(self, topic, qos):
        self.events.append(lambda: self.on_subscribe(self, None,
                           99 if fault == "wrong-subscription-id" else 7,
                           [SimpleNamespace(is_failure=fault == "refused-subscription")], None))
        return 0, 7
    monkeypatch.setattr(FakeClient, "subscribe", subscribe)
    if fault == "publish-failure":
        original = FakeClient.publish
        def publish(self, *a, **k):
            original(self, *a, **k)
            return SimpleNamespace(rc=7)
        monkeypatch.setattr(FakeClient, "publish", publish)
    with pytest.raises(cloud.CloudError):
        cloud.observe(session, "DEVICE-123")
    assert transport[0].disconnected
    assert len(transport[0].calls) == (1 if fault == "publish-failure" else 0)


def test_event_wait_timeout_cleans_up(monkeypatch, session, transport):
    ticks = iter([0, 0, 0.1, 2])
    monkeypatch.setattr(cloud.time, "monotonic", lambda: next(ticks))
    with pytest.raises(cloud.CloudError, match="timed out"):
        cloud.observe(session, "DEVICE-123", wait_seconds=1)
    assert transport[0].disconnected and len(transport[0].calls) == 2


def test_missing_optional_dependency_stops_before_ownership(monkeypatch, session):
    def missing(name):
        raise ImportError("missing optional dependency")
    monkeypatch.setattr(cloud.importlib, "import_module", missing)
    monkeypatch.setattr(cloud, "owned_printers", lambda s: pytest.fail("no HTTP needed"))
    with pytest.raises(cloud.CloudError, match="paho-mqtt"):
        cloud.observe(session, "DEVICE-123")


def test_interruption_closes_owned_client(monkeypatch, session, transport):
    monkeypatch.setattr(FakeClient, "loop", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        cloud.observe(session, "DEVICE-123")
    assert transport[0].disconnected


def test_actual_optional_paho_constructor_and_tls_setup(monkeypatch, session):
    mqtt = pytest.importorskip("paho.mqtt.client")
    calls = []
    monkeypatch.setattr(cloud, "owned_printers", lambda s: (cloud.OwnedPrinter("DEVICE-123", "P1S"),))
    def connect(client, *a, **k):
        assert client.callback_api_version == mqtt.CallbackAPIVersion.VERSION2
        calls.append("connect-refused-before-network")
        return mqtt.MQTT_ERR_NO_CONN
    monkeypatch.setattr(mqtt.Client, "connect", connect)
    monkeypatch.setattr(mqtt.Client, "disconnect", lambda s: calls.append("disconnect"))
    with pytest.raises(cloud.CloudError, match="connection failed"):
        cloud.observe(session, "DEVICE-123")
    assert calls == ["connect-refused-before-network", "disconnect"]
