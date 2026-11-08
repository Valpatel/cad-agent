#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""External one-frame reader; never import this module into cadagent.

C ABI declarations adapted from BambuStudio BambuTunnel.h at
355d71eee5a9ebc794693fe57e63674806019770 (AGPL-3.0). See README.md and COPYING.
No proprietary code is included. The parent pins its installed media library,
enforces the process deadline, and verifies the complete JPEG.
"""
from __future__ import annotations

import ctypes as C
import json
import os
from pathlib import Path
import resource
import sys
import time
from urllib.parse import parse_qs, urlsplit


class Video(C.Structure):
    _fields_ = [("width", C.c_int), ("height", C.c_int), ("frame_rate", C.c_int)]


class Audio(C.Structure):
    _fields_ = [("sample_rate", C.c_int), ("channel_count", C.c_int), ("sample_size", C.c_int)]


class Format(C.Union):
    _fields_ = [("video", Video), ("audio", Audio)]


class Stream(C.Structure):
    _fields_ = [("type", C.c_int), ("sub_type", C.c_int), ("format", Format),
                ("format_type", C.c_int), ("format_size", C.c_int),
                ("max_frame_size", C.c_int), ("format_buffer", C.c_void_p)]


class Sample(C.Structure):
    _fields_ = [("itrack", C.c_int), ("size", C.c_int), ("flags", C.c_int),
                ("buffer", C.c_void_p), ("decode_time", C.c_ulonglong)]


class ReadError(Exception):
    pass


def bind(lib, name, args, result=C.c_int):
    function = getattr(lib, name)
    function.argtypes, function.restype = args, result
    return function


def read_frame(library: str, url: str, output: Path) -> dict:
    """Read only VIDE/MJPG/video_jpeg samples using the pinned C interface."""
    if C.sizeof(C.c_void_p) != 8 or C.sizeof(Stream) != 40 or C.sizeof(Sample) != 32:
        raise ReadError("unsupported_native_abi")
    lib = C.CDLL(library)
    init = bind(lib, "Bambu_Init", [])
    deinit = bind(lib, "Bambu_Deinit", [], None)
    create = bind(lib, "Bambu_Create", [C.POINTER(C.c_void_p), C.c_char_p])
    destroy = bind(lib, "Bambu_Destroy", [C.c_void_p], None)
    open_stream = bind(lib, "Bambu_Open", [C.c_void_p])
    close = bind(lib, "Bambu_Close", [C.c_void_p], None)
    start = bind(lib, "Bambu_StartStream", [C.c_void_p, C.c_bool])
    count = bind(lib, "Bambu_GetStreamCount", [C.c_void_p])
    info = bind(lib, "Bambu_GetStreamInfo", [C.c_void_p, C.c_int, C.POINTER(Stream)])
    sample = bind(lib, "Bambu_ReadSample", [C.c_void_p, C.POINTER(Sample)])
    free_log = bind(lib, "Bambu_FreeLogMsg", [C.c_void_p], None)
    logger_type = C.CFUNCTYPE(None, C.c_void_p, C.c_int, C.c_void_p)
    set_logger = bind(lib, "Bambu_SetLogger", [C.c_void_p, logger_type, C.c_void_p], None)

    @logger_type
    def discard_log(context, level, pointer):
        if pointer:
            free_log(pointer)

    tunnel = C.c_void_p()
    initialized = False
    try:
        if init() != 0:
            raise ReadError("native_init_failed")
        initialized = True
        if create(C.byref(tunnel), url.encode("ascii")) != 0 or not tunnel:
            raise ReadError("native_create_failed")
        set_logger(tunnel, discard_log, None)
        if open_stream(tunnel) not in (0, 2):
            raise ReadError("native_open_failed")
        deadline = time.monotonic() + 12
        while True:
            code = start(tunnel, True)
            if code == 0:
                break
            if code != 2 or time.monotonic() >= deadline:
                raise ReadError("native_start_failed")
            time.sleep(0.1)
        tracks = count(tunnel)
        if not 1 <= tracks <= 16:
            raise ReadError("invalid_stream_count")
        video = None
        for track in range(tracks):
            description = Stream()
            if info(tunnel, track, C.byref(description)) == 0 and description.type == 0:
                if description.sub_type != 1 or description.format_type != 2:
                    raise ReadError("not_a_jpeg_stream")
                if not (16 <= description.format.video.width <= 4096
                        and 16 <= description.format.video.height <= 4096):
                    raise ReadError("invalid_video_dimensions")
                video = (track, description.format.video.width, description.format.video.height)
                break
        if video is None:
            raise ReadError("no_video_stream")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            packet = Sample()
            code = sample(tunnel, C.byref(packet))
            if code in (2, 3):
                time.sleep(0.05)
                continue
            if code != 0:
                raise ReadError("native_sample_failed")
            if packet.itrack != video[0]:
                continue
            if not packet.buffer or not 4 <= packet.size <= 8 * 1024 * 1024:
                raise ReadError("invalid_sample_size")
            data = C.string_at(packet.buffer, packet.size)
            if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
                raise ReadError("invalid_jpeg_markers")
            with output.open("xb") as handle:
                handle.write(data)
            return {"width": video[1], "height": video[2], "bytes": len(data)}
        raise ReadError("frame_wait_expired")
    finally:
        if tunnel:
            close(tunnel)
            destroy(tunnel)
        if initialized:
            deinit()


def main() -> int:
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (9 * 1024 * 1024, 9 * 1024 * 1024))
    if len(sys.argv) != 3:
        return 64
    out = Path(sys.argv[2])
    result = {"ok": False}
    try:
        raw = sys.stdin.buffer.read(32769)
        if len(raw) > 32768:
            raise ReadError("input_too_large")
        url = json.loads(raw)["url"]
        if not isinstance(url, str) or any(ord(c) < 33 or ord(c) > 126 for c in url):
            raise ReadError("invalid_url")
        parsed = urlsplit(url)
        fields = parse_qs(parsed.query, strict_parsing=True)
        if (not url.startswith("bambu:///tutk?") or parsed.netloc or parsed.fragment
                or set(fields) - {"uid", "authkey", "passwd", "region"}
                or not {"uid", "authkey", "passwd"} <= set(fields)
                or any(len(value) != 1 or not value[0] for value in fields.values())):
            raise ReadError("invalid_url")
        result.update(read_frame(sys.argv[1], url, out / "frame.jpg"))
        result["ok"] = True
    except ReadError as exc:
        result["error"] = str(exc)
    except Exception:
        result["error"] = "native_reader_failed"
    with (out / "result.json").open("x") as handle:
        json.dump(result, handle)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
