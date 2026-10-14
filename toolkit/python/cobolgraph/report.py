# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""The Notes page as Markdown: what the parser read and found, the agent's notes,
and the backlog once ``migration-spec.json`` has one. ``cobolgraph serve`` shows it; ``cobolgraph
report`` prints it."""

from __future__ import annotations

import collections
import json
import os
import re
import time
from pathlib import Path
from typing import Optional

from .store import connect, latest_files

NOTES = "notes.md"


def add_note(store: str | os.PathLike, text: str) -> Path:
    """Append a timestamped entry to ``<store>/notes.md``."""
    path = Path(store) / NOTES
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n### {time.strftime('%Y-%m-%d %H:%M')}\n\n{text.strip()}\n")
    return path


def plural(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


def spec_path(store: Path, root: str, spec: Optional[str]) -> Optional[Path]:
    for candidate in [spec, Path(root) / "migration-spec.json", store.parent / "migration-spec.json"]:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def report(store: str | os.PathLike, spec: Optional[str] = None) -> tuple[str, dict]:
    """The page as Markdown, and the latest run's status."""
    store = Path(store).resolve()
    conn = connect(store)
    try:
        run = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        root = run["root"] if run else str(store.parent)
        rel = lambda p: os.path.relpath(p, root) if p else "?"  # noqa: E731
        files = latest_files(conn)
        current = {f["path"] for f in files}
        status = collections.Counter(f["status"] for f in files)
        out = [f"# Notes\n\n`{root}`\n"]
        if not run:
            out.append("No parse has run yet. Run `cobolgraph parse` to start.\n")
        else:
            done = sum(status[s] for s in ("clean", "errors", "crash"))
            reused = conn.execute("SELECT COUNT(*) FROM run_files WHERE run_id = ? AND cached = 1",
                                  (run["id"],)).fetchone()[0]
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(run["finished"] or run["started"]))
            state = f"parsing, {done} of {len(files)} done" if run["status"] == "running" \
                else f"finished {when}"
            out.append(f"Run {run['id']}, {state}: {status['clean']} clean, {status['errors']} with "
                       f"errors, {status['crash']} crashed, {reused} reused from the previous run.\n")
            out += parser_sections(conn, files, current, rel)
    finally:
        conn.close()

    notes = store / NOTES
    out.append("## Agent Notes\n")
    out.append(notes.read_text(encoding="utf-8").strip() + "\n" if notes.is_file() else
               "_No notes yet. Add one with `cobolgraph note \"...\"` or edit "
               f"`{rel(str(notes))}`._\n")
    out += backlog_section(spec_path(store, root, spec), rel)
    return "\n".join(out), {"run": dict(run) if run else None, "root": root}


def parser_sections(conn, files, current, rel) -> list[str]:
    out = []
    folders, built_in, missing = collections.Counter(), set(), set()
    missing_names = {(d["message"] or "").split(":")[0] for d in conn.execute(
        "SELECT message FROM diagnostics WHERE code = 'missing copybook'")}
    for f in files:
        for name, path in json.loads(f["copies"] or "{}").items():
            if path:
                folders[rel(os.path.dirname(path))] += 1
            elif name in missing_names:
                missing.add(name)
            else:
                built_in.add(name)
    out.append("## Inputs\n")
    out.append(f"- {plural(len(files), 'program')} (`.cbl` and `.cob` files).")
    out.append("- Copybooks found in folders: " + ", ".join(
        f"`{d}` ({n})" for d, n in folders.most_common()) if folders else "- No copybooks found in folders.")
    if built_in:
        out.append("- Supplied by the parser: " + ", ".join(f"`{n}`" for n in sorted(built_in)) +
                   " (stand-ins or built-in definitions).")
    out.append("- Not found: " + ", ".join(f"`{n}`" for n in sorted(missing)) if missing
               else "- Every copybook was found.")

    errors = [d for d in conn.execute("SELECT * FROM diagnostics WHERE severity = 'ERROR'")
              if d["file"] in current]
    out.append("\n## Parse Errors\n")
    if not errors:
        out.append("None.")
    by_cause = collections.defaultdict(list)
    for d in errors:
        by_cause[d["message"] or d["code"] or "?"].append(d)
    for cause, ds in sorted(by_cause.items(), key=lambda kv: -len(kv[1]))[:15]:
        where = ", ".join(f"{rel(d['path'])}:{d['line']}" for d in ds[:3])
        more = f" and {len(ds) - 3} more" if len(ds) > 3 else ""
        out.append(f"- **{cause}** ×{len(ds)}: {where}{more}")
    for f in files:
        if f["status"] == "crash":
            out.append(f"- **Crashed:** {rel(f['path'])}: {f['message']}")

    def count(sql, *args):
        return conn.execute(sql, args).fetchall()

    calls = [c for c in count("SELECT * FROM calls") if c["file"] in current]
    access = [a for a in count("SELECT * FROM access") if a["file"] in current]
    out.append("\n## What the Parser Found\n")
    programs = [p for p in count("SELECT * FROM programs") if p["file"] in current]
    out.append(f"- {sum(p['paragraphs'] for p in programs):,} paragraphs, "
               f"{sum(p['statements'] for p in programs):,} statements and "
               f"{sum(p['data_items'] for p in programs):,} data items.")
    resolved = collections.Counter(c["resolved"] for c in calls)
    with_candidates = sum(1 for c in calls if c["resolved"] == "unresolved" and json.loads(c["candidates"]))
    out.append(f"- {len(calls)} calls between programs: {resolved['literal']} name the program, "
               f"{resolved['value']} use a data item's VALUE, {resolved['unresolved']} are set at run "
               f"time ({with_candidates} with names the program MOVEs into them).")
    stores = collections.Counter(a["store"] for a in access)
    out.append(f"- {len(access)} reads and writes of stored data: " + ", ".join(
        f"{stores[s]} {s} ({plural(len({a['resource'] for a in access if a['store'] == s}), 'resource')})"
        for s in sorted(stores)) + ".")
    unresolved = [c for c in calls if c["resolved"] == "unresolved"]
    if unresolved:
        out.append("\n### Calls Set at Run Time\n")
        for c in unresolved[:12]:
            maybe = json.loads(c["candidates"])
            out.append(f"- {c['program']} {c['via']} `{c['expression']}` at {rel(c['path'])}:{c['line']}"
                       + (f", maybe {', '.join(maybe)}" if maybe else ""))
        if len(unresolved) > 12:
            out.append(f"- and {len(unresolved) - 12} more")

    checks = count("SELECT * FROM checks WHERE run_id = (SELECT MAX(run_id) FROM checks)")
    if checks:
        out.append("\n## Count Check\n")
        out.append("Statement counts from the graph compared with a text scan that does not use the parser:\n")
        for c in checks:
            diff = json.loads(c["differences"] or "{}")
            note = "match" if c["text"] == c["graph"] else "differ in " + ", ".join(
                f"{p} ({t} vs {g})" for p, (t, g) in diff.items())
            out.append(f"- {c['kind']}: text {c['text']:,}, graph {c['graph']:,}, {note}.")
    return out + [""]


def pick(obj, *keys):
    """The value of the first key in ``obj`` that matches one of ``keys`` ignoring case, ``_`` and
    ``-``, since the agent chooses the exact field names in migration-spec.json."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower().replace("_", "").replace("-", "") in keys:
                return value
    return None


def name(value) -> str:
    if isinstance(value, dict):
        return str(pick(value, "id", "name", "unit", "resource", "program") or json.dumps(value))
    return str(value)


def load_spec(path: Optional[Path], rel) -> tuple[Optional[dict], Optional[str]]:
    """The spec, or a Markdown line saying why there is no backlog yet."""
    if not path:
        return None, "_Not ready. It appears here once `migration-spec.json` has units._\n"
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return None, f"Could not read `{rel(str(path))}`: {e}\n"
    if not pick(spec, "units", "backlog"):
        return None, f"_Not ready. `{rel(str(path))}` has no units yet._\n"
    return spec, None


def by_wave(units: list) -> list[tuple[str, list]]:
    waves = collections.defaultdict(list)
    for u in units:
        waves[pick(u, "wave", "wavenumber") or "unassigned"].append(u)
    order = sorted(waves, key=lambda w: (not str(w).isdigit(), int(w) if str(w).isdigit() else 0, str(w)))
    return [(f"Wave {w}" if str(w).isdigit() else str(w), waves[w]) for w in order]


def questions_section(spec: dict) -> list[str]:
    questions = pick(spec, "openquestions", "questions") or []
    if not questions:
        return []
    out = ["### Open Questions\n"]
    for q in questions:
        text = q if isinstance(q, str) else pick(q, "question", "text") or json.dumps(q)
        default = pick(q, "default", "defaultassumption") if isinstance(q, dict) else None
        out.append(f"- {text}" + (f" _Default: {default}_" if default else ""))
    return out + [""]


def backlog_section(path: Optional[Path], rel) -> list[str]:
    out = ["\n## Backlog\n"]
    spec, missing = load_spec(path, rel)
    if missing:
        return out + [missing]
    units = pick(spec, "units", "backlog")
    out.append(f"{len(units)} units from `{rel(str(path))}`. The Backlog tab "
               "(`cobolgraph backlog`) has every unit in full.\n")
    for wave, members in by_wave(units):
        out.append(f"### {wave}\n")
        for u in members:
            line = f"- **{name(u)}** {pick(u, 'name', 'title') or ''}".rstrip()
            for label, keys in (("programs", ("programs",)), ("depends on", ("dependencies", "dependson"))):
                values = pick(u, *keys)
                if values:
                    line += f"; {label}: " + ", ".join(name(v) for v in values)
            out.append(line)
        out.append("")
    return out + questions_section(spec)


def label(key: str) -> str:
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", key).replace("_", " ").replace("-", " ")
    return words[:1].upper() + words[1:].lower()


def field(key: str, value, indent: str = "") -> list[str]:
    """A unit field as Markdown list items: short lists on one line, longer ones and objects
    nested one level. Empty fields are left out."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return [f"{indent}- **{label(key)}:** {value}"]
    if value in ([], {}, ""):
        return []
    if isinstance(value, list) and all(not isinstance(v, (dict, list)) and len(str(v)) <= 40 for v in value):
        return [f"{indent}- **{label(key)}:** " + ", ".join(str(v) for v in value)]
    out = [f"{indent}- **{label(key)}:**"]
    items = value.items() if isinstance(value, dict) else enumerate(value)
    for k, v in items:
        if isinstance(v, dict):
            text = "; ".join(f"{label(a)}: {b if not isinstance(b, (dict, list)) else json.dumps(b)}"
                             for a, b in v.items())
        elif isinstance(v, list):
            text = ", ".join(str(x) for x in v)
        else:
            text = str(v)
        out.append(f"{indent}  - " + (f"**{label(k)}:** {text}" if isinstance(k, str) else text))
    return out


def backlog(store: str | os.PathLike, spec: Optional[str] = None) -> str:
    """Every unit in migration-spec.json with all of its fields and its units/<ID>.md file."""
    store = Path(store).resolve()
    conn = connect(store)
    try:
        run = conn.execute("SELECT root FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    root = run["root"] if run else str(store.parent)
    rel = lambda p: os.path.relpath(p, root)  # noqa: E731
    path = spec_path(store, root, spec)
    out = ["# Backlog\n"]
    data, missing = load_spec(path, rel)
    if missing:
        return "\n".join(out + [missing])
    units = pick(data, "units", "backlog")
    out.append(f"{len(units)} units from `{rel(str(path))}`, in build order.\n")
    for wave, members in by_wave(units):
        out.append(f"## {wave}\n")
        for u in members:
            unit_id = name(u)
            out.append(f"### {unit_id} {pick(u, 'name', 'title') or ''}".rstrip() + "\n")
            if isinstance(u, dict):
                for key, value in u.items():
                    if key.lower() not in ("id", "name", "title", "wave"):
                        out += field(key, value)
            notes = path.parent / "units" / f"{unit_id}.md"
            if notes.is_file():
                out.append(f"\nFrom `{rel(str(notes))}`:\n")
                for line in notes.read_text(encoding="utf-8").splitlines():
                    out.append(re.sub(r"^#{1,6} ", "#### ", line))
            out.append("")
    return "\n".join(out + questions_section(data))
