# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""What the parsed programs say about themselves: copybooks included, calls between programs, data
access, PERFORM and GO TO between paragraphs, CICS screens sent and received, and transactions
started or returned to.

So that PERFORM chains can be followed through a program and into the programs it calls:

- ``invokes`` goes from the paragraph that makes a call to the program it calls;
- ``enters`` goes from a program to the paragraph control reaches first;
- ``falls-through`` goes from a paragraph to the next one when it does not end in an unconditional
  GO TO, GOBACK, STOP RUN, EXIT PROGRAM or EXEC CICS RETURN, XCTL or ABEND (this is also how PERFORM A THRU B reaches the paragraphs
  between A and B);
- ``contains`` goes from a program to each of its paragraphs, and from a section to its paragraphs;
- ``handles`` goes to the paragraph an EXEC CICS HANDLE ABEND or HANDLE CONDITION names.
"""

from __future__ import annotations

import json
import re
from typing import Iterator

from . import Context, Entity, Fact, Relationship
from ..model import STATEMENT_NODE_TYPES, member_name, source_path

NAME = "programs"
CALL_KINDS = {"CALL": "calls", "LINK": "links", "XCTL": "transfers", "LOAD": "loads",
              "SQL CALL": "calls-procedure"}


def resolve(ctx: Context) -> Iterator[Fact]:
    current = {row["path"] for row in ctx.conn.execute(
        "SELECT f.path FROM files f JOIN run_files r ON r.path = f.path "
        "WHERE r.run_id = (SELECT MAX(id) FROM runs)")}
    copies = {}  # (program, copybook) -> where it is first copied, in the program or another copybook
    for p in ctx.project.programs.values():
        for n in p._own():
            if n.kind == "CopyNode" and n.name and n.location:
                copies.setdefault((p.name, n.name.upper()), n.location)
    for row in ctx.conn.execute("SELECT * FROM programs"):
        if row["file"] in current:
            for copybook in json.loads(row["copybooks"] or "[]"):
                loc = copies.get((row["name"], copybook.upper()))
                yield Relationship("includes", f"program:{row['name']}", f"copybook:{copybook}",
                                   path=loc.path if loc else row["file"], line=loc.line if loc else None)
    for c in ctx.conn.execute("SELECT * FROM calls"):
        if c["file"] not in current:
            continue
        kind = CALL_KINDS.get(c["via"], c["via"].lower())
        target = (("procedure:" if c["via"] == "SQL CALL" else "program:") + c["target"]) if c["target"] else None
        candidates = json.loads(c["candidates"] or "[]")
        note = f"maybe {', '.join(candidates)}" if candidates else None
        yield Relationship(kind, f"program:{c['program']}", target, c["resolved"], c["expression"], note,
                           c["path"], c["line"])
        if c["paragraph"]:
            yield Relationship("invokes", f"paragraph:{c['program']}.{c['paragraph']}", target, c["resolved"],
                               c["expression"], note or c["via"], c["path"], c["line"])
    for a in ctx.conn.execute("SELECT * FROM access"):
        if a["file"] not in current:
            continue
        target = f"{a['store']}:{a['resource']}" if a["resource"] else None
        yield Relationship(a["mode"], f"program:{a['program']}", target, a["resolved"], a["expression"],
                           a["verb"], a["path"], a["line"])

    for p in ctx.project.renamed:
        yield Entity(f"program:{p.name}", "duplicate-program-id",
                     f"PROGRAM-ID {p.program_id} is also in another file, so it is named after its file",
                     path=source_path(p.file))
    for f in ctx.project.files:
        stem = member_name(source_path(f))
        if f.programs and f.programs[0] not in ctx.project.renamed and re.fullmatch(r"[A-Z#@$][A-Z0-9#@$]{0,7}", stem) \
                and stem != f.programs[0].name:
            yield Entity(f"program:{f.programs[0].name}", "program-id-differs-from-file",
                         f"its file is named {stem}; a CALL, LINK or XCTL of {stem} may mean this program",
                         path=source_path(f))

    for p in ctx.project.programs.values():
        def where(s):
            return f"paragraph:{p.name}.{s.paragraph.name}" if s.paragraph else f"program:{p.name}"

        yield from flow(p)
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
            elif s.verb in ("RETURN", "START", "RUN") and s.option("TRANSID"):
                name, how = p.resolve(s.option("TRANSID"))
                yield Relationship("returns-to" if s.verb == "RETURN" else "starts", f"program:{p.name}",
                                   f"transaction:{name}" if name else None, how, s.option("TRANSID"),
                                   **evidence)
            elif s.verb == "HANDLE":  # HANDLE ABEND LABEL(x), HANDLE CONDITION NOTFND(x): x runs on that event
                for option, label in s.options:
                    target = p.paragraph(label.strip("() ")) if label else None
                    if target:
                        yield Relationship("handles", where(s), f"paragraph:{p.name}.{target.name}",
                                           "literal", label, f"HANDLE {option}", **evidence)


def ends(statements) -> bool:
    """Whether control leaves at the end of these statements instead of falling into the next
    paragraph: the last one outside any IF, EVALUATE or other statement is an unconditional GO TO,
    GOBACK, STOP RUN, EXIT PROGRAM, or EXEC CICS RETURN, XCTL or ABEND."""
    top = [s for s in statements if s.location and not any(
        a.node_type in STATEMENT_NODE_TYPES for a in s.node.ancestors())]
    if not top:
        return False
    words = max(top, key=lambda s: (s.location.line, s.location.column)).source.upper().replace(".", " ").split()
    return (words[:1] == ["GOBACK"] or words[:2] in (["STOP", "RUN"], ["EXIT", "PROGRAM"])
            or (words[:1] == ["GO"] and "DEPENDING" not in words)
            or (words[:2] == ["EXEC", "CICS"] and words[2:3] in (["RETURN"], ["XCTL"], ["ABEND"])))


def flow(p) -> Iterator[Fact]:
    """The paragraphs a program and its sections contain, where control enters the program, and
    where it falls from one paragraph into the next."""
    paragraphs = sorted((x for x in p.paragraphs if x.node.location),
                        key=lambda x: (x.node.location.line, x.node.location.column))
    if not paragraphs:
        return
    for x in paragraphs:
        loc = x.node.location
        yield Relationship("contains", f"program:{p.name}", f"paragraph:{p.name}.{x.name}",
                           path=loc.path, line=loc.line)
    for section in p.sections:
        for x in paragraphs:
            if any(a is section.node for a in x.node.ancestors()):
                yield Relationship("contains", f"paragraph:{p.name}.{section.name}",
                                   f"paragraph:{p.name}.{x.name}", path=x.node.location.path,
                                   line=x.node.location.line)
    first = paragraphs[0]
    if not ends(p._statements_by_paragraph.get(None, [])):
        yield Relationship("enters", f"program:{p.name}", f"paragraph:{p.name}.{first.name}",
                           path=first.node.location.path, line=first.node.location.line)
    for this, following in zip(paragraphs, paragraphs[1:]):
        if not ends(this.statements):
            yield Relationship("falls-through", f"paragraph:{p.name}.{this.name}",
                               f"paragraph:{p.name}.{following.name}",
                               path=following.node.location.path, line=following.node.location.line)
