# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""GraphWorker against a stand-in for ``server.jar graph`` written in Python."""

import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from mfmap.run import GraphWorker

FAKE = textwrap.dedent('''
    import json, os, sys, time
    print("pid", os.getpid(), file=sys.stderr, flush=True)
    for line in sys.stdin:
        path = line.strip()
        if path.endswith("DIE.cbl"):
            print("java.lang.OutOfMemoryError: Java heap space", file=sys.stderr, flush=True)
            sys.exit(3)
        if path.endswith("SLOW.cbl"):
            time.sleep(5)
        print(json.dumps({"uri": "file:" + path, "pid": os.getpid()}), flush=True)
''')


class WorkerTest(unittest.TestCase):
    def setUp(self):
        directory = Path(tempfile.mkdtemp())
        self.fake = directory / "fake_server.py"
        self.fake.write_text(FAKE)
        self.dir = directory

    def worker(self, timeout=30):
        # The worker runs: <java> <java_options> -jar <jar> graph; the fake ignores its arguments.
        return GraphWorker("unused.jar", java=sys.executable, java_options=[str(self.fake)], timeout=timeout)

    def test_one_process_serves_many_programs_and_is_replaced_after_a_crash(self):
        worker = self.worker()
        self.addCleanup(worker.close)
        first = json.loads(worker.parse(self.dir / "A.cbl"))
        second = json.loads(worker.parse(self.dir / "B.cbl"))
        self.assertEqual(first["pid"], second["pid"])
        self.assertTrue(second["uri"].endswith("/B.cbl"))

        crashed = json.loads(worker.parse(self.dir / "DIE.cbl"))
        self.assertEqual(crashed["crash"], "java.lang.OutOfMemoryError: Java heap space")
        after = json.loads(worker.parse(self.dir / "C.cbl"))
        self.assertNotEqual(after["pid"], first["pid"])

    @unittest.skipIf(os.name == "nt", "timeouts need POSIX pipes")
    def test_timeout_replaces_the_process(self):
        worker = self.worker(timeout=1)
        self.addCleanup(worker.close)
        self.assertEqual(json.loads(worker.parse(self.dir / "SLOW.cbl"))["crash"], "timed out after 1 s")
        self.assertIn("pid", json.loads(worker.parse(self.dir / "A.cbl")))


if __name__ == "__main__":
    unittest.main()
