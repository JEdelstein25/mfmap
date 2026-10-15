# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""CICS resource definitions and BMS screens.

From CSD definitions (``DEFINE TRANSACTION(...) PROGRAM(...)``, as DFHCSDUP reads them): each
transaction and the program it starts, and the programs CICS defines. From BMS map source
(``DFHMSD`` and ``DFHMDI`` macros): each screen as ``screen:MAPSET.MAP``. Markdown and HTML files
are skipped because they often quote definitions as examples.
"""

from __future__ import annotations

import re
from typing import Iterator

from . import Context, Entity, Fact, Relationship

NAME = "cics"
DEFINE = re.compile(r"\bDEFINE\s+(TRANSACTION|PROGRAM|MAPSET)\s*\(\s*([\w#@$]+)\s*\)", re.I)
PROGRAM = re.compile(r"\bPROGRAM\s*\(\s*([\w#@$]+)\s*\)", re.I)
DESCRIPTION = re.compile(r"\bDESCRIPTION\s*\(([^)]*)\)", re.I)
MAPSET = re.compile(r"^([\w#@$]+)\s+DFHMSD\b", re.I)
MAP = re.compile(r"^([\w#@$]+)\s+DFHMDI\b", re.I)


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def resolve(ctx: Context) -> Iterator[Fact]:
    for path, text in ctx.files(lambda p: p.suffix.lower() not in (".md", ".html", ".htm")):
        if "DEFINE" in text.upper():
            defines = list(DEFINE.finditer(text))
            for i, d in enumerate(defines):
                body = text[d.end(): defines[i + 1].start() if i + 1 < len(defines) else len(text)]
                kind, name, line = d.group(1).upper(), d.group(2).upper(), line_of(text, d.start())
                if kind == "TRANSACTION":
                    description = DESCRIPTION.search(body)
                    yield Entity(f"transaction:{name}", "defined",
                                 description.group(1).strip() if description else None, str(path), line)
                    program = PROGRAM.search(body)
                    if program:
                        yield Relationship("starts", f"transaction:{name}", f"program:{program.group(1).upper()}",
                                           path=str(path), line=line)
                elif kind == "PROGRAM":
                    yield Entity(f"program:{name}", "cics-program", path=str(path), line=line)
        if "DFHMSD" in text.upper():
            mapset = None
            for number, line in enumerate(text.splitlines(), 1):
                if m := MAPSET.match(line):
                    mapset = m.group(1).upper()
                elif (m := MAP.match(line)) and mapset:
                    yield Entity(f"screen:{mapset}.{m.group(1).upper()}", "defined", path=str(path), line=number)
