# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""The migration plan, ``migration.json``: loading it, and ``mfmap check``.

The file must follow ``schema/migration-v1.schema.json``. ``validate`` checks it against that
schema with a small validator for the keywords the schema uses, so the toolkit needs nothing beyond
Python. ``check`` also checks what a schema cannot: unit IDs are unique, every dependency is on a
unit in an earlier wave, every program is in exactly one unit or excluded, and every endpoint is
one the store knows. It warns when a unit has started before the units it depends on are built.
"""

from __future__ import annotations

import collections
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PLAN = "migration.json"
# A copy of schema/migration-v1.schema.json, so an installed package has it; a test keeps them equal.
SCHEMA = Path(__file__).with_name("migration-v1.schema.json")
ENDPOINT = re.compile(r"^[a-z][a-z0-9-]*:.+$")
STATUSES = ["todo", "building", "built", "verified"]


def schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def validate(value, sch: dict, root: Optional[dict] = None, where: str = "") -> list[str]:
    """Errors from checking ``value`` against a JSON Schema, for the keywords this schema uses."""
    root = root or sch
    if "$ref" in sch:
        target = root
        for part in sch["$ref"].lstrip("#/").split("/"):
            target = target[part]
        return validate(value, {**target, **{k: v for k, v in sch.items() if k != "$ref"}}, root, where)
    at = where or "the file"
    types = {"object": dict, "array": list, "string": str, "boolean": bool}
    kind = sch.get("type")
    if kind == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        return [f"{at}: must be a whole number"]
    if kind in types and not isinstance(value, types[kind]):
        return [f"{at}: must be {'an' if kind[0] in 'aeiou' else 'a'} {kind}"]
    errors = []
    if "const" in sch and value != sch["const"]:
        errors.append(f"{at}: must be {json.dumps(sch['const'])}")
    if "enum" in sch and value not in sch["enum"]:
        errors.append(f"{at}: must be one of {', '.join(json.dumps(e) for e in sch['enum'])}")
    if isinstance(value, str):
        if len(value) < sch.get("minLength", 0):
            errors.append(f"{at}: must not be empty")
        if "pattern" in sch and not re.search(sch["pattern"], value):
            errors.append(f"{at}: {json.dumps(value)} does not match {sch['pattern']}")
    if isinstance(value, int) and "minimum" in sch and value < sch["minimum"]:
        errors.append(f"{at}: must be at least {sch['minimum']}")
    if isinstance(value, dict):
        for key in sch.get("required", []):
            if key not in value:
                errors.append(f"{at}: missing {key}")
        props = sch.get("properties", {})
        for key, item in value.items():
            if key in props:
                errors += validate(item, props[key], root, f"{where}.{key}" if where else key)
            elif sch.get("additionalProperties") is False:
                errors.append(f"{at}: unknown field {key}")
    if isinstance(value, list):
        if len(value) < sch.get("minItems", 0):
            errors.append(f"{at}: needs at least {sch['minItems']} item")
        if sch.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) < len(value):
            errors.append(f"{at}: has duplicates")
        for i, item in enumerate(value):
            errors += validate(item, sch.get("items", {}), root, f"{where}[{i}]")
    return errors


def find(store: Path, root: Optional[str], explicit: Optional[str] = None) -> Optional[Path]:
    """``migration.json`` in the parse root or next to the store, or ``explicit``."""
    for candidate in [explicit, *(Path(base) / PLAN for base in (root, store.parent) if base)]:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


@dataclass
class Result:
    plan: Optional[dict]
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def known_endpoints(conn) -> tuple[set, set]:
    """Endpoints the store knows, and the programs it parsed."""
    programs = {f"program:{r['name']}" for r in conn.execute("SELECT name FROM programs")}
    known = set(programs)
    for r in conn.execute("SELECT entity FROM entities"):
        known.add(r["entity"])
    for r in conn.execute("SELECT source, target FROM relationships"):
        known.add(r["source"])
        if r["target"]:
            known.add(r["target"])
    return known, programs


def check(path: Path, conn=None) -> Result:
    """Validate the plan against the schema, then against itself and the store (``conn``)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return Result(None, [f"cannot read {path.name}: {e}"])
    errors = validate(data, schema())
    if errors:
        return Result(None, errors)
    result = Result(data)
    units = data["units"]
    waves, statuses = {}, {}
    for i, u in enumerate(units):
        if u["id"] in waves:
            result.errors.append(f"units[{i}]: unit ID {u['id']} is used twice")
        waves[u["id"]] = u["wave"]
        statuses[u["id"]] = u.get("status", "todo")
    for u in units:
        for d in u.get("dependencies", []):
            if d["unit"] == u["id"]:
                result.errors.append(f"unit {u['id']}: depends on itself")
            elif d["unit"] not in waves:
                result.errors.append(f"unit {u['id']}: depends on {d['unit']}, which is not a unit")
            elif waves[d["unit"]] >= u["wave"]:
                result.errors.append(f"unit {u['id']} (wave {u['wave']}): depends on {d['unit']}, which is in "
                                     f"wave {waves[d['unit']]}; a dependency must be in an earlier wave")
            elif statuses[u["id"]] != "todo" and STATUSES.index(statuses[d["unit"]]) < STATUSES.index("built"):
                result.warnings.append(f"unit {u['id']} is {statuses[u['id']]}, but it depends on {d['unit']}, "
                                       f"which is {statuses[d['unit']]}")
        for iface in u.get("interfaces", []):
            if iface.get("with") and iface["with"] not in waves:
                result.errors.append(f"unit {u['id']}: interface {iface['name']} is with {iface['with']}, which is not a unit")

    owners = collections.defaultdict(list)
    for u in units:
        for p in u["programs"]:
            owners[p].append(u["id"])
    excluded = {e["program"] for e in data.get("excluded", [])}
    for p, ids in sorted(owners.items()):
        if len(ids) > 1:
            result.errors.append(f"{p} is in more than one unit: {', '.join(ids)}")
        if p in excluded:
            result.errors.append(f"{p} is both in unit {ids[0]} and excluded")

    if conn is None:
        result.warnings.append("no store, so programs and endpoints were not checked against the map")
    else:
        known, programs = known_endpoints(conn)
        for p in sorted(programs - set(owners) - excluded):
            result.errors.append(f"{p} is not in any unit; add it to one or to excluded with a reason")
        for u in units:
            endpoints = [*u["programs"], *u.get("entryPoints", []), *u.get("reads", []), *u.get("writes", []),
                         *(d["on"] for d in u.get("dependencies", [])),
                         *(i["layout"] for i in u.get("interfaces", []) if ENDPOINT.match(i["layout"]))]
            for e in dict.fromkeys(endpoints):
                if e not in known:
                    result.errors.append(f"unit {u['id']}: {e} is not in the map; check the name, or record it "
                                         "with mfmap record if it is real")
        for e in sorted(excluded - programs):
            result.errors.append(f"excluded {e} is not a parsed program")
    for u in units:
        if not (path.parent / "units" / f"{u['id']}.md").is_file():
            result.warnings.append(f"unit {u['id']}: units/{u['id']}.md does not exist yet")
    return result


def report(result: Result, rel=lambda p: p) -> list[str]:
    """The check result as Markdown list items."""
    out = []
    if result.errors:
        out.append(f"**{len(result.errors)} problems** (`mfmap check`):\n")
        out += [f"- {e}" for e in result.errors[:30]]
        if len(result.errors) > 30:
            out.append(f"- and {len(result.errors) - 30} more")
        out.append("")
    if result.warnings:
        out += [f"- _{w}_" for w in result.warnings[:10]] + [""]
    return out
