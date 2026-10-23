# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""The Map tab's graph: the store's entities and relationships, the units in ``migration.json`` and
the open questions, aggregated on the server so the page never draws the whole map at once.

There are three levels, each a small graph the page lays out and draws:

- ``estate``: the resolved graph itself, whether or not there is a plan: programs and their calls
  (CALL, LINK, XCTL), the ways in that start them (transactions, job steps, procedures, APIs, web
  pages, z/OS assets), the screens they send and receive, the data stores they read and write, and
  a dashed node per call whose target is set at run time. Each node carries the unit, wave and
  status ``migration.json`` gives it, if any, so the page can draw groups around the same nodes.
- ``unit``: the unit's ways in (transactions, jobs, APIs, queues, callers in other units), its
  programs, the screens they send and receive, the programs they call in other units, and every
  data store they read or write.
- ``program``: the program's paragraphs and the control flow between them (``enters``,
  ``performs``, ``falls-through``, ``goes-to``, ``handles``), the programs each paragraph
  ``invokes``, and the data each paragraph reads or writes. Business-logic paragraphs carry the
  summary recorded for them.

Every node and edge carries its evidence (file and line) and overlays: the unit's status, parse
errors, unresolved calls and the open questions that name what it stands for. ``version`` changes
whenever a parse, resolver run, ``migration.json`` or the questions change, so the page can poll
cheaply and redraw only when something changed.
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Iterable, Optional

from . import plan as plans
from . import questions as question_store
from .store import connect

LEVELS = ("estate", "unit", "program")
# Endpoint types that hold data, and the tag each gets on its card.
DATA_TYPES = {"vsam": "VSAM", "dataset": "DATASET", "db2": "DB2", "ims": "IMS", "database": "IMS DB",
              "file": "FILE", "mq": "MQ", "queue": "TS/TD QUEUE", "ims-message": "IMS MSG", "gsam": "GSAM"}
ACCESS = {"read": "read", "write": "write", "read-write": "read-write"}
ENTRY_KINDS = {"starts": "START", "runs": "RUN", "serves": "SERVE", "triggers": "TRIGGER"}
# What can start a program: a transaction, a job or procedure step, an API or an IMS transaction.
ENTRY_TYPES = ("transaction", "job", "proc", "api", "ims-transaction")
CALL_KINDS = {"calls": "CALL", "links": "LINK", "transfers": "XCTL", "loads": "LOAD",
              "calls-procedure": "SQL CALL"}
FLOW_KINDS = {"enters": "ENTER", "performs": "PERFORM", "falls-through": "FALLS THROUGH",
              "goes-to": "GO TO", "handles": "HANDLE", "invokes": "INVOKE"}
EVIDENCE_LIMIT = 40
GENERATION = re.compile(r"\((?:[+-]?\d+)\)$")
FILE_REF = re.compile(r"([\w./-]+\.(?:cbl|CBL|cob|COB|cpy|CPY|dcl|DCL|jcl|JCL|prc|PRC|proc|csd|CSD|dbd|DBD|"
                      r"psb|PSB|ctl|CTL|sql|ddl|ca7|controlm|bms|BMS|md|sh))((?::\d+(?:[-–]\d+)?)(?:,\s*:\d+(?:[-–]\d+)?)*)?")
WORD = re.compile(r"[A-Z0-9#@$][A-Z0-9#@$_.-]{3,}")


def version(store: str | os.PathLike, explicit: Optional[str] = None) -> str:
    """A tag that changes when anything the map draws changes: the store's database (parses,
    resolvers, ``mfmap record``), ``migration.json``, the unit notes and the questions."""
    store = Path(store).resolve()
    parts = []
    for path in [store / "map.db", store / "map.db-wal", store / question_store.QUESTIONS,
                 *_plan_paths(store, explicit)]:
        try:
            st = path.stat()
            parts.append(f"{path}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append(f"{path}:-")
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def _plan_paths(store: Path, explicit: Optional[str]) -> list[Path]:
    root = None
    db = store / "map.db"
    if db.is_file():
        conn = connect(store)
        try:
            run = conn.execute("SELECT root FROM runs ORDER BY id DESC LIMIT 1").fetchone()
            root = run["root"] if run else None
        finally:
            conn.close()
    path = plans.find(store, root, explicit)
    return [path, path.parent / "units"] if path else []


def graph(store: str | os.PathLike, explicit: Optional[str] = None, level: str = "estate",
          id: Optional[str] = None) -> dict:
    """The graph for one level. ``id`` is the unit ID for ``unit`` and the program name for
    ``program``. Raises KeyError when the level or ID is unknown."""
    if level not in LEVELS:
        raise KeyError(f"no level {level}; there are {', '.join(LEVELS)}")
    m = Map(Path(store).resolve(), explicit)
    out = {"estate": m.estate, "unit": m.unit, "program": m.program}[level](id)
    out["version"] = version(store, explicit)
    out["questions"] = [q for q in m.open_questions if q["id"] in {x for n in out["nodes"]
                                                                    for x in n["overlays"]["questions"]}]
    out["overlays"] = {"status": True, "errors": m.error_total, "unresolved": m.unresolved_total,
                       "questions": len(m.open_questions)}
    out["run"] = m.run
    out["root"] = m.root
    # What the search box can jump to.
    out["index"] = {"units": [[u["id"], u["name"]] for u in m.units.values()], "programs": sorted(m.programs)}
    return out


def _where(path: Optional[str], line: Optional[int], text: str = "") -> Optional[dict]:
    return {"path": path, "line": line, "text": text} if path else None


class Map:
    """Everything the levels share, read once per request."""

    def __init__(self, store: Path, explicit: Optional[str]):
        conn = connect(store)
        try:
            run = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
            self.run = {"id": run["id"], "status": run["status"]} if run else None
            self.root = run["root"] if run else str(store.parent)
            self.rels = [dict(r) for r in conn.execute("SELECT * FROM relationships")]
            self.entities = [dict(r) for r in conn.execute("SELECT * FROM entities")]
            self.programs = {r["name"]: dict(r) for r in conn.execute("SELECT * FROM programs")}
            self.files = {r["path"]: dict(r) for r in conn.execute(
                "SELECT path, status, errors, warnings, message FROM files")}
            self.diagnostics = collections.defaultdict(list)
            for r in conn.execute("SELECT * FROM diagnostics WHERE severity = 'ERROR'"):
                self.diagnostics[r["file"]].append(dict(r))
            self.access_rows = [dict(r) for r in conn.execute("SELECT * FROM access")]
            path = plans.find(store, self.root, explicit)
            self.plan_path = path
            self.plan = plans.check(path, conn).plan if path else None
        finally:
            conn.close()
        self.plan = self.plan or {"units": [], "excluded": []}
        self.units = {u["id"]: u for u in self.plan.get("units", [])}
        self.owner, self.partial = {}, collections.defaultdict(dict)  # program -> unit; program -> {paragraph: unit}
        for u in self.units.values():
            for p in u["programs"]:
                kind, _, name = p.partition(":")
                if kind == "program":
                    self.owner.setdefault(name, u["id"])
                elif kind == "paragraph":
                    prog, _, para = name.partition(".")
                    self.partial[prog][para] = u["id"]
                    self.owner.setdefault(prog, u["id"])
        self.excluded = {e["program"].partition(":")[2]: e.get("reason", "") for e in self.plan.get("excluded", [])}
        self.business = {e["entity"]: e for e in self.entities if e["kind"] == "business-logic"}
        self.out = collections.defaultdict(list)
        self.into = collections.defaultdict(list)
        for r in self.rels:
            self.out[r["source"]].append(r)
            if r["target"]:
                self.into[r["target"]].append(r)
        self._canon = self._data_identity()
        datasets = [e.partition(":")[2].split(".") for e in set(self._canon.values()) if e.startswith("dataset:")]
        self.dataset_prefix = 0
        while datasets and all(len(d) > self.dataset_prefix + 1 and d[self.dataset_prefix] == datasets[0][self.dataset_prefix]
                               for d in datasets):
            self.dataset_prefix += 1
        self._canon_values = set(self._canon.values())
        # A batch program's file (its ASSIGN name, file:DD) is the dataset the DD statement names in
        # the steps that run it; the jcl resolver records that as program -> dataset "DD name in ...".
        self.dd = collections.defaultdict(set)
        for r in self.rels:
            m = re.match(r"DD (\S+) in ", r["note"] or "")
            if m and r["kind"] in ACCESS and r["source"].startswith("program:") and self.data(r["target"]):
                self.dd[(r["source"], m.group(1))].add(self.data(r["target"]))
        self.users = collections.defaultdict(set)  # data -> units that read or write it
        for ep in [f"program:{p}" for p in self.owner]:
            for d, _ in self.accesses(ep):
                self.users[d].add(self.owner[ep.partition(":")[2]])
        self.error_total = sum(len(v) for v in self.diagnostics.values())
        self.unresolved_total = sum(1 for r in self.rels if not r["target"])
        self.open_questions = [q for q in question_store.load(store) if not q.get("answer")]
        self.question_links = self._link_questions()

    # --- identities -------------------------------------------------------------------------

    def _data_identity(self) -> dict:
        """Endpoint -> canonical data node ID. A CICS file and the dataset it is stored in are one
        store, as are GDG generations of one dataset."""
        parent = {}

        def find(x):
            while parent.get(x, x) != x:
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                # The dataset is the canonical name; a CICS file name is an alias.
                if ra.startswith("dataset:"):
                    parent[rb] = ra
                else:
                    parent[ra] = rb

        for r in self.rels:
            if r["kind"] == "stored-in" and r["target"] and r["source"].split(":")[0] in ("vsam", "database"):
                union(r["source"], self._generation(r["target"]))
        canon = {}
        for endpoint in self._all_endpoints():
            if endpoint.split(":")[0] in DATA_TYPES:
                canon[endpoint] = find(self._generation(endpoint))
        return canon

    @staticmethod
    def _generation(endpoint: str) -> str:
        return GENERATION.sub("", endpoint)

    def _all_endpoints(self) -> Iterable[str]:
        seen = set()
        for r in self.rels:
            for e in (r["source"], r["target"]):
                if e and e not in seen:
                    seen.add(e)
                    yield e
        for e in self.entities:
            if e["entity"] not in seen:
                seen.add(e["entity"])
                yield e["entity"]

    def data(self, endpoint: Optional[str]) -> Optional[str]:
        return self._canon.get(endpoint) if endpoint else None

    def stores_of(self, program: str, endpoint: Optional[str]) -> list[str]:
        """The data nodes an access by ``program`` (an endpoint) to ``endpoint`` reaches."""
        if endpoint and endpoint.startswith("file:"):
            matched = self.dd.get((program, endpoint.partition(":")[2]))
            if matched:
                return sorted(matched)
        d = self.data(endpoint)
        return [d] if d else []

    def accesses(self, ep: str) -> list[tuple[str, dict]]:
        """(data node, relationship) for each read and write by a program or paragraph."""
        program = ep if ep.startswith("program:") else "program:" + ep.partition(":")[2].partition(".")[0]
        return [(d, r) for r in self.out[ep] if r["kind"] in ACCESS for d in self.stores_of(program, r["target"])]

    def aliases(self, canonical: str) -> list[str]:
        return sorted(e for e, c in self._canon.items() if c == canonical)

    def data_label(self, canonical: str) -> tuple[str, str, str]:
        """Label, subtitle and type tag of a data node."""
        names = self.aliases(canonical)
        vsam = [n for n in names if n.startswith("vsam:")]
        kind, _, name = canonical.partition(":")
        if vsam:
            return vsam[0].partition(":")[2], name if kind == "dataset" else "", "VSAM"
        if kind == "db2":
            return name.split(".")[-1], name, "DB2"
        if kind == "dataset":
            # The type is the store's (a dataset); the label drops the qualifiers every dataset shares.
            return ".".join(name.split(".")[self.dataset_prefix:]) or name, name, "DATASET"
        return name, "", DATA_TYPES.get(kind, kind.upper())

    def unit_of(self, endpoint: str) -> Optional[str]:
        kind, _, name = endpoint.partition(":")
        if kind == "program":
            return self.owner.get(name)
        if kind == "paragraph":
            prog, _, para = name.partition(".")
            return self.partial.get(prog, {}).get(para) or self.owner.get(prog)
        if kind == "unit":
            return name
        return None

    def unit_programs(self, uid: str) -> list[str]:
        return sorted(p for p, u in self.owner.items() if u == uid) + \
            sorted(p for p, paras in self.partial.items() if uid in paras.values() and self.owner.get(p) != uid)

    def program_file(self, name: str) -> Optional[str]:
        p = self.programs.get(name)
        return p["file"] if p else None

    # --- questions --------------------------------------------------------------------------

    def _paragraph_ranges(self) -> dict:
        """file -> sorted [(line, paragraph endpoint)] from each program's ``contains``."""
        ranges = collections.defaultdict(list)
        for r in self.rels:
            if r["kind"] == "contains" and r["source"].startswith("program:") and r["target"] \
                    and r["target"].startswith("paragraph:") and r["path"] and r["line"]:
                ranges[r["path"]].append((r["line"], r["target"]))
        return {k: sorted(v) for k, v in ranges.items()}

    def paragraph_at(self, path: str, line: int) -> Optional[str]:
        found = None
        for start, para in self.ranges.get(path, []):
            if start <= line:
                found = para
            else:
                break
        return found

    def _link_questions(self) -> dict:
        """Endpoint -> open question IDs that name it: by file:line (the program and paragraph that
        line is in), by ``units/<id>.md``, and by the name of a program, transaction, job, screen,
        table or file."""
        self.ranges = self._paragraph_ranges()
        known_paths = set(self.files) | {r["path"] for r in self.rels if r["path"]} | \
            {e["path"] for e in self.entities if e["path"]}
        by_file = collections.defaultdict(set)
        for name, p in self.programs.items():
            by_file[p["file"]].add(f"program:{name}")
        for e in self.entities:
            if e["kind"] == "defined" and e["path"]:
                by_file[e["path"]].add(e["entity"])
        names = collections.defaultdict(set)
        for endpoint in self._all_endpoints():
            kind, _, name = endpoint.partition(":")
            if kind in ("program", "transaction", "job", "proc", "api") or kind in DATA_TYPES:
                for word in {name, name.split(".")[-1]}:
                    if len(word) >= 4 and word.isupper():
                        names[word].add(self.data(endpoint) or endpoint)
            elif kind == "screen":
                for word in name.split("."):
                    if len(word) >= 4:
                        names[word].add(endpoint)
        links = collections.defaultdict(set)
        for q in self.open_questions:
            text = " ".join(str(q.get(k) or "") for k in ("question", "found", "default", "affects"))
            for m in FILE_REF.finditer(text):
                rel = m.group(1)
                unit = re.fullmatch(r"(?:.*/)?units/([\w-]+)\.md", rel)
                if unit and unit.group(1) in self.units:
                    links[f"unit:{unit.group(1)}"].add(q["id"])
                    continue
                paths = [p for p in known_paths if p == rel or p.endswith("/" + rel)]
                lines = [int(x) for x in re.findall(r":(\d+)", m.group(2) or "")]
                for path in paths:
                    for endpoint in by_file.get(path, ()):
                        links[endpoint].add(q["id"])
                    for line in lines:
                        para = self.paragraph_at(path, line)
                        if para:
                            links[para].add(q["id"])
            for word in WORD.findall(text):
                for endpoint in names.get(word.rstrip(".,;:)"), ()):
                    links[endpoint].add(q["id"])
        return links

    def questions_for(self, endpoints: Iterable[str]) -> list[str]:
        found = set()
        for e in endpoints:
            found |= self.question_links.get(e, set())
        return sorted(found, key=lambda q: int(q[1:]) if q[1:].isdigit() else 0)

    # --- overlays ---------------------------------------------------------------------------

    def errors_for(self, programs: Iterable[str]) -> list[dict]:
        out = []
        for p in programs:
            f = self.program_file(p)
            out += self.diagnostics.get(f, []) if f else []
        return out

    def unresolved_for(self, endpoints: Iterable[str]) -> list[dict]:
        wanted = set(endpoints)
        prefixes = tuple(f"paragraph:{e.partition(':')[2]}." for e in wanted if e.startswith("program:"))
        found = {}
        for r in self.rels:
            if not r["target"] and (r["source"] in wanted or (prefixes and r["source"].startswith(prefixes))):
                # A program's unresolved XCTL is also its paragraph's unresolved invokes: count it once.
                found.setdefault((r["path"], r["line"], r["expression"]), r)
        return list(found.values())

    def overlays(self, endpoints: list[str], programs: list[str] = (), status: Optional[str] = None) -> dict:
        errors = self.errors_for(programs)
        unresolved = self.unresolved_for(endpoints)
        return {"status": status, "errors": len(errors), "unresolved": len(unresolved),
                "questions": self.questions_for(endpoints),
                "errorEvidence": [_where(d["path"], d["line"], d["message"]) for d in errors[:EVIDENCE_LIMIT]],
                "unresolvedEvidence": [_where(r["path"], r["line"], f"{r['kind']} {r['expression'] or ''}"
                                              f"{' (' + r['note'] + ')' if r['note'] else ''}".strip())
                                       for r in unresolved[:EVIDENCE_LIMIT]]}

    # --- building blocks --------------------------------------------------------------------

    def program_tags(self, name: str) -> list[dict]:
        ep = f"program:{name}"
        kinds = {r["kind"] for r in self.into[ep]} | {r["kind"] for r in self.out[ep]}
        sources = {r["source"].split(":")[0] for r in self.into[ep] if r["kind"] in ENTRY_KINDS}
        tags = []
        if "transaction" in sources or {"sends", "receives"} & kinds:
            tags.append(("ONLINE", "online"))
        if "job" in sources or "proc" in sources:
            tags.append(("BATCH", "batch"))
        if "api" in sources:
            tags.append(("SERVICE", "service"))
        stores = {d.split(":")[0] for d, _ in self.accesses(ep)}
        stores |= {a["store"] for a in self.access_rows if a["program"] == name}
        for store, label in (("vsam", "VSAM"), ("dataset", "FILES"), ("file", "FILES"), ("db2", "DB2"),
                             ("ims", "IMS"), ("mq", "MQ"), ("queue", "TS/TD")):
            if store in stores and (label, label.lower()) not in tags:
                tags.append((label, label.lower().replace("/", "")))
        return [{"text": t, "tone": tone} for t, tone in tags]

    def program_node(self, name: str, band: str, external: bool = False) -> dict:
        p = self.programs.get(name)
        ep = f"program:{name}"
        paragraphs = [r["target"] for r in self.out[ep] if r["kind"] == "contains"]
        logic = [x for x in paragraphs if x in self.business]
        unit = self.unit_of(ep)
        counts = []
        if p:
            counts = [{"n": p["paragraphs"], "label": "paras"}, {"n": p["statements"], "label": "stmts"}]
            if logic:
                counts.append({"n": len(logic), "label": "logic"})
        defined = next((r for r in self.into[ep] if r["kind"] in ENTRY_KINDS), None)
        evidence = [_where(p["file"], 1, "source")] if p else []
        if defined:
            evidence.append(_where(defined["path"], defined["line"], f"{defined['source']} {defined['kind']} it"))
        sub = []
        for r in self.into[ep]:
            if r["kind"] in ENTRY_KINDS and r["source"].split(":")[0] in ("transaction", "job"):
                sub.append(r["source"].replace(":", " "))
        note = None
        if external:
            note = f"in unit {unit}" if unit else ("not migrated: " + self.excluded[name]) if name in self.excluded \
                else "not in any unit"
        elif name in self.excluded:
            note = "not migrated: " + self.excluded[name]
        return {"id": ep, "kind": "external" if external else "program", "label": name,
                "sub": " · ".join(sorted(set(sub))[:3]), "band": band, "tags": self.program_tags(name),
                "counts": counts, "note": note, "file": self._rel(p["file"]) if p else None,
                "evidence": [e for e in evidence if e], "drill": {"level": "program", "id": name} if p else None,
                "unit": unit,
                "overlays": self.overlays([ep, *paragraphs], [name], self.units[unit].get("status", "todo")
                                          if unit and not external else None)}

    def data_node(self, canonical: str, band: str, units: Iterable[str] = ()) -> dict:
        label, sub, tag = self.data_label(canonical)
        aliases = self.aliases(canonical)
        evidence = []
        for a in aliases:
            for r in self.out[a] + self.into[a]:
                if r["kind"] in ("stored-in", "defined", "contains", "indexes") and r["path"]:
                    evidence.append(_where(r["path"], r["line"], f"{r['source']} {r['kind']} {r['target'] or ''}"))
            for e in self.entities:
                if e["entity"] == a and e["path"]:
                    evidence.append(_where(e["path"], e["line"], f"{e['kind']} {e['note'] or ''}".strip()))
        units = sorted(set(units))
        tags = [{"text": tag, "tone": tag.lower().split()[0].replace("/", "")}]
        if len(units) > 1:
            tags.append({"text": "SHARED", "tone": "shared"})
        return {"id": canonical, "kind": "data", "label": label, "sub": sub, "band": band, "tags": tags,
                "counts": [], "note": ("used by " + ", ".join(units)) if units else None,
                "aliases": aliases, "evidence": evidence[:EVIDENCE_LIMIT], "drill": None, "unit": None,
                "overlays": self.overlays(aliases)}

    def entry_node(self, endpoint: str, band: str) -> dict:
        kind, _, name = endpoint.partition(":")
        evidence = []
        for e in self.entities:
            if e["entity"] == endpoint and e["path"]:
                evidence.append(_where(e["path"], e["line"], e["kind"]))
        for r in self.out[endpoint]:
            if r["path"]:
                evidence.append(_where(r["path"], r["line"], f"{r['kind']} {r['target'] or ''}"))
        schedules = [r["source"].partition(":")[2] for r in self.into[endpoint] if r["kind"] == "schedules"]
        sub = {"transaction": "CICS transaction", "job": "batch job", "proc": "JCL procedure",
               "api": "MQ service", "screen": "BMS map", "queue": "queue", "mq": "MQ queue"}.get(kind, kind)
        if schedules:
            sub += " · " + schedules[0]
        return {"id": endpoint, "kind": "screen" if kind == "screen" else "entry", "label": name, "sub": sub,
                "band": band, "tags": [{"text": kind.upper(), "tone": kind}], "counts": [], "note": None,
                "evidence": evidence[:EVIDENCE_LIMIT], "drill": None, "unit": None,
                "overlays": self.overlays([endpoint])}

    def _rel(self, path: Optional[str]) -> Optional[str]:
        return os.path.relpath(path, self.root) if path else None

    @staticmethod
    def edge(source: str, target: str, kind: str, label: str, tone: str, rels: list[dict],
             dashed: bool = False) -> dict:
        unique = {}
        for r in rels:  # the same statement can be recorded by two resolvers, or by a program and its paragraph
            unique.setdefault((r.get("path"), r.get("line"), r["kind"], r.get("target")), r)
        rels = list(unique.values())
        evidence = [_where(r.get("path"), r.get("line"), r.get("text") or
                           f"{r['source']} {r['kind']} {r.get('target') or ''}{' — ' + r['note'] if r.get('note') else ''}")
                    for r in rels]
        return {"id": f"{source}->{target}#{kind}", "source": source, "target": target, "kind": kind,
                "label": label, "tone": tone, "count": len(rels), "dashed": dashed,
                "evidence": [e for e in evidence if e][:EVIDENCE_LIMIT]}

    @staticmethod
    def access_label(modes: set) -> tuple[str, str]:
        if "read-write" in modes or {"read", "write"} <= modes:
            return "READ/WRITE", "rw"
        return ("WRITE", "write") if "write" in modes else ("READ", "read")

    # --- levels -----------------------------------------------------------------------------

    def estate(self, _id: Optional[str] = None) -> dict:
        """The resolved graph itself: programs and their calls, the ways in that start them, the
        screens they show and the data they read and write. Calls whose target is set at run time
        are dashed edges to a node of their own, labeled with the expression. Nothing here comes
        from ``migration.json``; each node only carries the unit, wave and status the plan gives it
        (when there is a plan), for the page to group by."""
        nodes, edges = {}, []
        parsed = set(self.programs)

        def program(endpoint: str) -> str:
            if endpoint not in nodes:
                name = endpoint.partition(":")[2]
                node = self.program_node(name, "", external=name not in parsed)
                if name not in parsed and name not in self.excluded:
                    node["note"] = "no source in the repository"
                nodes[endpoint] = node
            return endpoint

        def entry(endpoint: str) -> str:
            if endpoint not in nodes:
                nodes[endpoint] = self.entry_node(endpoint, "")
            return endpoint

        def link(source, target, kind, label, tone, rels, dashed=False):
            edges.append(self.edge(source, target, kind, label, tone, rels, dashed=dashed))

        for name in sorted(parsed):
            program(f"program:{name}")
        grouped = collections.defaultdict(list)
        for r in self.rels:
            src, dst, kind = r["source"], r["target"], r["kind"]
            stype, dtype = src.partition(":")[0], (dst or "").partition(":")[0]
            if kind in ENTRY_KINDS and stype in ENTRY_TYPES and dtype in ("program", "proc"):
                grouped[(src, dst, kind)].append(r)
            elif kind == "calls" and stype in ("page", "api") and dtype == "api":
                grouped[(src, dst, "calls-api")].append(r)
            elif kind == "links" and stype == "zosasset" and dtype == "program":
                grouped[(src, dst, kind)].append(r)
            elif stype == "program" and kind in CALL_KINDS and kind != "calls-procedure":
                if dst:
                    grouped[(src, dst, kind)].append(r)
                else:
                    expression = r["expression"] or "?"
                    grouped[(src, f"dynamic:{src.partition(':')[2]}:{expression}", kind)].append(r)
            elif stype == "program" and kind in ("sends", "receives") and dtype == "screen":
                grouped[(src, dst, "screen")].append(r)
            elif stype == "program" and kind == "submits" and dtype == "job":
                grouped[(src, dst, kind)].append(r)
        for (src, dst, kind), rels in sorted(grouped.items()):
            if kind in ENTRY_KINDS or kind in ("calls-api", "links") and src.startswith("zosasset:"):
                entry(src)
                program(dst) if dst.startswith("program:") else entry(dst)
                label = ENTRY_KINDS.get(kind, "LINK")
                link(src, dst, kind, label, "control", rels)
            elif kind == "calls-api":
                entry(src), entry(dst)
                link(src, dst, "call", "CALL", "control", rels)
            elif kind == "screen":
                entry(dst)
                modes = {r["kind"] for r in rels}
                link(src, dst, "screen", "SEND/RECEIVE" if len(modes) == 2 else modes.pop().upper().rstrip("S"),
                     "screen", rels)
            elif kind == "submits":
                entry(dst)
                link(src, dst, "submit", "SUBMIT", "control", rels)
            elif dst.startswith("dynamic:"):
                expression = dst.split(":", 2)[2]
                if dst not in nodes:
                    owner = self.owner.get(src.partition(":")[2])
                    nodes[dst] = {"id": dst, "kind": "dynamic", "label": expression, "sub": "set at run time",
                                  "band": "", "tags": [], "counts": [], "note": rels[0]["note"],
                                  "evidence": [], "drill": None, "unit": owner,
                                  "overlays": self.overlays([], [], None)}
                link(src, dst, "dynamic", f"{CALL_KINDS[kind]} {expression}", "control", rels, dashed=True)
            else:
                program(dst)
                link(src, dst, "call", CALL_KINDS[kind], "control", rels, dashed=kind == "transfers")
        # Reads and writes, with a CICS file and its dataset as one store.
        access = collections.defaultdict(list)
        for name in parsed:
            for d, r in self.accesses(f"program:{name}"):
                access[(f"program:{name}", d)].append(r)
        for (src, d), rels in sorted(access.items()):
            if d not in nodes:
                nodes[d] = self.data_node(d, "", self.users[d])
            label, tone = self.access_label({r["kind"] for r in rels})
            link(src, d, "access", label, tone, rels)
        for n in nodes.values():
            n["groups"] = self.groups_of(n)
        entries = sum(1 for n in nodes.values() if n["kind"] in ("entry", "screen"))
        dynamic = sum(1 for n in nodes.values() if n["kind"] == "dynamic")
        data = sum(1 for n in nodes.values() if n["kind"] == "data")
        return {"level": "estate", "id": None, "title": "Estate",
                "subtitle": f"{len(parsed)} programs, {entries} ways in and screens, {data} data stores, "
                            f"{dynamic} calls set at run time; double-click a program for its paragraphs",
                "crumbs": [{"level": "estate", "id": None, "label": "Estate"}],
                "bands": [], "nodes": list(nodes.values()), "edges": edges, "layout": "graph",
                "groupings": ["none", "unit", "wave", "status"] if self.units else ["none"],
                "groupLabels": {"unit": {u["id"]: u["name"] for u in self.units.values()}},
                "totals": self.totals()}

    def groups_of(self, node: dict) -> dict:
        """The unit, wave and status ``migration.json`` gives a node, for the page to group by: a
        program's unit, a way in that exactly one unit lists, and a run-time call its program's unit.
        Data stores are in no unit; the plan does not say who owns them."""
        uid = None
        kind, _, name = node["id"].partition(":")
        if kind == "program":
            uid = self.owner.get(name)
        elif kind == "dynamic":
            uid = node.get("unit")
        elif node["kind"] in ("entry", "screen"):
            listed = [u["id"] for u in self.units.values() if node["id"] in u.get("entryPoints", [])]
            uid = listed[0] if len(listed) == 1 else None
        if not uid:
            return {}
        u = self.units[uid]
        return {"unit": uid, "wave": f"Wave {u['wave']}", "status": u.get("status", "todo")}

    def totals(self) -> dict:
        endpoints = set(self._all_endpoints())
        return {"entities": len(endpoints), "relationships": len(self.rels)}

    def unit(self, uid: Optional[str]) -> dict:
        if uid not in self.units:
            raise KeyError(f"no unit {uid}")
        u = self.units[uid]
        programs = self.unit_programs(uid)
        mine = {f"program:{p}" for p in programs}
        nodes, edges = {}, []
        for p in programs:
            nodes[f"program:{p}"] = self.program_node(p, "programs")
        # Ways in: what starts, runs or serves the programs, and the plan's entry points.
        entry_rels = collections.defaultdict(list)
        for ep in mine:
            for r in self.into[ep]:
                if r["kind"] in ENTRY_KINDS:
                    entry_rels[(r["source"], ep, r["kind"])].append(r)
        for e in u.get("entryPoints", []):
            if e not in nodes and e.split(":")[0] not in DATA_TYPES:
                nodes.setdefault(e, self.entry_node(e, "entries"))
        for (src, ep, kind), rels in entry_rels.items():
            if src not in nodes:
                nodes[src] = self.entry_node(src, "entries")
            edges.append(self.edge(src, ep, kind, ENTRY_KINDS[kind], "control", rels))
        # Screens.
        screens = collections.defaultdict(list)
        for ep in mine:
            for r in self.out[ep]:
                if r["kind"] in ("sends", "receives") and r["target"]:
                    screens[(ep, r["target"])].append(r)
        for (ep, screen), rels in screens.items():
            nodes.setdefault(screen, self.entry_node(screen, "entries"))
            kinds = {r["kind"] for r in rels}
            label = "SEND/RECEIVE" if len(kinds) == 2 else kinds.pop().upper().rstrip("S")
            edges.append(self.edge(ep, screen, "screen", label, "screen", rels))
        # Calls between programs, in and out of the unit.
        calls = collections.defaultdict(list)
        for ep in mine:
            for r in self.out[ep]:
                if r["kind"] in CALL_KINDS and r["target"]:
                    calls[(ep, r["target"], r["kind"])].append(r)
            for r in self.into[ep]:
                if r["kind"] in CALL_KINDS and r["source"] not in mine:
                    calls[(r["source"], ep, r["kind"])].append(r)
        for (a, b, kind), rels in calls.items():
            for end, band in ((a, "callers"), (b, "callees")):
                if end not in nodes:
                    name = end.partition(":")[2]
                    nodes[end] = self.program_node(name, band, external=True) if end.startswith("program:") \
                        else self.entry_node(end, band)
            edges.append(self.edge(a, b, "call", CALL_KINDS[kind], "control", rels, dashed=kind == "transfers"))
        # Data.
        access = collections.defaultdict(list)
        for ep in mine:
            for d, r in self.accesses(ep):
                access[(ep, d)].append(r)
        for (ep, d), rels in access.items():
            nodes.setdefault(d, self.data_node(d, "data", self.users[d]))
            label, tone = self.access_label({r["kind"] for r in rels})
            edges.append(self.edge(ep, d, "access", label, tone, rels))
        # Called programs after the data: a unit has more reads and writes than calls out.
        bands = [{"id": "entries", "label": "Ways in"}, {"id": "callers", "label": "Callers"},
                 {"id": "programs", "label": "Programs"}, {"id": "data", "label": "Data"},
                 {"id": "callees", "label": "Called"}]
        used = {n["band"] for n in nodes.values()}
        return {"level": "unit", "id": uid, "title": u["name"],
                "subtitle": f"unit {uid}, wave {u['wave']}, {u.get('status', 'todo')}: {len(programs)} programs; "
                            "double-click a program for its paragraphs",
                "crumbs": [{"level": "estate", "id": None, "label": "Estate"},
                           {"level": "unit", "id": uid, "label": u["name"]}],
                "bands": [b for b in bands if b["id"] in used], "nodes": list(nodes.values()), "edges": edges,
                "layout": "columns", "totals": self.totals()}

    def program(self, name: Optional[str]) -> dict:
        if name not in self.programs:
            raise KeyError(f"no program {name}")
        ep = f"program:{name}"
        p = self.programs[name]
        uid = self.owner.get(name)
        nodes, edges = {}, []
        start = self.program_node(name, "program")
        start["kind"] = "program"
        start["drill"] = None
        nodes[ep] = start
        for r in self.out[ep]:
            if r["kind"] == "contains" and r["target"]:
                nodes[r["target"]] = self.paragraph_node(r["target"], r)
        flow = collections.defaultdict(list)
        for src in [ep, *nodes]:
            for r in self.out[src]:
                if r["kind"] in FLOW_KINDS and (r["kind"] != "enters" or src == ep):
                    target = r["target"]
                    if target is None:
                        continue
                    if target not in nodes:
                        if target.startswith("program:"):
                            nodes[target] = self.program_node(target.partition(":")[2], "callees", external=True)
                        elif target.startswith("paragraph:"):
                            nodes[target] = self.paragraph_node(target, None)
                        else:
                            nodes[target] = self.entry_node(target, "callees")
                    flow[(src, target, r["kind"])].append(r)
        for (a, b, kind), rels in flow.items():
            label = FLOW_KINDS[kind]
            if kind == "invokes":
                label = (rels[0]["note"] or "CALL").split(",")[0].upper()
                label = label if label in ("CALL", "LINK", "XCTL", "LOAD", "SQL CALL") else "CALL"
            thru = {r["note"] for r in rels if kind == "performs" and r["note"]}
            if thru:
                label += " " + sorted(thru)[0].upper()
            edges.append(self.edge(a, b, kind, label, "flow" if kind in ("falls-through",) else "control", rels,
                                   dashed=kind in ("falls-through", "handles")))
        # Data each paragraph reads or writes, from the parse.
        access = collections.defaultdict(list)
        for a in self.access_rows:
            if a["program"] != name or not a["resource"]:
                continue
            endpoint = f"{a['store']}:{a['resource']}"
            for d in self.stores_of(ep, endpoint) or [endpoint]:
                src = f"paragraph:{name}.{a['paragraph']}" if a["paragraph"] else ep
                if src not in nodes:
                    src = ep
                access[(src, d)].append({"source": src, "kind": a["mode"], "target": endpoint, "path": a["path"],
                                         "line": a["line"], "note": a["verb"]})
        for (src, d), rels in access.items():
            if d not in nodes:
                nodes[d] = self.data_node(d, "data", self.users[d]) if d in self._canon_values \
                    else self.entry_node(d, "data")
            label, tone = self.access_label({r["kind"] for r in rels})
            edges.append(self.edge(src, d, "access", label, tone, rels))
        crumbs = [{"level": "estate", "id": None, "label": "Estate"}]
        if uid:
            crumbs.append({"level": "unit", "id": uid, "label": self.units[uid]["name"]})
        crumbs.append({"level": "program", "id": name, "label": name})
        paragraphs = sum(1 for n in nodes.values() if n["kind"] == "paragraph")
        logic = sum(1 for n in nodes.values() if n["kind"] == "paragraph" and n["highlight"])
        return {"level": "program", "id": name, "title": name,
                "subtitle": f"{self._rel(p['file'])}: {paragraphs} paragraphs, {logic} with business logic"
                            + (f"; unit {uid}" if uid else ""),
                "crumbs": crumbs, "bands": [], "nodes": list(nodes.values()), "edges": edges, "layout": "flow",
                "totals": self.totals()}

    def paragraph_node(self, endpoint: str, contains: Optional[dict]) -> dict:
        prog, _, para = endpoint.partition(":")[2].partition(".")
        logic = self.business.get(endpoint)
        evidence = [_where(contains["path"], contains["line"], "paragraph")] if contains else []
        if logic:
            evidence.append(_where(logic["path"], logic["line"], "business logic: " + (logic["note"] or "")))
        unit = self.partial.get(prog, {}).get(para)
        tags = [{"text": "BUSINESS LOGIC", "tone": "logic"}] if logic else []
        if unit and unit != self.owner.get(prog):
            tags.append({"text": f"UNIT {unit}", "tone": "unit"})
        outs = collections.Counter(r["kind"] for r in self.out[endpoint])
        counts = [{"n": n, "label": FLOW_KINDS.get(k, k).lower()} for k, n in outs.items() if k in FLOW_KINDS]
        return {"id": endpoint, "kind": "paragraph", "label": para, "sub": prog, "band": "flow", "tags": tags,
                "counts": counts[:3], "note": logic["note"] if logic else None, "highlight": bool(logic),
                "evidence": [e for e in evidence if e], "drill": None, "unit": unit or self.owner.get(prog),
                "overlays": self.overlays([endpoint])}
