# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Resolvers turn the parse results and the repository's other files into entities and
relationships in the store's ``entities`` and ``relationships`` tables.

Each module in this package is one resolver: it defines ``NAME`` and ``resolve(ctx)``, which yields
``Entity`` and ``Relationship`` facts. Endpoints are written ``type:name``, such as
``program:ACCTUPD``, ``transaction:AUPD``, ``screen:ACCTSET.ACCTMAP``, ``dataset:PROD.ACCOUNTS``
or ``paragraph:ACCTUPD.2000-PROCESS``. To resolve something new, add a module here. Facts
recorded with ``mfmap record`` have the resolver name ``agent`` and are kept when resolvers run
again.
"""

from __future__ import annotations

import importlib
import os
import pkgutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional, Union

AGENT = "agent"
SKIP_DIRS = {"node_modules", "target", "build", "dist", "__pycache__"}
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".jar", ".class", ".gz", ".tar", ".ico",
          ".xlsx", ".docx", ".pyc", ".so", ".dll", ".exe", ".bin", ".db"}


@dataclass(frozen=True)
class Entity:
    entity: str  # type:name
    kind: str  # what this row says about it, such as "defined" or "business-logic"
    note: Optional[str] = None
    path: Optional[str] = None
    line: Optional[int] = None


@dataclass(frozen=True)
class Relationship:
    kind: str  # calls, reads, writes, starts, sends, runs, performs, ...
    source: str  # type:name
    target: Optional[str]  # type:name, or None when it is only known at run time
    resolved: str = "literal"  # literal, value, declared, inferred or unresolved
    expression: str = ""
    note: Optional[str] = None
    path: Optional[str] = None
    line: Optional[int] = None


Fact = Union[Entity, Relationship]


class Context:
    """What a resolver can read: the store, the parsed programs and the repository's files."""

    def __init__(self, store: Path, root: Path, conn: sqlite3.Connection):
        self.store, self.root, self.conn = store, root, conn
        self._project = None

    @property
    def project(self):
        """The parsed programs (``mfmap.model.Project``), loaded on first use."""
        if self._project is None:
            from ..store import load_project
            self._project = load_project(self.store)
        return self._project

    def files(self, accept: Callable[[Path], bool] = lambda p: True) -> Iterator[tuple[Path, str]]:
        """Text files under the root, skipping hidden folders, build output and the mfmap checkout."""
        for dirpath, dirnames, filenames in os.walk(self.root):
            if "FORK.md" in filenames and Path(dirpath) != self.root:
                dirnames[:] = []
                continue
            dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS)
            for name in sorted(filenames):
                path = Path(dirpath) / name
                if path.suffix.lower() in BINARY or not accept(path):
                    continue
                try:
                    if path.stat().st_size > 4_000_000:
                        continue
                    yield path, path.read_text(encoding="latin-1")
                except OSError:
                    continue


def discover() -> dict[str, Callable[[Context], Iterable[Fact]]]:
    """Every resolver module in this package, by NAME."""
    found = {}
    for module in pkgutil.iter_modules([str(Path(__file__).parent)]):
        mod = importlib.import_module(f"{__name__}.{module.name}")
        if hasattr(mod, "NAME") and hasattr(mod, "resolve"):
            found[mod.NAME] = mod.resolve
    return dict(sorted(found.items()))


def write(conn: sqlite3.Connection, resolver: str, facts: Iterable[Fact]) -> tuple[int, int]:
    """Store a resolver's facts, without duplicates. Returns (entities, relationships) written."""
    entities, relationships = set(), set()
    for f in facts:
        (entities if isinstance(f, Entity) else relationships).add(f)
    conn.executemany("INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?)",
                     [(resolver, e.entity, e.kind, e.note, e.path, e.line) for e in entities])
    conn.executemany("INSERT INTO relationships VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     [(resolver, r.kind, r.source, r.target, r.resolved, r.expression, r.note, r.path, r.line)
                      for r in relationships])
    return len(entities), len(relationships)


def run(store: str | os.PathLike, names: Optional[Iterable[str]] = None) -> dict[str, tuple[int, int]]:
    """Run resolvers (all of them by default), replacing what each one wrote before."""
    from ..store import connect
    store = Path(store).resolve()
    conn = connect(store)
    try:
        last = conn.execute("SELECT root FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        ctx = Context(store, Path(last["root"] if last else store.parent), conn)
        resolvers = discover()
        counts = {}
        for name in names or resolvers:
            if name not in resolvers:
                raise KeyError(f"no resolver {name}; there are {', '.join(resolvers)}")
            facts = list(resolvers[name](ctx))
            with conn:
                conn.execute("DELETE FROM entities WHERE resolver = ?", (name,))
                conn.execute("DELETE FROM relationships WHERE resolver = ?", (name,))
                counts[name] = write(conn, name, facts)
        return counts
    finally:
        conn.close()


def record(store: str | os.PathLike, kind: str, source: str, target: Optional[str] = None,
           note: Optional[str] = None, evidence: Optional[str] = None) -> Fact:
    """Store a fact the agent found itself: a relationship when there is a target, else an entity.
    Recording the same kind, source and target again replaces the earlier row."""
    from ..store import connect
    path, line = None, None
    if evidence:
        path, _, number = evidence.rpartition(":")
        path, line = (str(Path(path).resolve()), int(number)) if number.isdigit() else (evidence, None)
    fact = Relationship(kind, source, target, "declared", "", note, path, line) if target \
        else Entity(source, kind, note, path, line)
    conn = connect(store)
    try:
        with conn:
            if target:
                conn.execute("DELETE FROM relationships WHERE resolver = ? AND kind = ? AND source = ? AND target = ?",
                             (AGENT, kind, source, target))
            else:
                conn.execute("DELETE FROM entities WHERE resolver = ? AND kind = ? AND entity = ?", (AGENT, kind, source))
            write(conn, AGENT, [fact])
    finally:
        conn.close()
    return fact
