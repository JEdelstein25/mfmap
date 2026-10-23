# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Db2 tables, columns, keys, indexes and views from DDL files.

``mfmap parse`` runs the parser's ``ddl`` command on DDL files (``.sql``, ``.ddl``, ``.db2`` and
text files such as JCL with a CREATE TABLE, INDEX or VIEW at the start of a line) and keeps its
output in the store's ``ddl`` table. This resolver turns it into:

- ``db2:TABLE`` "defined" (or "view") with its column count, primary key and qualified name
- ``column:TABLE.COLUMN`` "column" with its type, NOT NULL and default
- ``index:NAME`` "defined", and ``indexes`` from the index to its table
- ``references`` from a table to the table a foreign key points at, with the columns
- ``selects-from`` from a view to each table it reads
- ``ddl:FILE`` "parse-error" for each statement the grammar rejected
- ``db2:TABLE`` "no-definition" for each table the programs access that no DDL defines

A table is named as the programs name it, so the definition and the programs' reads and writes
meet: ``BANKZ.ACCOUNT`` stays qualified when the programs write ``BANKZ.ACCOUNT`` or qualify other
tables with ``BANKZ``, and becomes ``ACCOUNT`` otherwise; ``ACCOUNT`` becomes ``BANKZ.ACCOUNT``
when that is the only way the programs name it. Catalog tables (``SYSIBM.SYSDUMMY1``) are not
reported as missing.
"""

from __future__ import annotations

import json
from typing import Iterator

from . import Context, Entity, Fact, Relationship

NAME = "ddl"


def resolve(ctx: Context) -> Iterator[Fact]:
    accessed = {r["resource"] for r in ctx.conn.execute(
        "SELECT DISTINCT resource FROM access WHERE store = 'db2' AND resource IS NOT NULL")}

    schemas = {a.rsplit(".", 1)[0] for a in accessed if "." in a}

    def table(name: str) -> str:
        if name in accessed:
            return f"db2:{name}"
        if "." in name:
            schema, short = name.rsplit(".", 1)
            # Programs that qualify other tables with this schema would qualify this one too.
            return f"db2:{name if short not in accessed and schema in schemas else short}"
        qualified = [a for a in accessed if a.endswith("." + name)]
        return f"db2:{qualified[0] if len(qualified) == 1 else name}"

    defined = set()
    for row in ctx.conn.execute("SELECT path, result FROM ddl"):
        path, result = row["path"], json.loads(row["result"])
        for error in result.get("errors", []):
            yield Entity(f"ddl:{path}", "parse-error", f"{error['statement']}: {error['message']}",
                         path, error["line"])
        for o in result.get("objects", []):
            kind, line = o["kind"], o["line"]
            if kind in ("TABLE", "ALTER TABLE"):
                name = table(o["name"])
                if kind == "TABLE":
                    defined.add(name)
                    key = ", ".join(o["primaryKey"])
                    note = f"{len(o['columns'])} columns" + (f"; primary key {key}" if key else "")
                    if f"db2:{o['name']}" != name:
                        note += f"; defined as {o['name']}"
                    yield Entity(name, "defined", note, path, line)
                for c in o["columns"]:
                    note = " ".join(filter(None, [c.get("type"), "NOT NULL" if c["notNull"] else None,
                                                  c.get("default")]))
                    yield Entity(f"column:{name[4:]}.{c['name']}", "column", note, path, line)
                for fk in o["foreignKeys"]:
                    note = f"{', '.join(fk['columns'])} -> {', '.join(fk['referencedColumns'])}"
                    if fk.get("onDelete"):
                        note += f"; ON DELETE {fk['onDelete']}"
                    yield Relationship("references", name, table(fk["references"]), "declared",
                                       note=note, path=path, line=line)
            elif kind == "INDEX":
                note = ("unique on " if o["unique"] else "on ") + ", ".join(o["columns"])
                yield Entity(f"index:{o['name']}", "defined", note, path, line)
                yield Relationship("indexes", f"index:{o['name']}", table(o["table"]), "declared",
                                   note=note, path=path, line=line)
            elif kind == "VIEW":
                name = table(o["name"])
                defined.add(name)
                yield Entity(name, "view", None, path, line)
                for t in o["tables"]:
                    yield Relationship("selects-from", name, table(t), "declared", path=path, line=line)
    for resource in sorted(accessed):
        if resource.startswith("SYS") or resource.split(".")[-1].startswith("SYSDUMMY"):
            continue  # Db2 catalog tables
        if f"db2:{resource}" not in defined and table(resource) not in defined:
            yield Entity(f"db2:{resource}", "no-definition",
                         "accessed by programs; no CREATE TABLE or VIEW in the DDL files")
