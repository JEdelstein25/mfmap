# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Find sources and run the parser on them through ``server.jar graph`` worker processes."""

from __future__ import annotations

import json
import os
import select
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Optional, Sequence

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


class GraphWorker:
    """One ``server.jar graph`` process that parses programs one at a time. Java start-up and
    warm-up are paid once per worker instead of once per program. A worker that crashes or times
    out is replaced on the next program."""

    def __init__(self, jar: str | os.PathLike, options: Sequence[str] = (), java: str = "java",
                 java_options: Sequence[str] = ("-Xmx2g",), timeout: int = 900):
        self.command = [java, *java_options, "-jar", str(jar), "graph", *options]
        self.timeout = timeout
        self.process: Optional[subprocess.Popen] = None

    def parse(self, source: Path) -> str:
        """The program's graph output as one line of JSON text."""
        if self.process is None or self.process.poll() is not None:
            self.errors = tempfile.TemporaryFile()
            self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=self.errors,
                                            text=True, encoding="utf-8", bufsize=1)
        line, problem = "", None
        try:
            self.process.stdin.write(str(source.resolve()) + "\n")
            self.process.stdin.flush()
            # select needs POSIX pipes; on Windows the read just waits without a timeout.
            ready = os.name == "nt" or select.select([self.process.stdout], [], [], self.timeout)[0]
            if ready:
                line = self.process.stdout.readline()
            else:
                problem = f"timed out after {self.timeout} s"
        except OSError:
            pass
        if line:
            return line
        if problem is None:
            self.process.wait(timeout=30)
            self.errors.seek(0)
            lines = self.errors.read().decode("utf-8", "replace").strip().splitlines()
            problem = lines[-1] if lines else f"parser exited with code {self.process.returncode}"
        self.close()
        return json.dumps({"uri": source.resolve().as_uri(), "language": "cobol", "crash": problem})

    def close(self) -> None:
        if self.process is not None:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait()
            for stream in (self.process.stdin, self.process.stdout):
                try:
                    stream.close()
                except OSError:
                    pass
            self.process = None


def parse_one(
    jar: str | os.PathLike,
    source: Path,
    target: Path,
    options: Sequence[str] = (),
    worker: Optional[GraphWorker] = None,
) -> str:
    """Parse one source into ``target`` and return the graph as JSON text. A failed run still
    writes a graph, with ``crash`` set to the error. Pass a worker to reuse its Java process. The
    text is written as received, so worker threads do no JSON work."""
    own = worker is None
    worker = worker or GraphWorker(jar, options)
    try:
        text = worker.parse(source)
    finally:
        if own:
            worker.close()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return text


def parser_options(copybook_dirs: Sequence[str | os.PathLike] = (),
                   copybook_extensions: Sequence[str] = ()) -> list[str]:
    options = []
    for d in copybook_dirs:
        options += ["-cf", str(Path(d).resolve())]
    for e in copybook_extensions:
        options += ["-ce", e]
    return options
