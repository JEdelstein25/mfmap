# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""How users and other systems call into the application.

- ``interface:3270`` ``starts`` each CICS transaction whose program sends a screen (terminal users).
  Uses the ``starts`` rows the ``cics`` resolver wrote, which runs first.
- ``api:PROGRAM`` ``serves`` each program that reads an MQ queue (MQGET): another system sends it
  requests; the note names the request and reply queue items, and says when the program is started
  by an MQ trigger (EXEC CICS RETRIEVE of the trigger message).
- ``script:NAME`` ``submits`` each job a script sends to JES by FTP (``put x.jcl`` after
  ``site filetype=JES``).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from ..model import data_access
from . import Context, Entity, Fact, Relationship

NAME = "interfaces"
FTP_JES = re.compile(r"filetype\s*=\s*JES", re.I)
PUT_JCL = re.compile(r"^\s*put\s+(\S+\.jcl)\b", re.I)


def resolve(ctx: Context) -> Iterator[Fact]:
    screens = {p.name for p in ctx.project.programs.values()
               if any(s.verb == "SEND" and s.has("MAP") for s in p.cics)}
    terminal = False
    for r in ctx.conn.execute("SELECT * FROM relationships WHERE resolver = 'cics' AND kind = 'starts'"):
        if r["target"] and r["target"].split(":", 1)[1] in screens:
            terminal = True
            yield Relationship("starts", "interface:3270", r["source"], note=f"{r['target']} sends screens",
                               path=r["path"], line=r["line"])
    if terminal:
        yield Entity("interface:3270", "defined", "CICS terminal users")

    for p in ctx.project.programs.values():
        access = [a for a in data_access(p) if a.store == "mq"]
        gets = [a for a in access if a.mode == "read"]
        if not gets:
            continue
        puts = sorted({a.resource or a.expression for a in access if a.mode == "write"})
        trigger = any(s.verb == "RETRIEVE" for s in p.cics)
        note = (f"MQ requests on {', '.join(sorted({a.resource or a.expression for a in gets}))}"
                + (f"; replies on {', '.join(puts)}" if puts else "")
                + ("; started by an MQ trigger" if trigger else ""))
        loc = gets[0].statement.location
        yield Entity(f"api:{p.name}", "defined", note, loc.path if loc else None, loc.line if loc else None)
        yield Relationship("serves", f"api:{p.name}", f"program:{p.name}", note=note,
                           path=loc.path if loc else None, line=loc.line if loc else None)

    for path, text in ctx.files(lambda p: p.suffix.lower() in (".sh", ".bash", ".ksh", ".ftp", ".txt", "")):
        if not FTP_JES.search(text):
            continue
        script = f"script:{Path(path).name}"
        found = False
        for number, line in enumerate(text.splitlines(), 1):
            if m := PUT_JCL.match(line):
                found = True
                job = Path(m.group(1)).stem.upper()
                yield Relationship("submits", script, f"job:{job}", note="FTP to JES", path=str(path), line=number)
        if found:
            yield Entity(script, "defined", "submits jobs to JES by FTP", str(path), 1)
