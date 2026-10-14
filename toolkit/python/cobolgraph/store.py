# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""A durable store for parser output: ``<store>/map.db`` (SQLite) and ``<store>/graphs/``.

Each ``parse`` run records which files it parsed, their status and diagnostics, and the
programs, calls and data access found in them, as each file finishes. A file whose source, used
copybooks, parser and options are unchanged since its last parse is not parsed again.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional, Sequence

from .crosscheck import PATTERNS, TextScan, crosscheck
from .model import Project, SourceFile, call_edges, data_access
from .run import output_names, parse_one, parser_options

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY, started REAL, finished REAL, status TEXT, root TEXT,
  parser TEXT, options TEXT, total INTEGER);
CREATE TABLE IF NOT EXISTS files (
  path TEXT PRIMARY KEY, graph TEXT, status TEXT, errors INTEGER, warnings INTEGER,
  message TEXT, run_id INTEGER, parsed REAL, seconds REAL, cache_key TEXT, deps TEXT,
  copies TEXT);
CREATE TABLE IF NOT EXISTS run_files (
  run_id INTEGER, path TEXT, status TEXT, errors INTEGER, cached INTEGER, seconds REAL,
  PRIMARY KEY (run_id, path));
CREATE TABLE IF NOT EXISTS diagnostics (
  file TEXT, severity TEXT, code TEXT, message TEXT, path TEXT, line INTEGER);
CREATE TABLE IF NOT EXISTS programs (
  file TEXT, name TEXT, paragraphs INTEGER, statements INTEGER, data_items INTEGER,
  copybooks TEXT);
CREATE TABLE IF NOT EXISTS calls (
  file TEXT, program TEXT, paragraph TEXT, via TEXT, target TEXT, resolved TEXT,
  expression TEXT, candidates TEXT, path TEXT, line INTEGER);
CREATE TABLE IF NOT EXISTS access (
  file TEXT, program TEXT, paragraph TEXT, store TEXT, resource TEXT, mode TEXT,
  resolved TEXT, expression TEXT, verb TEXT, path TEXT, line INTEGER);
CREATE TABLE IF NOT EXISTS file_controls (
  file TEXT, program TEXT, name TEXT, assign TEXT, organization TEXT, access_mode TEXT,
  record_key TEXT, path TEXT, line INTEGER);
CREATE TABLE IF NOT EXISTS checks (
  run_id INTEGER, kind TEXT, text INTEGER, graph INTEGER, differences TEXT);
CREATE INDEX IF NOT EXISTS diagnostics_file ON diagnostics (file);
CREATE INDEX IF NOT EXISTS programs_file ON programs (file);
CREATE INDEX IF NOT EXISTS calls_file ON calls (file);
CREATE INDEX IF NOT EXISTS access_file ON access (file);
CREATE INDEX IF NOT EXISTS file_controls_file ON file_controls (file);
"""
PER_FILE_TABLES = ("diagnostics", "programs", "calls", "access", "file_controls")


def connect(store: str | os.PathLike) -> sqlite3.Connection:
    """Open ``<store>/map.db``, creating it if needed. WAL lets the dashboard read during a run."""
    Path(store).mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(Path(store) / "map.db", timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def sha256(path: str | os.PathLike) -> Optional[str]:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def find_copybook(name: str, dirs: Sequence[str], extensions: Sequence[str]) -> Optional[str]:
    for d in dirs:
        for e in extensions:
            for candidate in (name + e, name.upper() + e):
                if (Path(d) / candidate).is_file():
                    return str(Path(d) / candidate)
    return None


def dependencies(graph: SourceFile) -> tuple[dict[str, Optional[str]], dict[str, Optional[str]]]:
    """Copybook files the source used with their hashes, and each COPY name with the file it
    resolved to (None when no folder had it, including the parser's built-in copybooks)."""
    deps, copies = {}, {}
    for node in graph.nodes("CopyNode"):
        path = graph._path(node.data.get("uri") or "")
        if path:
            deps[path] = sha256(path)
        if node.name:
            copies[node.name] = path
    return deps, copies


def cache_key(source_hash, parser, deps) -> str:
    text = json.dumps([source_hash, parser, sorted(deps.items())])
    return hashlib.sha256(text.encode()).hexdigest()


def ingest(conn: sqlite3.Connection, path: str, graph: SourceFile) -> None:
    """Replace a file's rows with what its graph contains."""
    for table in PER_FILE_TABLES:
        conn.execute(f"DELETE FROM {table} WHERE file = ?", (path,))
    for d in graph.diagnostics:
        location = (d.get("location") or {}).get("location") or {}
        start = (location.get("range") or {}).get("start") or {}
        conn.execute(
            "INSERT INTO diagnostics VALUES (?, ?, ?, ?, ?, ?)",
            (path, d.get("severity"), d.get("code"), d.get("message") or d.get("suggestion"),
             graph._path(location.get("uri", "")), start.get("line", -1) + 1))
    for p in graph.programs:
        conn.execute(
            "INSERT INTO programs VALUES (?, ?, ?, ?, ?, ?)",
            (path, p.name, len(p.paragraphs), len(p.statements), len(p.all_data_items),
             json.dumps(sorted(set(p.copybooks)))))
        for e in call_edges(p):
            loc = e.statement.location
            conn.execute(
                "INSERT INTO calls VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (path, p.name, e.statement.paragraph.name if e.statement.paragraph else None,
                 e.via, e.target, e.resolved, e.expression, json.dumps(list(e.candidates)),
                 loc.path if loc else None, loc.line if loc else None))
        for a in data_access(p):
            loc = a.statement.location
            conn.execute(
                "INSERT INTO access VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (path, p.name, a.paragraph.name if a.paragraph else None, a.store, a.resource,
                 a.mode, a.resolved, a.expression, a.statement.verb,
                 loc.path if loc else None, loc.line if loc else None))
        for f in p.files:
            loc = f.location
            conn.execute(
                "INSERT INTO file_controls VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (path, p.name, f.name, f.assign, f.organization, f.access_mode, f.record_key,
                 loc.path if loc else None, loc.line if loc else None))


def parse(
    store: str | os.PathLike,
    jar: str | os.PathLike,
    sources: Sequence[Path],
    copybook_dirs: Sequence[str | os.PathLike] = (),
    copybook_extensions: Sequence[str] = (),
    jobs: int = 4,
    force: bool = False,
    progress: Optional[Callable[[str, str], None]] = None,
) -> int:
    """Parse ``sources`` into the store and return the run id. Each file's results are committed
    as soon as it finishes, so a dashboard can follow the run."""
    store = Path(store)
    conn = connect(store)
    options = parser_options(copybook_dirs, copybook_extensions)
    dirs = [str(Path(d).resolve()) for d in copybook_dirs]
    extensions = ["", *[e if e.startswith(".") else "." + e for e in copybook_extensions]] \
        if copybook_extensions else ["", ".cpy"]
    parser = sha256(jar)
    names = output_names(list(sources))
    with conn:
        run_id = conn.execute(
            "INSERT INTO runs (started, status, root, parser, options, total) VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), "running", os.getcwd(), parser, json.dumps(options), len(sources)),
        ).lastrowid

    todo = []
    for source in sources:
        path = str(source.resolve())
        graph = store / "graphs" / names[source]
        row = conn.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()
        source_hash = sha256(path)
        if row and not force and row["cache_key"] and graph.is_file():
            # Reuse the last parse when the source, the copybooks it used and the parser are the
            # same, and every COPY still resolves to the same file with the current folders.
            deps = {p: sha256(p) for p in json.loads(row["deps"] or "{}")}
            copies = json.loads(row["copies"] or "{}")
            same_copies = all(find_copybook(n, dirs, extensions) == p for n, p in copies.items())
            if same_copies and cache_key(source_hash, parser, deps) == row["cache_key"]:
                with conn:
                    conn.execute("UPDATE files SET run_id = ? WHERE path = ?", (run_id, path))
                    conn.execute("INSERT INTO run_files VALUES (?, ?, ?, ?, 1, 0)",
                                 (run_id, path, row["status"], row["errors"]))
                if progress:
                    progress(path, "cached")
                continue
        with conn:
            conn.execute(
                "INSERT INTO files (path, graph, status, run_id) VALUES (?, ?, 'queued', ?) "
                "ON CONFLICT(path) DO UPDATE SET status = 'queued', run_id = excluded.run_id",
                (path, str(graph), run_id))
        todo.append((source, path, graph, source_hash))

    lock = threading.Lock()  # the connection is shared with the worker threads

    def work(item):
        source, path, graph, _ = item
        with lock, conn:
            conn.execute("UPDATE files SET status = 'parsing' WHERE path = ?", (path,))
        started = time.time()
        data = parse_one(jar, source, graph, options)
        return item, data, time.time() - started

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        for future in as_completed([pool.submit(work, item) for item in todo]):
            (source, path, graph_path, source_hash), data, seconds = future.result()
            graph = SourceFile(data)
            errors = len(graph.errors)
            warnings = sum(d.get("severity") == "WARNING" for d in graph.diagnostics)
            status = "crash" if graph.crash else "errors" if errors else "clean"
            deps, copies = dependencies(graph)
            key = cache_key(source_hash, parser, deps) if not graph.crash else None
            with lock, conn:
                ingest(conn, path, graph)
                conn.execute(
                    "UPDATE files SET graph = ?, status = ?, errors = ?, warnings = ?, message = ?, "
                    "parsed = ?, seconds = ?, cache_key = ?, deps = ?, copies = ? WHERE path = ?",
                    (str(graph_path), status, errors, warnings, graph.crash, time.time(), seconds,
                     key, json.dumps(deps), json.dumps(copies), path))
                conn.execute("INSERT INTO run_files VALUES (?, ?, ?, ?, 0, ?)",
                             (run_id, path, status, errors, seconds))
            if progress:
                progress(path, status)

    if copybook_dirs:
        text, graph, differences = crosscheck(load_project(store), TextScan(dirs, extensions))
        with conn:
            for kind in PATTERNS:
                diff = {n: d[kind] for n, d in differences.items() if kind in d}
                conn.execute("INSERT INTO checks VALUES (?, ?, ?, ?, ?)",
                             (run_id, kind, text[kind], graph[kind], json.dumps(diff)))
    with conn:
        conn.execute("UPDATE runs SET finished = ?, status = 'finished' WHERE id = ?",
                     (time.time(), run_id))
    conn.close()
    return run_id


def latest_files(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Files of the most recent run."""
    run = conn.execute("SELECT id FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    if not run:
        return []
    return conn.execute(
        "SELECT f.* FROM files f JOIN run_files r ON r.path = f.path AND r.run_id = ? "
        "UNION SELECT * FROM files WHERE run_id = ? ORDER BY path", (run["id"], run["id"])).fetchall()


def load_project(store: str | os.PathLike, **kwargs) -> Project:
    """The project as of the store's latest run."""
    conn = connect(store)
    try:
        graphs = [row["graph"] for row in latest_files(conn) if row["graph"]]
    finally:
        conn.close()
    return Project(SourceFile.load(g, **kwargs) for g in graphs if Path(g).is_file())
