# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Db2 stored procedure definitions, read from CREATE PROCEDURE statements in DDL files.

An external procedure (LANGUAGE COBOL, C, ...) names the program that implements it with EXTERNAL
NAME, or with a bare EXTERNAL, in which case the program has the procedure's name. A native SQL
procedure has its logic in the DDL; for those, ``tables`` and ``calls`` come from a text scan of
its body and are a starting point to check against the body, not parser output.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

DDL_SUFFIXES = {".sql", ".ddl", ".db2", ".spsql"}
NAME = r"[\"\w#@$]+(?:\.[\"\w#@$]+)?"
CREATE = re.compile(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+(" + NAME + r")", re.I)
NEXT_CREATE = re.compile(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?\w+", re.I)
LANGUAGE = re.compile(r"\bLANGUAGE\s+(\w+)", re.I)
EXTERNAL_NAME = re.compile(r"\bEXTERNAL\s+NAME\s+(['\"]?)([\w#@$.]+)\1", re.I)
EXTERNAL = re.compile(r"\bEXTERNAL\b(?!\s+(?:NAME|SECURITY|ACTION)\b)", re.I)
RESULT_SETS = re.compile(r"\bDYNAMIC\s+RESULT\s+SETS?\s+(\d+)", re.I)
WRITES = re.compile(r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO)\s+(" + NAME + r")", re.I)
READS = re.compile(r"\b(DELETE\s+)?(?:FROM|JOIN)\s+(" + NAME + r")", re.I)
CALLS = re.compile(r"\bCALL\s+(" + NAME + r")", re.I)
NOT_TABLES = {"FINAL", "TABLE", "LATERAL", "OLD", "NEW", "SET", "OF"}


@dataclass(frozen=True)
class Procedure:
    name: str  # as written, without quotes; may be schema-qualified
    language: Optional[str]  # COBOL, C, PLI, JAVA, SQL, ...
    program: Optional[str]  # the implementing program of an external procedure
    parameters: tuple  # each parameter as written, such as "IN EMP_ID INTEGER"
    result_sets: int
    path: str
    line: int
    reads: tuple = field(default=())  # native SQL procedures only, from a text scan
    writes: tuple = field(default=())
    calls: tuple = field(default=())

    @property
    def native(self) -> bool:
        return self.language == "SQL"


def find_ddl(root: str | os.PathLike, extra: Iterable[str | os.PathLike] = ()) -> list[Path]:
    """DDL files under ``root`` (by suffix), plus every file under each ``extra`` path. Hidden
    folders and the parser's own checkout (a folder with FORK.md) are skipped."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        if "FORK.md" in filenames and dirpath != str(root):
            dirnames[:] = []
            continue
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "node_modules")
        found += [Path(dirpath) / f for f in sorted(filenames) if Path(f).suffix.lower() in DDL_SUFFIXES]
    for path in map(Path, extra):
        found += sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
    return list(dict.fromkeys(found))


SCHEMA_DDL = re.compile(r"^\s*CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX|VIEW)\s", re.I | re.M)
NOT_DDL_SUFFIXES = {".cbl", ".cob", ".cpy", ".pco", ".sqb", ".md", ".html", ".htm", ".py", ".java",
                    ".js", ".ts", ".class", ".jar", ".zip", ".gz", ".png", ".jpg", ".pdf", ".db"}


TOOL_DIRS = {".git", ".hg", ".svn", ".mfmap", ".amp", ".venv", ".idea", ".vscode", "node_modules"}


def find_schema_ddl(root: str | os.PathLike, extra: Iterable[str | os.PathLike] = ()) -> list[Path]:
    """Files with CREATE TABLE, INDEX or VIEW statements: the DDL files ``find_ddl`` finds, plus
    other text files under ``root`` (such as JCL that runs DSNTIAD) with such a statement at the
    start of a line, including in hidden folders other than tool folders such as .git. Program,
    copybook, documentation, code and binary files are not searched."""
    found = find_ddl(root, extra)
    for dirpath, dirnames, filenames in os.walk(root):
        if "FORK.md" in filenames and dirpath != str(root):
            dirnames[:] = []
            continue
        # Setup folders such as .setup often hold the DDL, so only tool folders are skipped.
        dirnames[:] = sorted(d for d in dirnames if d not in TOOL_DIRS)
        for f in sorted(filenames):
            path = Path(dirpath) / f
            if path.suffix.lower() in NOT_DDL_SUFFIXES | DDL_SUFFIXES:
                continue
            try:
                if path.stat().st_size > 2_000_000:
                    continue
                text = path.read_text(encoding="latin-1")
                if "\0" not in text[:8192] and SCHEMA_DDL.search(text):
                    found.append(path)
            except OSError:
                continue
    return list(dict.fromkeys(found))


def unquote(name: str) -> str:
    return name.replace('"', "").upper()


def parameters(text: str) -> tuple:
    """The parameter list after the procedure name, split at top-level commas."""
    text = text.lstrip()
    if not text.startswith("("):
        return ()
    depth, current, out = 0, "", []
    for ch in text[1:]:
        if ch == ")" and depth == 0:
            break
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            out.append(current)
            current = ""
        else:
            current += ch
    out.append(current)
    return tuple(" ".join(p.split()) for p in out if p.strip())


def read(path: Path) -> list[Procedure]:
    text = path.read_text(encoding="latin-1")
    text = re.sub(r"--[^\n]*", "", text)  # SQL comments; newlines stay so line numbers hold
    out = []
    for match in CREATE.finditer(text):
        end = NEXT_CREATE.search(text, match.end())
        body = text[match.end(): end.start() if end else len(text)]
        name = unquote(match.group(1))
        language = LANGUAGE.search(body)
        language = language.group(1).upper() if language else ("SQL" if re.search(r"\bBEGIN\b", body, re.I) else None)
        external = EXTERNAL_NAME.search(body)
        program = external.group(2).upper() if external else \
            name.split(".")[-1] if language != "SQL" and EXTERNAL.search(body) else None
        sets = RESULT_SETS.search(body)
        reads = writes = calls = ()
        if language == "SQL":
            writes = tuple(dict.fromkeys(unquote(t) for t in WRITES.findall(body) if t.upper() not in NOT_TABLES))
            reads = tuple(dict.fromkeys(unquote(t) for d, t in READS.findall(body)
                                        if not d and t.upper() not in NOT_TABLES))
            calls = tuple(dict.fromkeys(unquote(c) for c in CALLS.findall(body)))
        out.append(Procedure(name, language, program, parameters(body), int(sets.group(1)) if sets else 0,
                             str(path), text.count("\n", 0, match.start()) + 1, reads, writes, calls))
    return out


def procedures(paths: Iterable[Path]) -> list[Procedure]:
    return [p for path in paths for p in read(path)]


def match(called: Optional[str], defined: Iterable[Procedure]) -> Optional[Procedure]:
    """The definition a CALL refers to: the same qualified name, or, for an unqualified CALL (whose
    schema comes from the package's bind options), the only definition with that name."""
    if not called:
        return None
    called = unquote(called)
    defined = list(defined)
    exact = [p for p in defined if p.name == called]
    if exact:
        return exact[0]
    short = [p for p in defined if p.name.split(".")[-1] == called.split(".")[-1]]
    return short[0] if len(short) == 1 and "." not in called else None
