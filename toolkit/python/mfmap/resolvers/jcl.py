# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Batch jobs from JCL and procedures: which job or procedure runs which program in each step, and
which dataset each DD statement names. A program's batch file access (its SELECT ... ASSIGN name)
is matched to the DD statement with that name in the steps that run it, giving reads and writes of
datasets. Programs run through TSO batch (IKJEFT01 with ``RUN PROGRAM(...)`` in SYSTSIN), as Db2
batch programs are, count as run by that step. Symbolic parameters (``&NAME``) are kept as written.
"""

from __future__ import annotations

import collections
import re
from typing import Iterator, Optional

from . import Context, Entity, Fact, Relationship

NAME = "jcl"
STATEMENT = re.compile(r"^//([^\s*][^\s]*)?\s+(JOB|EXEC|DD|PROC)\b\s*(.*)$")
JCL_LINE = re.compile(r"(?m)^//\S*\s+(JOB|EXEC|PROC)\b")
PGM = re.compile(r"\bPGM=([\w#@$&.]+)", re.I)
PROC = re.compile(r"\bPROC=([\w#@$&]+)", re.I)
DSN = re.compile(r"\bDSN(?:AME)?=([^,\s)(]+(?:\([^)]*\))?)", re.I)
RUN_PROGRAM = re.compile(r"\bRUN\s+PROGRAM\s*\(\s*([\w#@$]+)\s*\)", re.I)
TSO_BATCH = {"IKJEFT01", "IKJEFT1A", "IKJEFT1B"}


def operands(text: str) -> str:
    """The operand field: up to the first blank outside quotes (what follows is a comment)."""
    out, quoted = [], False
    for ch in text.strip():
        if ch == "'":
            quoted = not quoted
        elif ch == " " and not quoted:
            break
        out.append(ch)
    return "".join(out)


def statements(text: str) -> list[dict]:
    """JCL statements with continuation lines joined, and in-stream data attached to its DD."""
    out: list[dict] = []
    current: Optional[dict] = None
    instream: Optional[dict] = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw[:71].rstrip()
        if instream is not None:
            if line.startswith("/*") or line.startswith("//"):
                instream = None
            else:
                instream["data"].append(line)
                continue
        if not line.startswith("//") or line.startswith("//*"):
            continue
        if current is not None and current["operands"].endswith(","):
            current["operands"] += operands(line[2:])
            continue
        m = STATEMENT.match(line)
        if not m:
            current = None
            continue
        current = {"name": m.group(1) or "", "op": m.group(2).upper(), "operands": operands(m.group(3)),
                   "line": number, "data": []}
        out.append(current)
        if current["op"] == "DD" and re.match(r"(\*|DATA)(,|$)", current["operands"], re.I):
            instream = current
    return out


def steps(path, text) -> Iterator[Fact | dict]:
    """Entities for jobs and procedures, then one dict per step: its owner, name, program, EXEC line
    and DD statements with a dataset name."""
    owner, step = f"job:{path.stem.upper()}", None
    for s in statements(text):
        if s["op"] == "JOB":
            owner = f"job:{(s['name'] or path.stem).upper()}"
            yield Entity(owner, "defined", path=str(path), line=s["line"])
        elif s["op"] == "PROC" and s["name"]:
            owner = f"proc:{s['name'].upper()}"
            yield Entity(owner, "defined", path=str(path), line=s["line"])
        elif s["op"] == "EXEC":
            if step:
                yield step
            pgm, proc = PGM.search(s["operands"]), PROC.search(s["operands"])
            first = s["operands"].split(",")[0]
            proc_name = proc.group(1) if proc else (first if first and "=" not in first else None)
            step = {"owner": owner, "name": s["name"], "line": s["line"], "via": None, "dds": [],
                    "program": pgm.group(1).upper() if pgm else None,
                    "proc": proc_name.upper() if proc_name and not pgm else None}
        elif s["op"] == "DD" and step:
            dd = s["name"].upper()
            if step["program"] in TSO_BATCH and dd == "SYSTSIN":
                run = RUN_PROGRAM.search("\n".join(s["data"]))
                if run:
                    step["via"], step["program"] = step["program"], run.group(1).upper()
            dsn = DSN.search(s["operands"])
            if dsn and dd and "." not in dd:
                step["dds"].append((dd, dsn.group(1).upper(), s["line"]))
    if step:
        yield step


def resolve(ctx: Context) -> Iterator[Fact]:
    # The batch files each program accesses, by ASSIGN (DD) name.
    access = collections.defaultdict(set)
    for a in ctx.conn.execute("SELECT program, resource, mode FROM access WHERE store = 'file' AND resource IS NOT NULL"):
        access[(a["program"], a["resource"].upper())].add(a["mode"])

    for path, text in ctx.files():
        if not JCL_LINE.search(text):
            continue
        for step in steps(path, text):
            if not isinstance(step, dict):
                yield step
                continue
            owner, where_step = step["owner"], f"{step['owner'].split(':', 1)[1]} step {step['name']}"
            if step["program"]:
                note = f"step {step['name']}" + (f", through {step['via']}" if step["via"] else "")
                yield Relationship("runs", owner, f"program:{step['program']}", note=note,
                                   path=str(path), line=step["line"])
            elif step["proc"]:
                yield Relationship("runs", owner, f"proc:{step['proc']}", note=f"step {step['name']}",
                                   path=str(path), line=step["line"])
            for dd, dsn, line in step["dds"]:
                note = f"DD {dd} in {where_step}"
                yield Relationship("names", owner, f"dataset:{dsn}", note=note, path=str(path), line=line)
                modes = access.get((step["program"], dd)) if step["program"] else None
                if modes:
                    mode = next(iter(modes)) if len(modes) == 1 else "read-write"
                    yield Relationship(mode, f"program:{step['program']}", f"dataset:{dsn}", "declared", dd, note,
                                       str(path), line)
