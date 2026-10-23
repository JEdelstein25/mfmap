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

import collections
import hashlib
import json
import os
import sqlite3
import subprocess
import threading
import time
import urllib.parse
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional, Sequence

from .crosscheck import PATTERNS, TextScan, graph_counts
from . import procedures as sp
from .model import Project, SourceFile, call_edges, commit_points, data_access
from .resolvers import run as run_resolvers
from .run import GraphWorker, output_names, parse_one, parser_options

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY, started REAL, finished REAL, status TEXT, root TEXT,
  parser TEXT, options TEXT, total INTEGER);
CREATE TABLE IF NOT EXISTS files (
  path TEXT PRIMARY KEY, graph TEXT, status TEXT, errors INTEGER, warnings INTEGER,
  message TEXT, run_id INTEGER, parsed REAL, seconds REAL, cache_key TEXT, deps TEXT,
  copies TEXT, counts TEXT);
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
  resolved TEXT, expression TEXT, verb TEXT, path TEXT, line INTEGER, candidates TEXT);
CREATE TABLE IF NOT EXISTS commits (
  file TEXT, program TEXT, paragraph TEXT, kind TEXT, path TEXT, line INTEGER);
CREATE TABLE IF NOT EXISTS entities (
  resolver TEXT, entity TEXT, kind TEXT, note TEXT, path TEXT, line INTEGER);
CREATE TABLE IF NOT EXISTS relationships (
  resolver TEXT, kind TEXT, source TEXT, target TEXT, resolved TEXT, expression TEXT, note TEXT,
  path TEXT, line INTEGER);
CREATE INDEX IF NOT EXISTS relationships_source ON relationships (source);
CREATE INDEX IF NOT EXISTS relationships_target ON relationships (target);
CREATE TABLE IF NOT EXISTS procedures (
  name TEXT, language TEXT, program TEXT, parameters TEXT, result_sets INTEGER,
  reads TEXT, writes TEXT, calls TEXT, path TEXT, line INTEGER);
CREATE TABLE IF NOT EXISTS ddl (path TEXT, result TEXT);
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
CREATE INDEX IF NOT EXISTS commits_file ON commits (file);
"""
PER_FILE_TABLES = ("diagnostics", "programs", "calls", "access", "file_controls", "commits")


def connect(store: str | os.PathLike) -> sqlite3.Connection:
    """Open ``<store>/map.db``, creating it if needed. WAL lets the report page read during a run."""
    Path(store).mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(Path(store) / "map.db", timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    if "counts" not in {r["name"] for r in conn.execute("PRAGMA table_info(files)")}:
        conn.execute("ALTER TABLE files ADD COLUMN counts TEXT")  # stores made before 0.1.1
    if "candidates" not in {r["name"] for r in conn.execute("PRAGMA table_info(access)")}:
        conn.execute("ALTER TABLE access ADD COLUMN candidates TEXT")  # stores made before 0.1.4
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


def rows(path: str, graph: SourceFile) -> dict[str, list[tuple]]:
    """A file's rows for the per-file tables."""
    out: dict[str, list[tuple]] = {table: [] for table in PER_FILE_TABLES}
    for d in graph.diagnostics:
        location = (d.get("location") or {}).get("location") or {}
        start = (location.get("range") or {}).get("start") or {}
        out["diagnostics"].append(
            (path, d.get("severity"), d.get("code"), d.get("message") or d.get("suggestion"),
             graph._path(location.get("uri", "")), start.get("line", -1) + 1))
    for p in graph.programs:
        out["programs"].append(
            (path, p.name, len(p.paragraphs), len(p.statements), len(p.all_data_items),
             json.dumps(sorted(set(p.copybooks)))))
        for e in call_edges(p):
            loc = e.statement.location
            out["calls"].append(
                (path, p.name, e.statement.paragraph.name if e.statement.paragraph else None,
                 e.via, e.target, e.resolved, e.expression, json.dumps(list(e.candidates)),
                 loc.path if loc else None, loc.line if loc else None))
        for a in data_access(p):
            loc = a.statement.location
            out["access"].append(
                (path, p.name, a.paragraph.name if a.paragraph else None, a.store, a.resource,
                 a.mode, a.resolved, a.expression, a.statement.verb,
                 loc.path if loc else None, loc.line if loc else None, json.dumps(list(a.candidates))))
        for c in commit_points(p):
            loc = c.statement.location
            out["commits"].append(
                (path, p.name, c.statement.paragraph.name if c.statement.paragraph else None, c.kind,
                 loc.path if loc else None, loc.line if loc else None))
        for f in p.files:
            loc = f.location
            out["file_controls"].append(
                (path, p.name, f.name, f.assign, f.organization, f.access_mode, f.record_key,
                 loc.path if loc else None, loc.line if loc else None))
    return out


def write_rows(conn: sqlite3.Connection, path: str, table_rows: dict[str, list[tuple]]) -> None:
    """Replace a file's rows in the per-file tables."""
    for table in PER_FILE_TABLES:
        conn.execute(f"DELETE FROM {table} WHERE file = ?", (path,))
        if table_rows[table]:
            marks = ", ".join("?" * len(table_rows[table][0]))
            conn.executemany(f"INSERT INTO {table} VALUES ({marks})", table_rows[table])


def ingest(conn: sqlite3.Connection, path: str, graph: SourceFile) -> None:
    """Replace a file's rows with what its graph contains."""
    write_rows(conn, path, rows(path, graph))


_scans: dict = {}


def analyze(path: str, graph_path: str, source_hash, parser, dirs: Sequence[str],
            extensions: Sequence[str], scan_enabled: bool) -> dict:
    """Everything the store records about one parsed file. Runs in a separate process so the
    JSON decoding and model building of many files proceed in parallel."""
    graph = SourceFile(json.loads(Path(graph_path).read_text(encoding="utf-8")))
    errors = len(graph.errors)
    deps, copies = dependencies(graph)
    scan = None
    if scan_enabled and not graph.crash:
        scan = _scans.setdefault((tuple(dirs), tuple(extensions)), TextScan(dirs, extensions))
    return {
        "rows": rows(path, graph),
        "errors": errors,
        "warnings": sum(d.get("severity") == "WARNING" for d in graph.diagnostics),
        "status": "crash" if graph.crash else "errors" if errors else "clean",
        "crash": graph.crash,
        "key": cache_key(source_hash, parser, deps) if not graph.crash else None,
        "deps": deps,
        "copies": copies,
        # Statement counts from the graph and from a text scan, for the count check.
        "counts": {"graph": dict(sum((graph_counts(p) for p in graph.programs), collections.Counter())),
                   "text": dict(scan.counts(Path(path))) if scan else None},
    }


def parse(
    store: str | os.PathLike,
    jar: str | os.PathLike,
    sources: Sequence[Path],
    copybook_dirs: Sequence[str | os.PathLike] = (),
    copybook_extensions: Sequence[str] = (),
    jobs: int = 4,
    force: bool = False,
    progress: Optional[Callable[[str, str], None]] = None,
    ddl: Sequence[str | os.PathLike] = (),
) -> int:
    """Parse ``sources`` into the store and return the run id. Each file's results are committed
    as soon as it finishes, so the report page can follow the run. Stored procedure definitions
    are read from DDL files under the current folder and from the ``ddl`` files or folders. Then
    every resolver runs (see ``mfmap.resolvers``)."""
    store = Path(store)
    conn = connect(store)
    options = parser_options(copybook_dirs, copybook_extensions)
    dirs = [str(Path(d).resolve()) for d in copybook_dirs]
    extensions = ["", *[e if e.startswith(".") else "." + e for e in copybook_extensions]] \
        if copybook_extensions else ["", ".cpy"]
    parser = sha256(jar)
    scan = TextScan(dirs, extensions) if copybook_dirs else None
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
    local, workers = threading.local(), []  # one parser process per thread, reused for its files

    def work(item):
        source, path, graph, source_hash = item
        with lock, conn:
            conn.execute("UPDATE files SET status = 'parsing' WHERE path = ?", (path,))
        if not hasattr(local, "worker"):
            local.worker = GraphWorker(jar, options)
            with lock:
                workers.append(local.worker)
        started = time.time()
        parse_one(jar, source, graph, options, worker=local.worker)
        seconds = time.time() - started
        result = analyses.submit(analyze, path, str(graph), source_hash, parser, dirs, extensions,
                                 scan is not None).result()
        return item, result, seconds

    try:
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool, \
                ProcessPoolExecutor(max_workers=max(1, jobs)) as analyses:
            for future in as_completed([pool.submit(work, item) for item in todo]):
                (source, path, graph_path, source_hash), r, seconds = future.result()
                with lock, conn:
                    write_rows(conn, path, r["rows"])
                    conn.execute(
                        "UPDATE files SET graph = ?, status = ?, errors = ?, warnings = ?, message = ?, "
                        "parsed = ?, seconds = ?, cache_key = ?, deps = ?, copies = ?, counts = ? "
                        "WHERE path = ?",
                        (str(graph_path), r["status"], r["errors"], r["warnings"], r["crash"],
                         time.time(), seconds, r["key"], json.dumps(r["deps"]), json.dumps(r["copies"]),
                         json.dumps(r["counts"]), path))
                    conn.execute("INSERT INTO run_files VALUES (?, ?, ?, ?, 0, ?)",
                                 (run_id, path, r["status"], r["errors"], seconds))
                if progress:
                    progress(path, r["status"])
    finally:
        for worker in workers:
            worker.close()

    if scan:
        # Sum the per-file counts of this run's files; reused files keep their earlier counts.
        text, graph, differences = collections.Counter(), collections.Counter(), {}
        for row in latest_files(conn):
            counts = json.loads(row["counts"] or "null")
            if not counts or counts.get("text") is None:
                continue
            text.update(counts["text"])
            graph.update(counts["graph"])
            names = [p["name"] for p in conn.execute("SELECT name FROM programs WHERE file = ?", (row["path"],))]
            for kind in PATTERNS:
                t, g = counts["text"].get(kind, 0), counts["graph"].get(kind, 0)
                if t != g:
                    differences.setdefault(", ".join(names) or os.path.basename(row["path"]), {})[kind] = (t, g)
        with conn:
            for kind in PATTERNS:
                diff = {n: d[kind] for n, d in differences.items() if kind in d}
                conn.execute("INSERT INTO checks VALUES (?, ?, ?, ?, ?)",
                             (run_id, kind, text[kind], graph[kind], json.dumps(diff)))
    with conn:
        conn.execute("DELETE FROM procedures")
        conn.executemany(
            "INSERT INTO procedures VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(d.name, d.language, d.program, json.dumps(d.parameters), d.result_sets, json.dumps(d.reads),
              json.dumps(d.writes), json.dumps(d.calls), d.path, d.line)
             for d in sp.procedures(sp.find_ddl(os.getcwd(), ddl))])
        conn.execute("DELETE FROM ddl")
        conn.executemany("INSERT INTO ddl VALUES (?, ?)", read_ddl(jar, sp.find_schema_ddl(os.getcwd(), ddl)))
    conn.close()
    run_resolvers(store)
    conn = connect(store)
    with conn:
        conn.execute("UPDATE runs SET finished = ?, status = 'finished' WHERE id = ?",
                     (time.time(), run_id))
    conn.close()
    return run_id


def read_ddl(jar: str | os.PathLike, files: Sequence[Path]) -> list[tuple[str, str]]:
    """Tables, keys, indexes and views in DDL files, from the parser's ``ddl`` command: one
    (path, JSON) pair per file."""
    if not files:
        return []
    out = subprocess.run(["java", "-jar", str(jar), "ddl", *map(str, files)],
                         capture_output=True, text=True, check=True).stdout
    rows = []
    for line in out.splitlines():
        if line.startswith("{"):
            uri = urllib.parse.urlparse(json.loads(line)["uri"])
            rows.append((str(Path(urllib.parse.unquote(uri.path)).resolve()), line))
    return rows


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
        rows = [(row["path"], row["graph"]) for row in latest_files(conn) if row["graph"]]
    finally:
        conn.close()
    files = []
    for path, g in rows:
        if Path(g).is_file():
            files.append(SourceFile.load(g, **kwargs))
            files[-1].source = path
    return Project(files)


def apply_program_names(conn: sqlite3.Connection, project: Project) -> None:
    """Give the per-file rows the names ``project`` uses. Rows are written with the PROGRAM-ID, so
    a program Project named after its file is renamed here, and named back when it no longer needs
    to be. Only files with one program are renamed; a nested program keeps its PROGRAM-ID."""
    with conn:
        for f in project.files:
            if len(f.programs) != 1:
                continue
            name = f.programs[0].name
            conn.execute("UPDATE programs SET name = ? WHERE file = ? AND name != ?", (name, f.source, name))
            for table in ("calls", "access", "file_controls", "commits"):
                conn.execute(f"UPDATE {table} SET program = ? WHERE file = ? AND program != ?",
                             (name, f.source, name))
