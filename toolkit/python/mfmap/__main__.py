# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Command line: ``python -m mfmap parse|serve|question|...``; ``--help`` lists every command."""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from pathlib import Path

from . import bms, mq, plan, questions, resolvers
from . import procedures as sp
from .crosscheck import PATTERNS, TextScan, crosscheck
from .model import Project, call_edges, commit_points, data_access
from .run import SOURCE_EXTENSIONS, find_sources
from .report import add_note, backlog, report, report_markdown
from .serve import serve
from .store import parse


def where(location, root: str) -> str:
    if location is None or location.path is None:
        return ""
    return f"{os.path.relpath(location.path, root)}:{location.line}"


def facts(project: Project, root: str, ddl=()) -> dict:
    """Programs, calls, data access, files, commit points and stored procedures as plain JSON,
    with file:line evidence. Stored procedures come from DDL files under ``root`` and ``ddl``."""
    programs, calls, access, files, commits = [], [], [], [], []
    defined = sp.procedures(sp.find_ddl(root, ddl))
    for p in project.programs.values():
        programs.append({
            "name": p.name,
            "file": os.path.relpath(p.file.path or "", root),
            "clean": p.file.clean,
            "paragraphs": len(p.paragraphs),
            "statements": len(p.statements),
            "copybooks": sorted(set(p.copybooks)),
        })
        for e in call_edges(p):
            call = {
                "from": p.name, "to": e.target, "via": e.via, "resolved": e.resolved,
                "expression": e.expression, "candidates": list(e.candidates),
                "paragraph": e.statement.paragraph.name if e.statement.paragraph else None,
                "evidence": where(e.statement.location, root),
            }
            if e.via == "SQL CALL":
                d = sp.match(e.target, defined)
                call["definition"] = f"{os.path.relpath(d.path, root)}:{d.line}" if d else None
                call["program"] = d.program if d else None
            calls.append(call)
        for a in data_access(p):
            access.append({
                "program": p.name, "paragraph": a.paragraph.name if a.paragraph else None,
                "store": a.store, "resource": a.resource, "mode": a.mode, "resolved": a.resolved,
                "expression": a.expression, "statement": a.statement.verb,
                "evidence": where(a.statement.location, root),
                **({"candidates": list(a.candidates)} if a.candidates else {}),
            })
        for c in commit_points(p):
            commits.append({
                "program": p.name, "paragraph": c.statement.paragraph.name if c.statement.paragraph else None,
                "kind": c.kind, "evidence": where(c.statement.location, root),
            })
        for f in p.files:
            files.append({
                "program": p.name, "name": f.name, "assign": f.assign,
                "organization": f.organization, "access": f.access_mode,
                "recordKey": f.record_key, "evidence": where(f.location, root),
            })
    called = {e["to"] for e in calls if e["via"] == "SQL CALL"}
    procedures = [{
        "name": d.name, "language": d.language, "program": d.program,
        "programInRepository": d.program in project.programs if d.program else None,
        "parameters": list(d.parameters), "resultSets": d.result_sets,
        "calledFromCobol": any(sp.match(c, [d]) for c in called if c),
        **({"reads": list(d.reads), "writes": list(d.writes), "calls": list(d.calls)} if d.native else {}),
        "evidence": f"{os.path.relpath(d.path, root)}:{d.line}",
    } for d in defined]
    return {"programs": programs, "calls": calls, "access": access, "files": files,
            "commits": commits, "procedures": procedures}


def graph(store: str, root: str) -> dict:
    """The resolvers' and the agent's entities and relationships from the store."""
    from .store import connect
    conn = connect(store)
    try:
        def evidence(r):
            return f"{os.path.relpath(r['path'], root)}:{r['line']}" if r["path"] else None
        entities = [{"entity": r["entity"], "kind": r["kind"], "note": r["note"], "resolver": r["resolver"],
                     "evidence": evidence(r)} for r in conn.execute("SELECT * FROM entities ORDER BY entity")]
        relationships = [{"kind": r["kind"], "from": r["source"], "to": r["target"], "resolved": r["resolved"],
                          "expression": r["expression"], "note": r["note"], "resolver": r["resolver"],
                          "evidence": evidence(r)}
                         for r in conn.execute("SELECT * FROM relationships ORDER BY source, kind, target")]
    finally:
        conn.close()
    return {"entities": entities, "relationships": relationships}


def summary(project: Project) -> str:
    files = project.files
    clean = [f for f in files if f.clean]
    crashed = [f for f in files if f.crash]
    counts = collections.Counter()
    for p in project.programs.values():
        counts["paragraphs"] += len(p.paragraphs)
        counts["data items"] += len(p.all_data_items)
        counts["CALL"] += len(p.calls)
        counts["PERFORM"] += len(p.performs)
        counts["EXEC CICS"] += len(p.cics)
        counts["EXEC SQL"] += len(p.sql)
        counts["SQL CALL"] += sum(s.statement_type == "CALL" for s in p.sql)
        counts["EXEC DLI"] += len(p.dli)
        counts["file I/O"] += len(p.file_io)
    codes = collections.Counter(
        f"{d.get('code', '?')}: {(d.get('message') or d.get('suggestion') or '')[:70]}"
        for f in files for d in f.errors)
    lines = [
        f"files: {len(files)}  clean: {len(clean)}  with errors: {len(files) - len(clean) - len(crashed)}"
        f"  crashed: {len(crashed)}",
        f"programs: {len(project.programs)}",
        "counts: " + ", ".join(f"{k} {v}" for k, v in counts.items()),
        "most common errors:",
        *(f"  {n:4d}  {c}" for c, n in codes.most_common(15)),
    ]
    for f in crashed:
        lines.append(f"crashed: {f.uri}: {f.crash}")
    return "\n".join(lines)


STORE = ".mfmap"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="mfmap")
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("parse", help="parse sources into the store")
    p.add_argument("sources", nargs="+", help="source files or folders")
    p.add_argument("--jar", default=os.environ.get("MFMAP_JAR"), help="server.jar (or $MFMAP_JAR)")
    p.add_argument("--store", default=STORE, help=f"store folder (default {STORE})")
    p.add_argument("-cf", "--copybooks", action="append", default=[], help="copybook folder")
    p.add_argument("-ce", "--copybook-extension", action="append", default=[], help="copybook extension")
    p.add_argument("-se", "--source-extension", action="append", default=[],
                   help="extension of programs in source folders (default .cbl and .cob); "
                        "pass '' for members with no extension. Files named directly are always parsed")
    p.add_argument("-j", "--jobs", type=int, default=4)
    p.add_argument("--force", action="store_true", help="parse unchanged files again")
    p.add_argument("--ddl", action="append", default=[],
                   help="DDL file or folder with CREATE PROCEDURE, TABLE, INDEX or VIEW statements, in addition to the "
                        ".sql, .ddl and .db2 files under the current folder")

    v = commands.add_parser("serve", help="serve the report page, refreshed as it changes")
    v.add_argument("--store", default=STORE, help=f"store folder (default {STORE})")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8765)
    v.add_argument("--plan", help="migration.json (default: in the parse root or next to the store)")

    r = commands.add_parser("report", help="print the Notes and Parser tabs as Markdown")
    r.add_argument("--store", default=STORE, help=f"store folder (default {STORE})")

    b = commands.add_parser("backlog", help="print every backlog unit in full as Markdown")
    b.add_argument("--store", default=STORE, help=f"store folder (default {STORE})")
    b.add_argument("--plan", help="migration.json (default: in the parse root or next to the store)")

    n = commands.add_parser("note", help="add a timestamped note to the report")
    n.add_argument("text", help="Markdown; file:line references link to the source")
    n.add_argument("--store", default=STORE, help=f"store folder (default {STORE})")

    q = commands.add_parser("question", help="add an open question for a person to the Notes tab")
    q.add_argument("text", help="the question; file:line references link to the source")
    q.add_argument("--found", help="what you found that leaves it open")
    q.add_argument("--default", help="the assumption you go ahead with until it is answered")
    q.add_argument("--affects", help="what the answer would change")
    q.add_argument("--store", default=STORE, help=f"store folder (default {STORE})")

    qs = commands.add_parser("questions", help="print the open questions and their answers")
    qs.add_argument("--store", default=STORE, help=f"store folder (default {STORE})")

    a = commands.add_parser("answer", help="record the answer to a question")
    a.add_argument("id", help="question ID, such as Q3")
    a.add_argument("text", help="the answer; an empty answer reopens the question")
    a.add_argument("--store", default=STORE, help=f"store folder (default {STORE})")

    rv = commands.add_parser("resolve", help="run the resolvers again (parse runs them too)")
    rv.add_argument("names", nargs="*", help="resolvers to run; default all")
    rv.add_argument("--store", default=STORE, help=f"store folder (default {STORE})")

    rc = commands.add_parser("record", help="record an entity or relationship you found yourself")
    rc.add_argument("kind", help="what it is, such as business-logic, exposes or reads")
    rc.add_argument("source", help="type:name, such as paragraph:ACCTUPD.2000-PROCESS")
    rc.add_argument("target", nargs="?", help="type:name; leave out to record a fact about the source")
    rc.add_argument("--note", help="a one-line summary")
    rc.add_argument("--evidence", help="file:line")
    rc.add_argument("--store", default=STORE, help=f"store folder (default {STORE})")

    ck = commands.add_parser("check", help="check migration.json against its schema and the map")
    ck.add_argument("--plan", help="migration.json (default: in the parse root or next to the store)")
    ck.add_argument("--store", default=STORE, help=f"store folder (default {STORE})")

    s = commands.add_parser("summary", help="parse rate, counts and common errors")
    s.add_argument("graphs", nargs="?", default=STORE, help="store or folder of graph files")

    f = commands.add_parser("facts", help="programs, calls, data access and files as JSON")
    f.add_argument("graphs", nargs="?", default=STORE, help="store or folder of graph files")
    f.add_argument("--root", default=".", help="make evidence paths relative to this folder")
    f.add_argument("--ddl", action="append", default=[], help="DDL file or folder (see parse)")

    c = commands.add_parser("crosscheck", help="compare statement counts with a text scan")
    c.add_argument("graphs", nargs="?", default=STORE, help="store or folder of graph files")
    c.add_argument("-cf", "--copybooks", action="append", default=[], help="copybook folder")
    c.add_argument("-ce", "--copybook-extension", action="append", default=[], help="copybook extension")

    m = commands.add_parser("fetch-mq-copybooks", help="download IBM MQ's COBOL copybooks")
    m.add_argument("--out", required=True, help="folder for the copybooks; pass it to parse with -cf")
    m.add_argument("--version", help="MQ redistributable client version; default: the newest")
    m.add_argument("--accept-license", action="store_true", help="accept IBM's MQ license terms")

    bm = commands.add_parser("bms-copybooks", help="write COBOL symbolic map copybooks from BMS source")
    bm.add_argument("sources", nargs="+", help=".bms files or folders")
    bm.add_argument("--out", required=True,
                    help="folder for the copybooks, outside the application source; pass it to parse with -cf")

    args = parser.parse_args(argv)
    if args.command == "bms-copybooks":
        written = bms.write(args.sources, args.out)
        print(f"wrote {len(written)} symbolic map copybooks to {args.out}; add -cf {args.out} when parsing")
        return 0
    if args.command == "fetch-mq-copybooks":
        if not args.accept_license:
            print("The MQ copybooks are IBM's and are licensed under the IBM MQ license terms "
                  "(https://www.ibm.com/terms). They come from IBM's free MQ redistributable "
                  "client and are saved with IBM's license files. Run again with "
                  "--accept-license to download them.", file=sys.stderr)
            return 2
        version, copybooks = mq.fetch(args.out, args.version)
        print(f"wrote {len(copybooks)} IBM MQ {version} copybooks to {args.out}; "
              f"add -cf {args.out} -ce cpy when parsing")
        return 0
    if args.command == "parse":
        if not args.jar:
            parser.error("--jar or $MFMAP_JAR is required")
        sources = find_sources(args.sources, args.source_extension or SOURCE_EXTENSIONS)
        statuses = collections.Counter()

        def progress(path: str, status: str) -> None:
            statuses[status] += 1
            print(f"[{sum(statuses.values())}/{len(sources)}] {status:7} {os.path.relpath(path)}", flush=True)

        run = parse(args.store, args.jar, sources, args.copybooks, args.copybook_extension,
                    args.jobs, args.force, progress, args.ddl)
        print(f"run {run}: " + ", ".join(f"{n} {s}" for s, n in sorted(statuses.items()))
              + f"; store {args.store}")
        return 1 if statuses["crash"] else 0
    if args.command == "serve":
        serve(args.store, args.host, args.port, args.plan)
        return 0
    if args.command == "report":
        print(report_markdown(report(args.store)))
        return 0
    if args.command == "check":
        from .store import connect
        store = Path(args.store).resolve()
        conn = connect(store) if (store / "map.db").is_file() else None
        try:
            last = conn.execute("SELECT root FROM runs ORDER BY id DESC LIMIT 1").fetchone() if conn else None
            path = plan.find(store, last["root"] if last else os.getcwd(), args.plan)
            if not path:
                parser.error("no migration.json in the parse root or next to the store; pass --plan")
            result = plan.check(path, conn)
        finally:
            if conn:
                conn.close()
        for e in result.errors:
            print(f"error: {e}")
        for w in result.warnings:
            print(f"warning: {w}")
        if not result.errors:
            units = len(result.plan["units"])
            print(f"{path.name}: {units} unit{'s' if units != 1 else ''}, no problems")
        return 1 if result.errors else 0
    if args.command == "resolve":
        try:
            counts = resolvers.run(args.store, args.names or None)
        except KeyError as e:
            parser.error(str(e.args[0]))
        for name, (entities, relationships) in counts.items():
            print(f"{name}: {entities} entities, {relationships} relationships")
        return 0
    if args.command == "record":
        resolvers.record(args.store, args.kind, args.source, args.target, args.note, args.evidence)
        print("recorded")
        return 0
    if args.command == "question":
        entry = questions.ask(args.store, args.text, args.found, args.default, args.affects)
        print(f"added {entry['id']}")
        return 0
    if args.command == "questions":
        print("\n".join(questions.markdown(questions.load(args.store))))
        return 0
    if args.command == "answer":
        try:
            entry = questions.answer(args.store, args.id, args.text, "agent")
        except KeyError as e:
            parser.error(str(e.args[0]))
        print(f"{entry['id']}: " + ("answered" if entry["answer"] else "reopened"))
        return 0
    if args.command == "backlog":
        print(backlog(args.store, args.plan))
        return 0
    if args.command == "note":
        print(f"added to {add_note(args.store, args.text)}")
        return 0
    project = Project.load(args.graphs)
    if args.command == "summary":
        print(summary(project))
    elif args.command == "crosscheck":
        extensions = args.copybook_extension or [".cpy"]
        scan = TextScan(args.copybooks, ["", *extensions])
        text, counted, differences = crosscheck(project, scan)
        print(f"{'':10} {'text':>6} {'graph':>6}")
        for key in PATTERNS:
            print(f"{key:10} {text[key]:6d} {counted[key]:6d}")
        for name, diff in differences.items():
            print(f"{name}: " + ", ".join(f"{k} text {t} graph {g}" for k, (t, g) in diff.items()))
        return 0 if not differences else 1
    else:
        out = facts(project, args.root, args.ddl)
        if (Path(args.graphs) / "map.db").is_file():
            out.update(graph(args.graphs, args.root))
        json.dump(out, sys.stdout, indent=1)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
