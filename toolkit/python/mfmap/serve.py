# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""``mfmap serve``: the Notes, Parser, Backlog and Map tabs, refreshed while a parse runs or the notes
change. The page is read-only: questions are answered with ``mfmap answer``. It is one Svelte
app, prebuilt into ``static/app.js`` and ``app.css`` from ``toolkit/web``, so it needs no network;
it reads ``/api/report``, ``/api/graph`` and ``/api/source``."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from . import graph as graphs
from . import plan as plans
from .report import plan_view, report
from .store import connect

PAGE = Path(__file__).with_name("page.html")
STATIC = Path(__file__).with_name("static")
STATIC_TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}


def source(store: str | os.PathLike, path: str, line: int, context: int = 12,
           plan: Optional[str] = None) -> Optional[dict]:
    """Lines around ``line`` of a file the store knows about, else None: a parsed source or
    copybook, a file a relationship, entity or diagnostic cites, ``migration.json`` or a unit's
    notes."""
    conn = connect(store)
    try:
        known = any(r["path"] == path or path in json.loads(r["deps"] or "{}")
                    for r in conn.execute("SELECT path, deps FROM files")) or any(
            conn.execute(f"SELECT 1 FROM {table} WHERE path = ? LIMIT 1", (path,)).fetchone()
            for table in ("relationships", "entities", "diagnostics"))
        if not known:
            run = conn.execute("SELECT root FROM runs ORDER BY id DESC LIMIT 1").fetchone()
            found = plans.find(Path(store), run["root"] if run else str(Path(store).parent), plan)
            known = bool(found) and (Path(path) == found or (Path(path).parent == found.parent / "units"
                                                             and path.endswith(".md")))
    finally:
        conn.close()
    if not known or not Path(path).is_file():
        return None
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, line - context)
    return {"path": path, "line": line, "start": start, "lines": lines[start - 1: line + context]}


def make_handler(store: Path, plan: Optional[str]):
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
                body = {**report(store), "plan": plan_view(store, plan)}
                self.send(200, json.dumps(body).encode(), "application/json")
            elif url.path == "/api/source":
                found = source(store, query.get("path", ""), int(query.get("line") or "1"), plan=plan)
                self.send(200 if found else 404, json.dumps(found).encode(), "application/json")
            elif url.path == "/api/graph":
                self.graph(query)
            elif url.path.startswith("/static/") and (STATIC / url.path[8:]).is_file() \
                    and "/" not in url.path[8:] and Path(url.path).suffix in STATIC_TYPES:
                self.send(200, (STATIC / url.path[8:]).read_bytes(), STATIC_TYPES[Path(url.path).suffix])
            else:
                self.send(404, b"not found", "text/plain")

        def graph(self, query: dict) -> None:
            """One level of the map. The ETag is the store's version, so a page polling with
            If-None-Match gets 304 until a parse, resolver, unit or question changes."""
            tag = '"' + graphs.version(store, plan) + '"'
            if self.headers.get("If-None-Match") == tag:
                self.send_response(304)
                self.send_header("ETag", tag)
                self.end_headers()
                return
            try:
                body = graphs.graph(store, plan, query.get("level", "estate"), query.get("id") or None)
            except KeyError as e:
                self.send(404, json.dumps({"error": e.args[0]}).encode(), "application/json")
                return
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("ETag", tag)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def serve(store: str | os.PathLike, host: str = "127.0.0.1", port: int = 8765,
          plan: Optional[str] = None) -> None:
    store = Path(store).resolve()
    server = ThreadingHTTPServer((host, port), make_handler(store, plan))
    print(f"report for {store} at http://{host}:{port}/", flush=True)
    server.serve_forever()
