# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Find sources and run ``server.jar analysis --graph`` on one of them."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Iterable, Sequence

SOURCE_EXTENSIONS = (".cbl", ".cob")


def find_sources(paths: Iterable[str | os.PathLike], extensions=SOURCE_EXTENSIONS) -> list[Path]:
    """Files under ``paths`` whose extension matches, case-insensitively, sorted."""
    found = []
    for path in map(Path, paths):
        candidates = [path] if path.is_file() else (p for p in path.rglob("*") if p.is_file())
        found += [p for p in candidates if p.suffix.lower() in extensions]
    return sorted(set(found))


def output_names(sources: Sequence[Path]) -> dict[Path, str]:
    """``PROGRAM.json``; sources sharing a stem also get their parent folders' names."""
    names: dict[Path, str] = {}
    for source in sources:
        stem, parts = source.stem, list(source.parent.parts)
        name = stem
        while name + ".json" in names.values() and parts:
            name = f"{name}@{parts.pop()}"
        names[source] = name + ".json"
    return names


def parse_one(
    jar: str | os.PathLike,
    source: Path,
    target: Path,
    options: Sequence[str] = (),
    java: str = "java",
    java_options: Sequence[str] = (),
    timeout: int = 900,
) -> dict:
    """Parse one source into ``target`` and return the graph. A failed run still writes a graph,
    with ``crash`` set to the error."""
    command = [java, *java_options, "-jar", str(jar), "analysis", "-s", str(source.resolve()),
               "--graph", *options]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        stdout, stderr = done.stdout, done.stderr
    except subprocess.TimeoutExpired:
        stdout, stderr = "", f"timed out after {timeout} s"
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        data = {"uri": source.resolve().as_uri(), "language": "cobol",
                "crash": (stderr.strip().splitlines() or ["no output"])[-1]}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data), encoding="utf-8")
    return data


def parser_options(copybook_dirs: Sequence[str | os.PathLike] = (),
                   copybook_extensions: Sequence[str] = ()) -> list[str]:
    options = []
    for d in copybook_dirs:
        options += ["-cf", str(Path(d).resolve())]
    for e in copybook_extensions:
        options += ["-ce", e]
    return options
