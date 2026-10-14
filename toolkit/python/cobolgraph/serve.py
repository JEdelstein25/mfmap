# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""``cobolgraph serve``: a dashboard over a store, refreshed while a parse runs."""

from __future__ import annotations

import json
import os
import sqlite3
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .model import DataItem, SourceFile
from .store import connect, latest_files

DASHBOARD = Path(__file__).with_name("dashboard.html")


def rows(conn: sqlite3.Connection, sql: str, *args) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


class Dashboard:
    def __init__(self, store: str | os.PathLike, spec: Optional[str] = None):
        self.store = Path(store).resolve()
        self.spec = spec
        self._graphs: dict[str, tuple[float, SourceFile]] = {}

    def connect(self) -> sqlite3.Connection:
        return connect(self.store)

    def root(self, conn) -> str:
        run = conn.execute("SELECT root FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        return run["root"] if run else str(self.store.parent)

    def spec_path(self, root: str) -> Optional[Path]:
        for candidate in [self.spec, Path(root) / "migration-spec.json",
                          self.store.parent / "migration-spec.json"]:
            if candidate and Path(candidate).is_file():
                return Path(candidate)
        return None

    def state(self) -> dict:
        conn = self.connect()
        try:
            root = self.root(conn)
            rel = lambda p: os.path.relpath(p, root) if p else p  # noqa: E731
            runs = rows(conn, """
                SELECT r.*, COUNT(f.path) AS done,
                  SUM(f.status = 'clean') AS clean, SUM(f.status = 'errors') AS errors,
                  SUM(f.status = 'crash') AS crash, SUM(f.cached) AS cached
                FROM runs r LEFT JOIN run_files f ON f.run_id = r.id
                GROUP BY r.id ORDER BY r.id DESC LIMIT 30""")
            files = [dict(r) for r in latest_files(conn)]
            current = {f["path"] for f in files}
            programs_by_file = defaultdict(list)
            programs = []
            for p in rows(conn, "SELECT * FROM programs ORDER BY name"):
                if p["file"] in current:
                    programs_by_file[p["file"]].append(p["name"])
                    programs.append(p)
            status = {f["path"]: f["status"] for f in files}
            for p in programs:
                p["status"] = status.get(p["file"])
                p["file"] = rel(p["file"])
                p["copybooks"] = json.loads(p["copybooks"] or "[]")
            for f in files:
                f["programs"] = programs_by_file.get(f["path"], [])
                for key in ("cache_key", "deps", "copies", "graph"):
                    f.pop(key, None)
                f["path"] = rel(f["path"])

            causes = {}
            for d in rows(conn, "SELECT * FROM diagnostics WHERE severity = 'ERROR'"):
                if d["file"] not in current:
                    continue
                cause = causes.setdefault(d["message"] or d["code"] or "?", {
                    "message": d["message"] or d["code"] or "?", "code": d["code"],
                    "count": 0, "files": set(), "where": []})
                cause["count"] += 1
                cause["files"].add(rel(d["file"]))
                if len(cause["where"]) < 50:
                    cause["where"].append({"path": rel(d["path"]), "abs": d["path"], "line": d["line"]})
            causes = sorted(causes.values(), key=lambda c: -c["count"])
            for c in causes:
                c["files"] = sorted(c["files"])

            def evidence(table: str) -> list[dict]:
                result = []
                for r in rows(conn, f"SELECT * FROM {table}"):
                    if r["file"] not in current:
                        continue
                    r["abs"] = r.get("path")
                    r["path"] = rel(r.get("path"))
                    r["file"] = rel(r["file"])
                    if "candidates" in r:
                        r["candidates"] = json.loads(r["candidates"] or "[]")
                    result.append(r)
                return result

            # The latest run that has a count check; a running run adds its check at the end.
            checks = rows(conn, "SELECT * FROM checks WHERE run_id = (SELECT MAX(run_id) FROM checks)")
            for c in checks:
                c["differences"] = json.loads(c["differences"] or "{}")
            spec_file = self.spec_path(root)
            spec, spec_error = None, None
            if spec_file:
                try:
                    spec = json.loads(spec_file.read_text(encoding="utf-8"))
                except (OSError, ValueError) as e:
                    spec_error = str(e)
            return {
                "store": str(self.store), "root": root, "runs": runs, "files": files,
                "programs": programs, "causes": causes, "checks": checks,
                "calls": evidence("calls"), "access": evidence("access"),
                "fileControls": evidence("file_controls"),
                "spec": spec, "specPath": str(spec_file) if spec_file else None,
                "specError": spec_error,
            }
        finally:
            conn.close()

    def graph(self, path: str) -> Optional[SourceFile]:
        mtime = os.path.getmtime(path)
        cached = self._graphs.get(path)
        if not cached or cached[0] != mtime:
            self._graphs[path] = (mtime, SourceFile.load(path))
        return self._graphs[path][1]

    def program(self, name: str) -> Optional[dict]:
        conn = self.connect()
        try:
            root = self.root(conn)
            row = conn.execute(
                "SELECT f.graph, f.path FROM programs p JOIN files f ON f.path = p.file "
                "WHERE p.name = ? ORDER BY f.parsed DESC LIMIT 1", (name,)).fetchone()
        finally:
            conn.close()
        if not row or not row["graph"] or not Path(row["graph"]).is_file():
            return None
        program = next((p for p in self.graph(row["graph"]).programs if p.name == name), None)
        if program is None:
            return None
        rel = lambda loc: {"path": os.path.relpath(loc.path, root), "abs": loc.path,  # noqa: E731
                           "line": loc.line} if loc and loc.path else None

        def item(i: DataItem, depth: int = 0) -> dict:
            return {
                "name": i.name, "level": i.level, "pic": i.pic, "usage": i.usage,
                "occurs": i.occurs, "value": i.value, "copybook": i.copybook,
                "redefines": i.redefines.name if i.redefines else None,
                "references": len(i.references), "at": rel(i.location),
                "children": [item(c, depth + 1) for c in i.children] if depth < 6 else [],
            }

        paragraphs = []
        for para in program.paragraphs + program.sections:
            statements = para.statements
            paragraphs.append({
                "name": para.name, "at": rel(para.location), "statements": len(statements),
                "performs": sorted({p.target_name for p in statements
                                    if hasattr(p, "target_name") and p.target_name}),
                "performedBy": sorted({p.paragraph.name for p in para.performed_by if p.paragraph}),
                "verbs": sorted({s.verb for s in statements}),
            })
        return {
            "name": name, "file": os.path.relpath(row["path"], root), "abs": row["path"],
            "paragraphs": paragraphs, "dataItems": [item(i) for i in program.data_items],
            "copybooks": sorted(set(program.copybooks)),
        }

    def source(self, path: str, line: int, context: int = 12) -> Optional[dict]:
        conn = self.connect()
        try:  # only sources and copybooks the store knows about
            known = any(r["path"] == path or path in json.loads(r["deps"] or "{}")
                        for r in conn.execute("SELECT path, deps FROM files"))
        finally:
            conn.close()
        if not known or not Path(path).is_file():
            return None
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, line - context)
        return {"path": path, "line": line, "start": start,
                "lines": lines[start - 1: line + context]}


def make_handler(dashboard: Dashboard):
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

        def json(self, value) -> None:
            if value is None:
                self.send(404, b'{"error": "not found"}', "application/json")
            else:
                self.send(200, json.dumps(value, default=list).encode(), "application/json")

        def do_GET(self):
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            if url.path in ("/", "/index.html"):
                self.send(200, DASHBOARD.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/state":
                self.json(dashboard.state())
            elif url.path == "/api/program":
                self.json(dashboard.program(query.get("name", "")))
            elif url.path == "/api/source":
                self.json(dashboard.source(query.get("path", ""), int(query.get("line", "1"))))
            else:
                self.send(404, b"not found", "text/plain")

    return Handler


def serve(store: str | os.PathLike, host: str = "127.0.0.1", port: int = 8765,
          spec: Optional[str] = None) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(Dashboard(store, spec)))
    print(f"dashboard for {Path(store).resolve()} at http://{host}:{port}/", flush=True)
    server.serve_forever()
