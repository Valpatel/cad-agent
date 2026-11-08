"""The public command dispatches without loading a CAD project or leaking tokens."""
import json

from cadagent.cli import main
from cadagent.manufacturing.devices.bambu import cloud


def test_listing_and_explicit_observation(monkeypatch, capsys):
    marker = object()
    monkeypatch.setattr(cloud, "load_session", lambda p: marker)
    monkeypatch.setattr(cloud, "owned_printers", lambda s: (cloud.OwnedPrinter("DUMMY-123", "P1S"),))
    assert main(["bambu-status"]) == 0
    assert json.loads(capsys.readouterr().out)["printers"] == [{"device_id": "DUMMY-123", "model": "P1S"}]
    calls = []
    def observe(session, device, **kw):
        calls.append((session, device, kw))
        return {"model": "P1S", "fresh_state_received": True}
    monkeypatch.setattr(cloud, "observe", observe)
    assert main(["bambu-status", "--device", "DUMMY-123", "--wait-seconds", "5"]) == 0
    assert calls == [(marker, "DUMMY-123", {"wait_seconds": 5})]
    assert json.loads(capsys.readouterr().out)["fresh_state_received"] is True


def test_missing_session_fails_without_network(monkeypatch, capsys):
    def missing(path):
        raise cloud.CloudError("cannot read a valid private cached session")
    monkeypatch.setattr(cloud, "load_session", missing)
    monkeypatch.setattr(cloud, "owned_printers", lambda s: (_ for _ in ()).throw(AssertionError("must not connect")))
    assert main(["bambu-status"]) == 2
    output = capsys.readouterr()
    assert not output.out and "private cached session" in output.err


def test_explicit_empty_selector_is_not_an_owned_printer_listing(monkeypatch, capsys):
    monkeypatch.setattr(cloud, "load_session", lambda p: object())
    monkeypatch.setattr(cloud, "owned_printers", lambda s: (_ for _ in ()).throw(AssertionError("must not list")))
    assert main(["bambu-status", "--device", ""]) == 2
    output = capsys.readouterr()
    assert not output.out and "invalid requested printer identity" in output.err
