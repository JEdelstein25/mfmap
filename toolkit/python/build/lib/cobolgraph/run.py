# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Run ``server.jar analysis --graph`` over a source tree, one JVM per program, in parallel."""

from __future__ import annotations

import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

SOURCE_EXTENSIONS = (".cbl", ".cob")


@dataclass(frozen=True)
class ParseResult:
    source: Path
    output: Path
    ok: bool
    message: str = ""


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


def parse(
    jar: str | os.PathLike,
    sources: Sequence[Path],
    out_dir: str | os.PathLike,
    copybook_dirs: Sequence[str | os.PathLike] = (),
    copybook_extensions: Sequence[str] = (),
    jobs: int = 4,
    java: str = "java",
    java_options: Sequence[str] = (),
    timeout: int = 900,
) -> list[ParseResult]:
    """Parse each source into ``out_dir``. A failed run writes a graph file with ``crash`` set."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    options = []
    for d in copybook_dirs:
        options += ["-cf", str(Path(d).resolve())]
    for e in copybook_extensions:
        options += ["-ce", e]
    names = output_names(sources)

    def run(source: Path) -> ParseResult:
        target = out / names[source]
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
        target.write_text(json.dumps(data), encoding="utf-8")
        return ParseResult(source, target, "crash" not in data, data.get("crash", ""))

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        return list(pool.map(run, sources))
