# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""IMS databases and PSBs from DBDGEN and PSBGEN source, joined to the programs that use them.

A DBD (``DBD NAME=...``) is ``database:NAME``; it ``contains`` its segments (``ims:SEGMENT``, as
programs' IMS access names them) and is ``stored-in`` the DD names of its DATASET statements. A PSB
(``PSBGEN PSBNAME=...``) ``uses`` the database of each PCB, noting PROCOPT. A program ``uses`` a PSB
when it schedules it (``EXEC DLI SCHD PSB(...)``) or a DFSRRC00 job step runs it with that PSB. For
such a step, each PCB's DD names are matched to the step's DD statements: a database is
``stored-in`` that dataset, and a GSAM read or write reaches its dataset (PROCOPT L or LS writes,
anything else reads).
"""

from __future__ import annotations

import re
from typing import Iterator

from . import Context, Entity, Fact, Relationship, jcl

NAME = "ims"
DBD = re.compile(r"^\S*\s+DBD\s+.*?\bNAME=([\w#@$]+)(?:.*?\bACCESS=\(?([\w,]+))?", re.I)
SEGM = re.compile(r"^\S*\s+SEGM\s+.*?\bNAME=([\w#@$]+)", re.I)
DATASET = re.compile(r"^\S*\s+DATASET\s+(.*)$", re.I)
DD_NAME = re.compile(r"\bDD(\d)=([\w#@$]+)", re.I)
PCB = re.compile(r"^\S*\s+PCB\s+.*?\bTYPE=(\w+).*?\bDBDNAME=([\w#@$]+)(?:.*?\bPROCOPT=(\w+))?", re.I)
PSBGEN = re.compile(r"^\S*\s+PSBGEN\s+.*?\bPSBNAME=([\w#@$]+)", re.I)
STEP_PSB = re.compile(r"DFSRRC00 \w+, PSB ([\w#@$]+)")


def gen_source(path, text: str):
    """(databases, psbs) from one file: {dbd: (access, [(segment, line)], [dd], line)} and
    {psb: ([(type, dbd, procopt, line)], line)}."""
    databases, psbs, dbd, pcbs = {}, {}, None, []
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("*"):
            continue
        if m := DBD.match(line):
            dbd = m.group(1).upper()
            databases[dbd] = ((m.group(2) or "").upper(), [], [], number)
        elif dbd and (m := SEGM.match(line)):
            databases[dbd][1].append((m.group(1).upper(), number))
        elif dbd and (m := DATASET.match(line)):
            databases[dbd][2].extend(name.upper() for _, name in sorted(DD_NAME.findall(m.group(1))))
        elif m := PCB.match(line):
            pcbs.append((m.group(1).upper(), m.group(2).upper(), (m.group(3) or "").upper(), number))
        elif m := PSBGEN.match(line):
            psbs[m.group(1).upper()] = (pcbs, number)
            pcbs = []
    return databases, psbs


def resolve(ctx: Context) -> Iterator[Fact]:
    databases, psbs, where = {}, {}, {}
    for path, text in ctx.files():
        if re.search(r"\b(DBDGEN|PSBGEN)\b", text):
            d, p = gen_source(path, text)
            databases.update(d)
            psbs.update(p)
            where.update({name: str(path) for name in [*d, *p]})
    for name, (access, segments, dds, line) in databases.items():
        yield Entity(f"database:{name}", "defined", access or None, where[name], line)
        for segment, number in segments:
            yield Relationship("contains", f"database:{name}", f"ims:{segment}", path=where[name], line=number)
        for dd in dds:
            yield Relationship("stored-in", f"database:{name}", f"dd:{dd}", path=where[name], line=line)
    for name, (pcbs, line) in psbs.items():
        yield Entity(f"psb:{name}", "defined", None, where[name], line)
        for kind, dbd, procopt, number in pcbs:
            yield Relationship("uses", f"psb:{name}", f"database:{dbd}", note=f"{kind} PCB, PROCOPT {procopt}",
                               path=where[name], line=number)

    for p in ctx.project.programs.values():
        for s in p.dli:
            if s.verb == "SCHD" and s.option("PSB"):
                psb, how = p.resolve(s.option("PSB").strip("()"))
                loc = s.location
                yield Relationship("uses", f"program:{p.name}", f"psb:{psb}" if psb else None, how,
                                   s.option("PSB"), "EXEC DLI SCHD", loc.path if loc else None, loc.line if loc else None)

    for path, text in ctx.files():
        if not jcl.JCL_LINE.search(text) or "DFSRRC00" not in text.upper():
            continue
        for step in jcl.steps(path, text):
            m = STEP_PSB.search(step.get("via") or "") if isinstance(step, dict) else None
            if not m:
                continue
            program, psb = f"program:{step['program']}", m.group(1).upper()
            yield Relationship("uses", program, f"psb:{psb}", note=f"{step['owner']} step {step['name']}",
                               path=str(path), line=step["line"])
            dds = {dd: (dsn, line) for dd, dsn, line in step["dds"]}
            for kind, dbd, procopt, _ in psbs.get(psb, ([], 0))[0]:
                mode = "write" if procopt.startswith("L") else "read"
                for dd in databases.get(dbd, ("", [], [], 0))[2]:
                    if dd not in dds:
                        continue
                    dsn, line = dds[dd]
                    if kind == "GSAM":
                        yield Relationship(mode, program, f"dataset:{dsn}", "declared", dd,
                                           f"GSAM {dbd} through PSB {psb}", str(path), line)
                    else:
                        yield Relationship("stored-in", f"database:{dbd}", f"dataset:{dsn}", "declared", dd,
                                           f"DD {dd} in {step['owner']} step {step['name']}", str(path), line)
