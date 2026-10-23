# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Compare graph statement counts with an independent text scan of the source.

The scan does not use the parser. It reads fixed-format source, drops comment lines, sequence
numbers and string literals, expands COPY and EXEC SQL INCLUDE members it can find, and counts
statement keywords. A difference means the graph or the scan missed something; read both.
"""

from __future__ import annotations

import collections
import os
import re
from pathlib import Path
from typing import Iterable, Optional, Sequence

from .model import Program, Project

PATTERNS = {
    "CALL": r"(?<![\w-])CALL(?![\w-])",
    "PERFORM": r"(?<![\w-])PERFORM(?![\w-])",
    "EXEC CICS": r"\bEXEC\s+CICS\b",
    "EXEC SQL": r"\bEXEC\s+SQL\b(?!\s+INCLUDE\b)",
    "SQL CALL": r"\bEXEC\s+SQL\s+CALL\b",
    "EXEC DLI": r"\bEXEC\s+DLI\b",
}
INCLUDE = re.compile(
    r"\bCOPY\s+['\"]?([\w#@$-]+)['\"]?|\bEXEC\s+SQL\s+INCLUDE\s+([\w#@$-]+)|^\s*INCLUDE\s+([\w#@$-]+)", re.I)
STRING = re.compile(r"'[^']*'|\"[^\"]*\"")
EXEC_SQL = re.compile(r"\bEXEC\s+SQL\b.*?\bEND-EXEC\b", re.I | re.S)


def graph_counts(program: Program) -> collections.Counter:
    return collections.Counter({
        "CALL": len(program.calls), "PERFORM": len(program.performs),
        "EXEC CICS": len(program.cics), "EXEC SQL": len(program.sql), "EXEC DLI": len(program.dli),
        "SQL CALL": sum(s.statement_type == "CALL" for s in program.sql),
    })


class TextScan:
    def __init__(self, copybook_dirs: Iterable[str | os.PathLike], extensions: Sequence[str] = ("", ".cpy")):
        self.dirs = [Path(d) for d in copybook_dirs]
        self.extensions = [e if not e or e.startswith(".") else "." + e for e in extensions]

    def find(self, name: str) -> Optional[Path]:
        for d in self.dirs:
            for e in self.extensions:
                for candidate in (d / (name + e), d / (name.upper() + e)):
                    if candidate.is_file():
                        return candidate
        return None

    def text(self, path: Path, seen: tuple = ()) -> str:
        """Code text with copybooks expanded; SQLCA and members that are not found stay out."""
        out = []
        for raw in path.read_text(encoding="latin-1").splitlines():
            if len(raw) > 6 and raw[6] in "*/":
                continue
            code = raw[7:72]
            match = INCLUDE.search(code)
            member = self.find(next(g for g in match.groups() if g)) if match else None
            if member and member not in seen:
                # Keep a bare INCLUDE so the EXEC SQL on the line above is still not counted.
                out.append(STRING.sub("''", code[: match.start()]) + (" INCLUDE" if match.group(3) else ""))
                out.append(self.text(member, seen + (member,)))
            else:
                out.append(STRING.sub("''", code))
        return "\n".join(out)

    def counts(self, path: Path) -> collections.Counter:
        text = self.text(path)
        counts = collections.Counter({k: len(re.findall(p, text, re.I)) for k, p in PATTERNS.items()})
        # A stored procedure CALL inside EXEC SQL is not a COBOL CALL.
        counts["CALL"] = len(re.findall(PATTERNS["CALL"], EXEC_SQL.sub(" ", text), re.I))
        return counts


def crosscheck(project: Project, scan: TextScan) -> tuple[collections.Counter, collections.Counter, dict]:
    """Totals from the text scan and the graph, and per-program differences."""
    text_total, graph_total, differences = collections.Counter(), collections.Counter(), {}
    for program in sorted(project.programs.values(), key=lambda p: p.name):
        if not program.file.path or not os.path.exists(program.file.path):
            continue
        text, graph = scan.counts(Path(program.file.path)), graph_counts(program)
        text_total.update(text)
        graph_total.update(graph)
        diff = {k: (text[k], graph[k]) for k in PATTERNS if text[k] != graph[k]}
        if diff:
            differences[program.name] = diff
    return text_total, graph_total, differences
