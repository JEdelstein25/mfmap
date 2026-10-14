# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""``cobolgraph serve``: the report page, refreshed while a parse runs or the notes change."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .report import report
from .store import connect

PAGE = Path(__file__).with_name("page.html")


def source(store: str | os.PathLike, path: str, line: int, context: int = 12) -> Optional[dict]:
    """Lines around ``line`` of a source or copybook the store knows about, else None."""
    conn = connect(store)
    try:
        known = any(r["path"] == path or path in json.loads(r["deps"] or "{}")
                    for r in conn.execute("SELECT path, deps FROM files"))
    finally:
        conn.close()
    if not known or not Path(path).is_file():
        return None
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, line - context)
    return {"path": path, "line": line, "start": start, "lines": lines[start - 1: line + context]}


def make_handler(store: Path, spec: Optional[str]):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            if url.path in ("/", "/index.html"):
                self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/report":
                markdown, status = report(store, spec)
                self.send(200, json.dumps({"markdown": markdown, **status}).encode(), "application/json")
            elif url.path == "/api/source":
                found = source(store, query.get("path", ""), int(query.get("line", "1")))
                self.send(200 if found else 404, json.dumps(found).encode(), "application/json")
            else:
                self.send(404, b"not found", "text/plain")

    return Handler


def serve(store: str | os.PathLike, host: str = "127.0.0.1", port: int = 8765,
          spec: Optional[str] = None) -> None:
    store = Path(store).resolve()
    server = ThreadingHTTPServer((host, port), make_handler(store, spec))
    print(f"report for {store} at http://{host}:{port}/", flush=True)
    server.serve_forever()
