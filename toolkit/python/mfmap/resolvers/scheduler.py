# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Job schedules from batch schedulers, so the map says when jobs run and in what order.

Control-M job definitions (XML ``DEFTABLE`` exports): each folder (or, in older exports, scheduling
table) ``schedules`` its jobs, noting the days and time, and a job whose OUTCOND (``SIGN="+"``) is
another job's INCOND in the same file ``precedes`` it. CA-7 job listings (``LJOB,JOB=...,LIST=ALL``
output): a job ``triggers`` each job in its TRIGGERED JOBS section, noting the schedule ID.
"""

from __future__ import annotations

import collections
import re
from typing import Iterator

from . import Context, Entity, Fact, Relationship

NAME = "scheduler"
ATTR = re.compile(r'(\w+)="([^"]*)"')
FOLDER = re.compile(r"<(?:SMART_FOLDER|FOLDER|SMART_TABLE|SCHED_TABLE|TABLE)\b")
CA7_JOB = re.compile(r"^\s*1?LJOB,JOB=([\w#@$]+)")
CA7_TRIGGER = re.compile(r"^\s+JOB=([\w#@$]+)\s+SCHID=(\d+)")


def control_m(path, text: str) -> Iterator[Fact]:
    folder, job = None, None
    produced = collections.defaultdict(list)  # condition -> jobs that add it
    needed = []  # (condition, job, line)
    for number, line in enumerate(text.splitlines(), 1):
        attrs = dict(ATTR.findall(line))
        if FOLDER.search(line):
            folder = f"schedule:{attrs.get('FOLDER_NAME') or attrs.get('TABLE_NAME') or 'unnamed'}"
            when = ", ".join(f"{k.lower()} {attrs[k]}" for k in ("DAYS", "TIMETO", "INTERVAL") if attrs.get(k))
            yield Entity(folder, "defined", f"Control-M {when}" if when else "Control-M", str(path), number)
        elif "<JOB " in line and folder:
            job = f"job:{(attrs.get('MEMNAME') or attrs.get('JOBNAME', '')).upper()}"
            when = ", ".join(f"{k.lower()} {attrs[k]}" for k in ("DAYS", "TIMETO") if attrs.get(k))
            note = "; ".join(filter(None, [attrs.get("DESCRIPTION"), when])) or None
            yield Relationship("schedules", folder, job, note=note, path=str(path), line=number)
        elif "<OUTCOND " in line and job and attrs.get("SIGN") == "+":
            produced[attrs["NAME"]].append(job)
        elif "<INCOND " in line and job:
            needed.append((attrs["NAME"], job, number))
        elif "</JOB>" in line:
            job = None
    for condition, job, number in needed:
        for before in produced.get(condition, []):
            yield Relationship("precedes", before, job, note=f"Control-M condition {condition}",
                               path=str(path), line=number)


def ca7(path, text: str) -> Iterator[Fact]:
    job, triggered = None, False
    for number, line in enumerate(text.splitlines(), 1):
        if m := CA7_JOB.match(line):
            job, triggered = f"job:{m.group(1).upper()}", False
            yield Entity(job, "scheduled", "CA-7", str(path), number)
        elif "TRIGGERED JOBS" in line:
            triggered = True
        elif triggered and job and (m := CA7_TRIGGER.match(line)):
            yield Relationship("triggers", job, f"job:{m.group(1).upper()}", note=f"CA-7 SCHID {m.group(2)}",
                               path=str(path), line=number)
        elif triggered and line.strip() and not line.startswith(" " * 6):
            triggered = False


def resolve(ctx: Context) -> Iterator[Fact]:
    for path, text in ctx.files():
        if "<DEFTABLE" in text and "<JOB " in text:
            yield from control_m(path, text)
        elif "LJOB,JOB=" in text:
            yield from ca7(path, text)
