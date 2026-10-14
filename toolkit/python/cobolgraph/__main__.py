# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Command line: ``python -m cobolgraph parse|summary|facts``."""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

from . import mq
from .crosscheck import PATTERNS, TextScan, crosscheck
from .model import Project, call_edges, data_access
from .run import find_sources
from .serve import serve
from .store import parse


def where(location, root: str) -> str:
    if location is None or location.path is None:
        return ""
    return f"{os.path.relpath(location.path, root)}:{location.line}"


def facts(project: Project, root: str) -> dict:
    """Programs, calls, data access and files as plain JSON, with file:line evidence."""
    programs, calls, access, files = [], [], [], []
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
            calls.append({
                "from": p.name, "to": e.target, "via": e.via, "resolved": e.resolved,
                "expression": e.expression, "candidates": list(e.candidates),
                "paragraph": e.statement.paragraph.name if e.statement.paragraph else None,
                "evidence": where(e.statement.location, root),
            })
        for a in data_access(p):
            access.append({
                "program": p.name, "paragraph": a.paragraph.name if a.paragraph else None,
                "store": a.store, "resource": a.resource, "mode": a.mode, "resolved": a.resolved,
                "expression": a.expression, "statement": a.statement.verb,
                "evidence": where(a.statement.location, root),
            })
        for f in p.files:
            files.append({
                "program": p.name, "name": f.name, "assign": f.assign,
                "organization": f.organization, "access": f.access_mode,
                "recordKey": f.record_key, "evidence": where(f.location, root),
            })
    return {"programs": programs, "calls": calls, "access": access, "files": files}


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


STORE = ".cobolgraph"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="cobolgraph")
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("parse", help="parse sources into the store")
    p.add_argument("sources", nargs="+", help="source files or folders")
    p.add_argument("--jar", default=os.environ.get("PARSEBOL_JAR"), help="server.jar (or $PARSEBOL_JAR)")
    p.add_argument("--store", default=STORE, help=f"store folder (default {STORE})")
    p.add_argument("-cf", "--copybooks", action="append", default=[], help="copybook folder")
    p.add_argument("-ce", "--copybook-extension", action="append", default=[], help="copybook extension")
    p.add_argument("-j", "--jobs", type=int, default=4)
    p.add_argument("--force", action="store_true", help="parse unchanged files again")

    v = commands.add_parser("serve", help="dashboard over the store")
    v.add_argument("--store", default=STORE, help=f"store folder (default {STORE})")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8765)
    v.add_argument("--spec", help="migration-spec.json (default: next to the store or in the parse root)")

    s = commands.add_parser("summary", help="parse rate, counts and common errors")
    s.add_argument("graphs", nargs="?", default=STORE, help="store or folder of graph files")

    f = commands.add_parser("facts", help="programs, calls, data access and files as JSON")
    f.add_argument("graphs", nargs="?", default=STORE, help="store or folder of graph files")
    f.add_argument("--root", default=".", help="make evidence paths relative to this folder")

    c = commands.add_parser("crosscheck", help="compare statement counts with a text scan")
    c.add_argument("graphs", nargs="?", default=STORE, help="store or folder of graph files")
    c.add_argument("-cf", "--copybooks", action="append", default=[], help="copybook folder")
    c.add_argument("-ce", "--copybook-extension", action="append", default=[], help="copybook extension")

    m = commands.add_parser("fetch-mq-copybooks", help="download IBM MQ's COBOL copybooks")
    m.add_argument("--out", required=True, help="folder for the copybooks; pass it to parse with -cf")
    m.add_argument("--version", help="MQ redistributable client version; default: the newest")
    m.add_argument("--accept-license", action="store_true", help="accept IBM's MQ license terms")

    args = parser.parse_args(argv)
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
            parser.error("--jar or $PARSEBOL_JAR is required")
        sources = find_sources(args.sources)
        statuses = collections.Counter()

        def progress(path: str, status: str) -> None:
            statuses[status] += 1
            print(f"[{sum(statuses.values())}/{len(sources)}] {status:7} {os.path.relpath(path)}", flush=True)

        run = parse(args.store, args.jar, sources, args.copybooks, args.copybook_extension,
                    args.jobs, args.force, progress)
        print(f"run {run}: " + ", ".join(f"{n} {s}" for s, n in sorted(statuses.items()))
              + f"; store {args.store}")
        return 1 if statuses["crash"] else 0
    if args.command == "serve":
        serve(args.store, args.host, args.port, args.spec)
        return 0
    project = Project.load(args.graphs)
    if args.command == "summary":
        print(summary(project))
    elif args.command == "crosscheck":
        extensions = args.copybook_extension or [".cpy"]
        scan = TextScan(args.copybooks, ["", *extensions])
        text, graph, differences = crosscheck(project, scan)
        print(f"{'':10} {'text':>6} {'graph':>6}")
        for key in PATTERNS:
            print(f"{key:10} {text[key]:6d} {graph[key]:6d}")
        for name, diff in differences.items():
            print(f"{name}: " + ", ".join(f"{k} text {t} graph {g}" for k, (t, g) in diff.items()))
        return 0 if not differences else 1
    else:
        json.dump(facts(project, args.root), sys.stdout, indent=1)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
