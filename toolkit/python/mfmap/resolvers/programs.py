# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""What the parsed programs say about themselves: copybooks included, calls between programs, data
access, PERFORM and GO TO between paragraphs, CICS screens sent and received, and transactions
started or returned to."""

from __future__ import annotations

import json
from typing import Iterator

from . import Context, Fact, Relationship

NAME = "programs"
CALL_KINDS = {"CALL": "calls", "LINK": "links", "XCTL": "transfers", "LOAD": "loads",
              "SQL CALL": "calls-procedure"}


def resolve(ctx: Context) -> Iterator[Fact]:
    current = {row["path"] for row in ctx.conn.execute(
        "SELECT f.path FROM files f JOIN run_files r ON r.path = f.path "
        "WHERE r.run_id = (SELECT MAX(id) FROM runs)")}
    for row in ctx.conn.execute("SELECT * FROM programs"):
        if row["file"] in current:
            for copybook in json.loads(row["copybooks"] or "[]"):
                yield Relationship("includes", f"program:{row['name']}", f"copybook:{copybook}", path=row["file"])
    for c in ctx.conn.execute("SELECT * FROM calls"):
        if c["file"] not in current:
            continue
        kind = CALL_KINDS.get(c["via"], c["via"].lower())
        target = (("procedure:" if c["via"] == "SQL CALL" else "program:") + c["target"]) if c["target"] else None
        candidates = json.loads(c["candidates"] or "[]")
        yield Relationship(kind, f"program:{c['program']}", target, c["resolved"], c["expression"],
                           f"maybe {', '.join(candidates)}" if candidates else None, c["path"], c["line"])
    for a in ctx.conn.execute("SELECT * FROM access"):
        if a["file"] not in current:
            continue
        target = f"{a['store']}:{a['resource']}" if a["resource"] else None
        yield Relationship(a["mode"], f"program:{a['program']}", target, a["resolved"], a["expression"],
                           a["verb"], a["path"], a["line"])

    for p in ctx.project.programs.values():
        def where(s):
            return f"paragraph:{p.name}.{s.paragraph.name}" if s.paragraph else f"program:{p.name}"

        for s in p.performs:
            if s.target_name:
                loc = s.location
                yield Relationship("performs", where(s), f"paragraph:{p.name}.{s.target_name}",
                                   note=f"thru {s.thru_name}" if s.thru_name else None,
                                   path=loc.path if loc else None, line=loc.line if loc else None)
        for s in p.statements:
            loc = s.location
            if type(s).__name__ == "GoTo":
                for t in s.targets:
                    yield Relationship("goes-to", where(s), f"paragraph:{p.name}.{t}",
                                       path=loc.path if loc else None, line=loc.line if loc else None)
        for s in p.cics:
            loc = s.location
            evidence = dict(path=loc.path if loc else None, line=loc.line if loc else None)
            if s.command in ("SEND MAP", "RECEIVE MAP") or (s.verb in ("SEND", "RECEIVE") and s.has("MAP")):
                name, how = p.resolve(s.option("MAP"))
                mapset, _ = p.resolve(s.option("MAPSET")) if s.option("MAPSET") else (name, how)
                target = f"screen:{mapset}.{name}" if name and mapset else None
                yield Relationship("sends" if s.verb == "SEND" else "receives", f"program:{p.name}", target,
                                   how if target else "unresolved", s.option("MAP") or "", **evidence)
            elif s.verb in ("RETURN", "START") and s.option("TRANSID"):
                name, how = p.resolve(s.option("TRANSID"))
                yield Relationship("returns-to" if s.verb == "RETURN" else "starts", f"program:{p.name}",
                                   f"transaction:{name}" if name else None, how, s.option("TRANSID"),
                                   **evidence)
