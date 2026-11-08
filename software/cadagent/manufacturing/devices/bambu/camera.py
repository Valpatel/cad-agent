"""One private P1S frame; no GUI automation, physical controls or retry.

The optional AGPL reader is a separate program, never imported into this package.
The digest below pins the installed media library selected for the trial;
this integration still needs its own exact-source review and actual trial.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote, urlencode
import uuid

from packaging.version import Version

from . import cloud

MEDIA_SHA256 = "4e05f16fa02740fd12f0040b9efc3e70d43446c7a1a877c6a3926ef0758ca7db"
_MAX_FRAME = 8 * 1024 * 1024
_FIRMWARE = re.compile(r"\d+(?:\.\d+){3}\Z")


def _media_path(path: Path) -> Path:
    try:
        path = Path(path).resolve(strict=True)
        if not path.is_file() or not 0 < path.stat().st_size <= 32 * 1024 * 1024:
            raise cloud.CloudError("media library must be a regular file within the size limit")
        if hashlib.sha256(path.read_bytes()).hexdigest() != MEDIA_SHA256:
            raise cloud.CloudError("installed media library does not match the reviewed runtime digest")
        return path
    except OSError:
        raise cloud.CloudError("cannot read the installed media library") from None


def _grant(session: cloud.CloudSession, device_id: str, firmware: str) -> str:
    if not cloud._SERIAL.fullmatch(device_id) or not _FIRMWARE.fullmatch(firmware):
        raise cloud.CloudError("invalid camera device or firmware identity")
    reply = cloud._request_json(session, cloud._CAMERA, {
        "dev_id": device_id, "dev_version": firmware, "protocols": ["tutk"],
    })
    if reply.get("type") != "tutk":
        raise cloud.CloudError("camera grant did not select the supported transport")
    parameters = {}
    for key, target in (("ttcode", "uid"), ("authkey", "authkey"), ("passwd", "passwd"), ("region", "region")):
        value = reply.get(key)
        if key == "region" and value in (None, ""):
            continue
        if (not isinstance(value, str) or not 0 < len(value) <= 4096
                or any(ord(c) < 33 or ord(c) > 126 for c in value)):
            raise cloud.CloudError("camera grant is incomplete or malformed")
        parameters[target] = value
    url = "bambu:///tutk?" + urlencode(parameters, quote_via=quote)
    if len(url) > 32000:
        raise cloud.CloudError("camera grant exceeds the reader input limit")
    return url


def _private_bytes(path: Path, limit: int) -> bytes:
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o077 or not 0 < info.st_size <= limit):
            raise cloud.CloudError("reader output is not a bounded private regular file")
        with os.fdopen(fd, "rb") as handle:
            fd = None
            data = handle.read(limit + 1)
        if len(data) > limit:
            raise cloud.CloudError("reader output exceeds the size limit")
        return data
    except OSError:
        raise cloud.CloudError("camera reader did not produce a private frame") from None
    finally:
        if fd is not None:
            os.close(fd)


def _read_jpeg(reader: Path, library: Path, url: str, *, seconds: float = 45) -> tuple[bytes, tuple[int, int]]:
    """Bound and reap the external process group, then independently decode its JPEG."""
    from PIL import Image

    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 60:
        raise cloud.CloudError("camera reader deadline must be finite and at most 60 seconds")
    with tempfile.TemporaryDirectory(prefix="cad-agent-camera-") as tmp:
        folder = Path(tmp)
        process = None
        try:
            # An unlinked private file avoids blocking on a child that never reads its input pipe.
            with tempfile.TemporaryFile(dir=folder) as grant_input:
                grant_input.write(json.dumps({"url": url}).encode("ascii"))
                grant_input.seek(0)
                process = subprocess.Popen([sys.executable, str(reader), str(library), str(folder)],
                                           stdin=grant_input, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           start_new_session=True)
                deadline = time.monotonic() + seconds
                while True:
                    # WNOWAIT keeps the leader's PID reserved until group cleanup, avoiding reuse races.
                    state = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                    if state is not None:
                        if state.si_code != os.CLD_EXITED or state.si_status != 0:
                            raise cloud.CloudError("camera reader failed; no automatic retry")
                        break
                    if time.monotonic() >= deadline:
                        raise cloud.CloudError("camera reader exceeded its deadline; no automatic retry")
                    time.sleep(0.025)
        except OSError:
            raise cloud.CloudError("camera reader could not start") from None
        finally:
            if process is not None:
                # The unreaped leader still reserves this PGID, even if it exited before its children.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
        try:
            receipt = json.loads(_private_bytes(folder / "result.json", 4096))
            data = _private_bytes(folder / "frame.jpg", _MAX_FRAME)
            with Image.open(io.BytesIO(data)) as picture:
                dimensions = picture.size
                if picture.format != "JPEG" or not all(16 <= n <= 4096 for n in dimensions):
                    raise cloud.CloudError("camera output is not a supported JPEG")
                picture.verify()
            with Image.open(io.BytesIO(data)) as picture:
                picture.load()
            if (not isinstance(receipt, dict) or receipt.get("ok") is not True
                    or receipt.get("bytes") != len(data)
                    or [receipt.get("width"), receipt.get("height")] != list(dimensions)):
                raise cloud.CloudError("decoded image does not match the reader receipt")
            return data, dimensions
        except cloud.CloudError:
            raise
        except (OSError, ValueError, TypeError, SyntaxError):
            raise cloud.CloudError("camera output did not fully decode as JPEG") from None


def capture(session: cloud.CloudSession, device_id: str, *, media_library: Path,
            media_reader: Path, output: Path) -> dict:
    """Fresh ownership/status/version, one grant, one bounded external frame read.

    Output is a new file in an existing owner-only directory. The cached session
    is not changed. HTTP/MQTT retain their individual socket/event deadlines;
    only the external reader has a hard process deadline. A decoded frame is not
    an empty-bed assessment, sustained-video qualification or print permission.
    """
    if (sys.version_info < (3, 11) or os.name != "posix" or not sys.platform.startswith("linux")
            or platform.machine() != "x86_64"):
        raise cloud.CloudError("camera capture requires Python 3.11+ on Linux x86_64")
    try:
        import PIL  # fail before any account/device request if the supported decoder is absent
    except ImportError:
        raise cloud.CloudError("camera capture needs Pillow 13+ (cad-agent[bambu-camera])") from None
    if Version(PIL.__version__) < Version("13.0"):
        raise cloud.CloudError("camera capture needs Pillow 13+ (cad-agent[bambu-camera])")
    library = _media_path(media_library)
    try:
        reader = Path(media_reader).resolve(strict=True)
        if not reader.is_file():
            raise cloud.CloudError("external camera reader must be a regular file")
    except OSError:
        raise cloud.CloudError("external camera reader was not found") from None
    output = Path(output)
    if not output.is_absolute() or ".." in output.parts:
        raise cloud.CloudError("frame output must be an absolute path without parent traversal")
    directory = None
    try:
        directory = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        parent = os.fstat(directory)
        if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) & 0o077:
            raise cloud.CloudError("frame directory must be private and owned by this user")
        try:
            os.stat(output.name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise cloud.CloudError("frame output already exists; choose a new filename")
        observation = cloud.observe(session, device_id)
        if observation.get("model") != "P1S":
            raise cloud.CloudError("this camera reader currently supports P1S only; no grant requested")
        modules = observation.get("firmware_modules", [])
        firmware = [m.get("sw_ver") for m in modules if isinstance(m, dict) and m.get("name") == "ota"]
        if (observation.get("fresh_state_received") is not True
                or observation.get("version_reply_matched") is not True or len(firmware) != 1
                or not isinstance(firmware[0], str) or not _FIRMWARE.fullmatch(firmware[0])):
            raise cloud.CloudError("camera capture needs one fresh matched firmware version")
        url = _grant(session, device_id, firmware[0])
        _media_path(library)  # an app update between preparation and launch must not change the pinned runtime
        data, dimensions = _read_jpeg(reader, library, url)
        staging = ".cad-agent-frame-" + uuid.uuid4().hex
        fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            # A complete file appears atomically; link() refuses to overwrite any existing destination.
            os.link(staging, output.name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            os.fsync(directory)
        finally:
            os.unlink(staging, dir_fd=directory)
        return {"model": "P1S", "frame": str(output), "width": dimensions[0], "height": dimensions[1],
                "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "received_at_utc": datetime.now(timezone.utc).isoformat(),
                "bed_clear": None, "print_authorized": False}
    except OSError:
        raise cloud.CloudError("cannot create a new private camera output") from None
    finally:
        if directory is not None:
            os.close(directory)
