# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Download IBM MQ's COBOL copybooks from IBM's public MQ redistributable client.

The copybooks are IBM's, under IBM's license; they are not part of this project. ``fetch`` writes
them with IBM's license files into a folder for the parser's ``-cf`` option.
"""

from __future__ import annotations

import re
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

REDIST_URL = "https://public.dhe.ibm.com/ibmdl/export/pub/software/websphere/messaging/mqdev/redist/"
PACKAGE = "{version}-IBM-MQC-Redist-LinuxX64.tar.gz"
COPYBOOKS = "inc/cobcpy64/"
LICENSES = re.compile(r"lap/licenses/(Developer|Production)/(LA|LI)_en$")


def latest_version() -> str:
    with urllib.request.urlopen(REDIST_URL, timeout=60) as response:
        index = response.read().decode("utf-8", "replace")
    versions = set(re.findall(r"(\d+\.\d+\.\d+\.\d+)-IBM-MQC-Redist-LinuxX64\.tar\.gz", index))
    if not versions:
        raise RuntimeError(f"no MQ redistributable client found at {REDIST_URL}")
    return max(versions, key=lambda v: tuple(map(int, v.split("."))))


def fetch(out_dir: str | Path, version: Optional[str] = None) -> tuple[str, list[Path]]:
    """Write the 64-bit COBOL copybooks as ``<NAME>.cpy`` and IBM's English license files to
    ``out_dir/licenses``. Returns the MQ version and the copybook paths."""
    version = version or latest_version()
    url = REDIST_URL + PACKAGE.format(version=version)
    out = Path(out_dir)
    (out / "licenses").mkdir(parents=True, exist_ok=True)
    copybooks = []
    with tempfile.TemporaryFile() as archive:
        with urllib.request.urlopen(url, timeout=600) as response:
            shutil.copyfileobj(response, archive)
        archive.seek(0)
        with tarfile.open(fileobj=archive, mode="r:gz") as tar:
            for member in tar:
                if not member.isfile():
                    continue
                if member.name.startswith(COPYBOOKS):
                    target = out / (Path(member.name).name + ".cpy")
                    copybooks.append(target)
                else:
                    match = LICENSES.match(member.name)
                    if not match:
                        continue
                    target = out / "licenses" / f"{match.group(1)}-{match.group(2)}_en"
                target.write_bytes(tar.extractfile(member).read())
    (out / "SOURCE.txt").write_text(
        f"IBM MQ {version} COBOL copybooks (inc/cobcpy64) from {url}\n"
        "These files are IBM's and are licensed under the IBM MQ license terms in licenses/.\n"
        "They are not part of mfmap and are not covered by the EPL.\n",
        encoding="utf-8",
    )
    return version, sorted(copybooks)
