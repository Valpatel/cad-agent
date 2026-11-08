"""Camera success requires decoded bytes, private output and a reaped native process."""
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

import pytest

from cadagent.manufacturing.devices.bambu import camera as K, cloud

ROOT = Path(__file__).resolve().parents[2]
READER = ROOT / "tools/bambu-camera/capture.py"
LINUX = sys.platform.startswith("linux")


@pytest.fixture
def session():
    return cloud.CloudSession("TEST-TOKEN", "123", datetime.now(timezone.utc) + timedelta(hours=1))


@pytest.fixture
def jpeg():
    Image = pytest.importorskip("PIL.Image")
    out = io.BytesIO()
    Image.new("RGB", (64, 32), "navy").save(out, format="JPEG")
    return out.getvalue()


def test_normal_grant_uses_one_fixed_post_and_keeps_secrets_out_of_errors(session, monkeypatch):
    calls = []
    def request(s, path, payload):
        calls.append((path, payload))
        return {"type": "tutk", "ttcode": "TEST+ID", "authkey": "TEST&KEY", "passwd": "TEST/PASS"}
    monkeypatch.setattr(cloud, "_request_json", request)
    url = K._grant(session, "TESTDEVICE", "01.02.03.04")
    assert calls == [(cloud._CAMERA, {"dev_id": "TESTDEVICE", "dev_version": "01.02.03.04", "protocols": ["tutk"]})]
    assert "uid=TEST%2BID" in url and "authkey=TEST%26KEY" in url and "passwd=TEST%2FPASS" in url
    monkeypatch.setattr(cloud, "_request_json", lambda *a: {"type": "tutk", "passwd": "SECRET"})
    with pytest.raises(cloud.CloudError) as error:
        K._grant(session, "TESTDEVICE", "01.02.03.04")
    assert "SECRET" not in str(error.value)


def test_camera_post_uses_verified_tls_and_the_tool_identity(session, monkeypatch):
    calls = []
    class Response(io.BytesIO):
        status = 200
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            assert timeout == 10
            return Response(b'{"type":"tutk","ttcode":"TEST","authkey":"TEST","passwd":"TEST"}')
    def opener(*handlers):
        assert any(isinstance(h, cloud._NoRedirect) for h in handlers)
        tls = next(h for h in handlers if isinstance(h, cloud.HTTPSHandler))._context
        assert tls.check_hostname and tls.verify_mode == cloud.ssl.CERT_REQUIRED
        return Opener()
    monkeypatch.setattr(cloud, "build_opener", opener)
    K._grant(session, "TESTDEVICE", "01.02.03.04")
    request, = calls
    assert request.get_method() == "POST" and request.full_url == cloud._ORIGIN + cloud._CAMERA
    assert request.get_header("X-bbl-client-name") == "cad-agent"
    assert request.get_header("X-bbl-client-type") == "tool"
    assert request.get_header("X-bbl-client-version") == cloud.__version__
    assert json.loads(request.data) == {"dev_id": "TESTDEVICE", "dev_version": "01.02.03.04", "protocols": ["tutk"]}


@pytest.mark.parametrize("reply", [{}, {"type": "agora"}, {"type": "tutk", "ttcode": "x", "authkey": "y", "passwd": "z\n"}])
def test_incomplete_or_different_transport_never_becomes_a_reader_url(session, monkeypatch, reply):
    monkeypatch.setattr(cloud, "_request_json", lambda *a: reply)
    with pytest.raises(cloud.CloudError):
        K._grant(session, "TESTDEVICE", "01.02.03.04")


@pytest.fixture
def prepared(tmp_path, monkeypatch, jpeg):
    folder = tmp_path / "private"
    folder.mkdir(mode=0o700)
    library = folder / "test-library"
    library.write_bytes(b"TEST LIBRARY NOT EXECUTABLE")
    monkeypatch.setattr(K, "MEDIA_SHA256", hashlib.sha256(library.read_bytes()).hexdigest())
    observation = {"model": "P1S", "fresh_state_received": True, "version_reply_matched": True,
                   "firmware_modules": [{"name": "ota", "sw_ver": "01.02.03.04"}]}
    monkeypatch.setattr(cloud, "observe", lambda *a: observation)
    grants = []
    monkeypatch.setattr(K, "_grant", lambda *a: grants.append(a) or "TEST URL")
    monkeypatch.setattr(K, "_read_jpeg", lambda *a: (jpeg, (64, 32)))
    return folder, library, observation, grants


@pytest.mark.skipif(not LINUX, reason="pinned Linux native runtime")
def test_capture_creates_new_private_file_and_does_not_claim_an_empty_bed(session, prepared):
    folder, library, observation, grants = prepared
    output = folder / "frame.jpg"
    result = K.capture(session, "TESTDEVICE", media_library=library, media_reader=READER, output=output)
    assert len(grants) == 1 and result["bed_clear"] is None and result["print_authorized"] is False
    assert result["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert output.stat().st_mode & 0o777 == 0o600
    assert not list(folder.glob(".cad-agent-frame-*"))
    with pytest.raises(cloud.CloudError, match="already exists"):
        K.capture(session, "TESTDEVICE", media_library=library, media_reader=READER, output=output)
    assert len(grants) == 1


@pytest.mark.skipif(not LINUX, reason="pinned Linux native runtime")
def test_unsupported_installed_decoder_stops_before_camera_queries(session, prepared, monkeypatch):
    import PIL
    folder, library, observation, grants = prepared
    monkeypatch.setattr(PIL, "__version__", "12.3.0")
    monkeypatch.setattr(cloud, "observe", lambda *a: pytest.fail("must stop before device query"))
    with pytest.raises(cloud.CloudError, match="Pillow 13"):
        K.capture(session, "TESTDEVICE", media_library=library, media_reader=READER, output=folder / "frame.jpg")
    assert not grants


@pytest.mark.skipif(not LINUX, reason="pinned Linux native runtime")
def test_a_destination_created_during_capture_is_preserved(session, prepared, monkeypatch, jpeg):
    folder, library, observation, grants = prepared
    output = folder / "frame.jpg"
    def competing_writer(*args):
        output.write_bytes(b"user file created after preflight")
        return jpeg, (64, 32)
    monkeypatch.setattr(K, "_read_jpeg", competing_writer)
    with pytest.raises(cloud.CloudError):
        K.capture(session, "TESTDEVICE", media_library=library, media_reader=READER, output=output)
    assert output.read_bytes() == b"user file created after preflight"
    assert not list(folder.glob(".cad-agent-frame-*"))


@pytest.mark.skipif(not LINUX, reason="pinned Linux native runtime")
@pytest.mark.parametrize("fault", ["runtime", "mode", "symlink", "x1e", "stale", "ambiguous-firmware"])
def test_preflight_and_observation_failures_do_not_request_a_camera_grant(session, prepared, fault):
    folder, library, observation, grants = prepared
    output = folder / "frame.jpg"
    if fault == "runtime":
        library.write_bytes(b"DIFFERENT RUNTIME")
    elif fault == "mode":
        folder.chmod(0o755)
    elif fault == "symlink":
        output.symlink_to(folder / "absent")
    elif fault == "x1e":
        observation["model"] = "X1E"
    elif fault == "stale":
        observation["fresh_state_received"] = False
    else:
        observation["firmware_modules"] *= 2
    with pytest.raises(cloud.CloudError):
        K.capture(session, "TESTDEVICE", media_library=library, media_reader=READER, output=output)
    assert not grants


def scripted_reader(tmp_path, jpeg, monkeypatch, fault=""):
    path = tmp_path / "reader.py"
    data = jpeg if fault != "corrupt" else b"\xff\xd8not an image\xff\xd9"
    if fault == "bomb":
        data = bytearray(data)
        frame = data.index(b"\xff\xc0")
        data[frame + 5:frame + 9] = struct.pack(">HH", 65535, 65535)
        data = bytes(data)
    path.write_text("import json,os,sys\nfrom pathlib import Path\nos.umask(0o077)\n"
                    "out=Path(sys.argv[2])\n"
                    f"data={data!r}\n(out/'frame.jpg').write_bytes(data)\n"
                    f"(out/'result.json').write_text(json.dumps({{'ok':True,'width':{63 if fault == 'dimensions' else 64},'height':32,'bytes':len(data)}}))\n"
                    + ("(out/'frame.jpg').chmod(0o644)\n" if fault == "public" else "")
                    + ("raise SystemExit(1)\n" if fault == "exit" else ""))
    monkeypatch.setattr(K, "READER_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    return path


@pytest.mark.skipif(not LINUX, reason="Linux waitid/process groups")
def test_parent_reopens_and_fully_decodes_the_external_reader_output(tmp_path, jpeg, monkeypatch):
    data, size = K._read_jpeg(scripted_reader(tmp_path, jpeg, monkeypatch), Path("unused"), "TEST-PRIVATE-URL")
    assert data == jpeg and size == (64, 32)


@pytest.mark.skipif(not LINUX, reason="Linux waitid/process groups")
@pytest.mark.parametrize("fault", ["corrupt", "bomb", "dimensions", "public", "exit"])
def test_native_success_or_jpeg_markers_alone_are_not_a_verified_frame(tmp_path, jpeg, fault, monkeypatch):
    with pytest.raises(cloud.CloudError):
        K._read_jpeg(scripted_reader(tmp_path, jpeg, monkeypatch, fault), Path("unused"), "TEST-PRIVATE-URL")


@pytest.mark.skipif(not LINUX, reason="Linux waitid/process groups")
@pytest.mark.parametrize("leader_exits", [False, True])
def test_native_group_is_stopped_on_timeout_and_when_leader_exits_first(tmp_path, jpeg, leader_exits, monkeypatch):
    pidfile = tmp_path / "child.pid"
    reader = tmp_path / "reader.py"
    reader.write_text("import subprocess,sys,time\nfrom pathlib import Path\n"
                      "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])\n"
                      f"Path({str(pidfile)!r}).write_text(str(child.pid))\n"
                      + ("raise SystemExit(1)\n" if leader_exits else "time.sleep(60)\n"))
    monkeypatch.setattr(K, "READER_SHA256", hashlib.sha256(reader.read_bytes()).hexdigest())
    start = time.monotonic()
    with pytest.raises(cloud.CloudError):
        K._read_jpeg(reader, Path("unused"), "TEST-PRIVATE-URL", seconds=.4)
    assert time.monotonic() - start < 5
    pid = int(pidfile.read_text())
    proc = Path(f"/proc/{pid}/stat")
    deadline = time.monotonic() + 1
    while proc.exists() and proc.read_text().split(")", 1)[1].split()[0] != "Z" and time.monotonic() < deadline:
        time.sleep(.01)
    assert not proc.exists() or proc.read_text().split(")", 1)[1].split()[0] == "Z"


@pytest.mark.skipif(not LINUX, reason="Linux private reader snapshot")
def test_reader_substitution_after_validation_cannot_receive_the_grant(tmp_path, jpeg, monkeypatch):
    reader = scripted_reader(tmp_path, jpeg, monkeypatch)
    popen = K.subprocess.Popen
    def replace_source_then_launch(args, **kwargs):
        reader.write_text("raise RuntimeError('substituted reader ran')\n")
        assert Path(args[1]) != reader
        assert Path(args[1]).stat().st_mode & 0o777 == 0o600
        return popen(args, **kwargs)
    monkeypatch.setattr(K.subprocess, "Popen", replace_source_then_launch)
    data, size = K._read_jpeg(reader, Path("unused"), "TEST-PRIVATE-URL")
    assert data == jpeg and size == (64, 32)


@pytest.mark.skipif(not LINUX, reason="Linux private reader snapshot")
@pytest.mark.parametrize("fault", ["different-bytes", "symlink", "oversize"])
def test_unreviewed_reader_stops_before_device_queries(session, prepared, monkeypatch, fault):
    folder, library, observation, grants = prepared
    reader = folder / "reader.py"
    if fault == "symlink":
        reader.symlink_to(READER)
    elif fault == "oversize":
        reader.write_bytes(b"#" * 65537)
    else:
        reader.write_text("print('unreviewed script')\n")
    monkeypatch.setattr(cloud, "observe", lambda *a: pytest.fail("must stop before device query"))
    with pytest.raises(cloud.CloudError):
        K.capture(session, "TESTDEVICE", media_library=library, media_reader=reader, output=folder / "frame.jpg")
    assert not grants


@pytest.mark.skipif(not LINUX, reason="Linux native ABI")
def test_external_reader_uses_real_c_layout_and_frees_native_log_pointer(tmp_path):
    """Independent C producer exercises field offsets and the callback's pointer ownership."""
    cc = shutil.which("cc")
    assert cc, "Linux camera-reader ABI control requires the system C compiler"
    source = tmp_path / "fixture.c"
    library = tmp_path / "fixture.so"
    source.write_text(r'''
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
typedef struct { int type, sub; int width, height, fps; int kind, size, max; const void *buffer; } Info;
typedef struct { int track, size, flags; const void *buffer; unsigned long long time; } Sample;
static int token, freed;
static unsigned char jpeg[] = {255,216,255,217};
int Bambu_Init(void) { return 0; }
void Bambu_Deinit(void) {}
int Bambu_Create(void **out, const char *url) { *out=&token; return 0; }
void Bambu_Destroy(void *p) {}
int Bambu_Open(void *p) { return 0; }
void Bambu_Close(void *p) {}
void Bambu_FreeLogMsg(void *p) { free(p); freed=1; }
void Bambu_SetLogger(void *p, void (*fn)(void*,int,void*), void *ctx) {
    char *message=malloc(24); strcpy(message,"TEST PRIVATE MESSAGE"); fn(ctx,0,message);
}
int Bambu_StartStream(void *p, bool video) { return freed && video ? 0 : 9; }
int Bambu_GetStreamCount(void *p) { return 1; }
int Bambu_GetStreamInfo(void *p, int i, Info *out) {
    *out=(Info){.type=0,.sub=1,.width=64,.height=32,.fps=5,.kind=2}; return 0;
}
int Bambu_ReadSample(void *p, Sample *out) {
    *out=(Sample){.track=0,.size=sizeof(jpeg),.buffer=jpeg,.time=1234567}; return 0;
}
''')
    subprocess.run([cc, "-shared", "-fPIC", str(source), "-o", str(library)], check=True, capture_output=True, timeout=15)
    out = tmp_path / "private"
    out.mkdir(mode=0o700)
    process = subprocess.run([sys.executable, str(READER), str(library), str(out)],
                             input=b'{"url":"bambu:///tutk?uid=TEST&authkey=TEST&passwd=TEST"}',
                             capture_output=True, timeout=5)
    assert process.returncode == 0 and b"PRIVATE MESSAGE" not in process.stdout + process.stderr
    assert json.loads((out / "result.json").read_text()) == {"ok": True, "width": 64, "height": 32, "bytes": 4}
    assert (out / "frame.jpg").read_bytes() == b"\xff\xd8\xff\xd9"
    # This verifies the C boundary/candidate bytes only. Parent tests reject this non-decodable JPEG.
