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

from .crosscheck import PATTERNS, TextScan, crosscheck
from .model import Project, call_edges, data_access
from .run import find_sources, parse


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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="cobolgraph")
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("parse", help="parse sources into graph files")
    p.add_argument("sources", nargs="+", help="source files or folders")
    p.add_argument("--jar", default=os.environ.get("PARSEBOL_JAR"), help="server.jar (or $PARSEBOL_JAR)")
    p.add_argument("--out", required=True, help="output folder for graph files")
    p.add_argument("-cf", "--copybooks", action="append", default=[], help="copybook folder")
    p.add_argument("-ce", "--copybook-extension", action="append", default=[], help="copybook extension")
    p.add_argument("-j", "--jobs", type=int, default=4)

    s = commands.add_parser("summary", help="parse rate, counts and common errors")
    s.add_argument("graphs", help="folder of graph files")

    f = commands.add_parser("facts", help="programs, calls, data access and files as JSON")
    f.add_argument("graphs", help="folder of graph files")
    f.add_argument("--root", default=".", help="make evidence paths relative to this folder")

    c = commands.add_parser("crosscheck", help="compare statement counts with a text scan")
    c.add_argument("graphs", help="folder of graph files")
    c.add_argument("-cf", "--copybooks", action="append", default=[], help="copybook folder")
    c.add_argument("-ce", "--copybook-extension", action="append", default=[], help="copybook extension")

    args = parser.parse_args(argv)
    if args.command == "parse":
        if not args.jar:
            parser.error("--jar or $PARSEBOL_JAR is required")
        results = parse(args.jar, find_sources(args.sources), args.out, args.copybooks,
                        args.copybook_extension, args.jobs)
        for r in results:
            if not r.ok:
                print(f"crashed: {r.source}: {r.message}", file=sys.stderr)
        print(f"parsed {sum(r.ok for r in results)} of {len(results)} sources into {args.out}")
        return 0 if all(r.ok for r in results) else 1
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
