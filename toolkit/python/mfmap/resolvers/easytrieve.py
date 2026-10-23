# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Easytrieve Plus programs (``.ezt``), which the COBOL parser does not read: each program, the
files it reads and writes by their FILE names (the JCL DD names), the reports it prints, the macros
it includes and the programs it calls. Files named in JOB INPUT, GET, READ or as SORT input are
read; files named in PUT or WRITE, or as SORT output, are written."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from . import Context, Entity, Fact, Relationship

NAME = "easytrieve"
WORD = re.compile(r"[A-Z0-9][A-Z0-9#@$-]*")


def statements(text: str) -> Iterator[tuple[int, str]]:
    """(first line number, statement text) with comments, columns past 72 and + continuations
    removed."""
    start, parts = None, []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw[:72].rstrip()
        if not line.strip() or line.lstrip().startswith("*"):
            continue
        start = start or number
        if line.endswith("+") or line.endswith("-"):
            parts.append(line[:-1])
            continue
        parts.append(line)
        yield start, " ".join(parts).upper()
        start, parts = None, []
    if parts:
        yield start, " ".join(parts).upper()


def resolve(ctx: Context) -> Iterator[Fact]:
    for path, text in ctx.files(lambda p: p.suffix.lower() == ".ezt"):
        program = f"program:{Path(path).stem.upper()}"
        yield Entity(program, "defined", "Easytrieve Plus program", str(path), 1)
        stmts = list(statements(text))
        files = {s.split()[1] for _, s in stmts if s.split()[0] == "FILE" and len(s.split()) > 1}

        def rel(kind, target, line, expression):
            return Relationship(kind, program, target, "declared", expression, path=str(path), line=line)

        for line, s in stmts:
            words = s.split()
            verb = words[0]
            if verb == "JOB" and len(words) > 1 and words[1] == "INPUT":
                inputs = s.split("INPUT", 1)[1]
                inputs = re.split(r"\b(START|FINISH|NAME|ENVIRONMENT)\b", inputs)[0]
                for name in dict.fromkeys(WORD.findall(re.sub(r"KEY\s*\([^)]*\)", " ", inputs))):
                    if name in files:
                        yield rel("read", f"file:{name}", line, s)
            elif verb in ("GET", "READ") and len(words) > 1 and words[1] in files:
                yield rel("read", f"file:{words[1]}", line, s)
            elif verb in ("PUT", "WRITE") and len(words) > 1 and words[1] in files:
                yield rel("write", f"file:{words[1]}", line, s)
            elif verb == "SORT" and len(words) > 3 and "TO" in words:
                yield rel("read", f"file:{words[1]}", line, s)
                yield rel("write", f"file:{words[words.index('TO') + 1]}", line, s)
            elif verb == "REPORT" and len(words) > 1:
                yield rel("prints", f"report:{Path(path).stem.upper()}.{words[1]}", line, s)
            elif verb == "CALL" and len(words) > 1:
                yield Relationship("calls", program, f"program:{words[1]}", "literal", s,
                                   path=str(path), line=line)
            elif verb.startswith("%"):
                yield Relationship("includes", program, f"macro:{verb[1:]}", "literal", s,
                                   path=str(path), line=line)
