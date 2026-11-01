"""Serve a CAD project's root over http, so gallery pages can hand 3MF files to
a slicer by URL (``bambustudio://open?file=http://...``)."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional, Tuple

from cadagent.project import CadProject

URL_FILE = "server-url.txt"

def make_server(
    project: CadProject,
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> Tuple[ThreadingHTTPServer, str]:
    """Bind the server (port 0 = any free port) and record its preview URL in
    ``<preview_dir>/server-url.txt``. The caller runs ``serve_forever``."""
    host = host or project.serve.host
    port = project.serve.port if port is None else port
    handler = partial(SimpleHTTPRequestHandler, directory=str(project.root))
    server = ThreadingHTTPServer((host, port), handler)
    shown = "127.0.0.1" if host in ("", "0.0.0.0") else host
    try:
        preview = project.preview_dir.relative_to(project.root).as_posix().strip("/")
    except ValueError:
        preview = ""
    url = f"http://{shown}:{server.server_port}/" + (f"{preview}/" if preview else "")
    project.preview_dir.mkdir(parents=True, exist_ok=True)
    (project.preview_dir / URL_FILE).write_text(url + "\n")
    return server, url

def serve(project: CadProject, host: Optional[str] = None, port: Optional[int] = None) -> int:
    server, url = make_server(project, host, port)
    print(url, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
