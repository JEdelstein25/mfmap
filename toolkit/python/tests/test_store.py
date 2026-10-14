# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Store and dashboard tests. The parser is replaced by a copy of fixtures/SAMPLE.json whose
/FIXTURE paths point at a temporary copy of the fixtures, so no Java is needed."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cobolgraph import store
from cobolgraph.serve import Dashboard

FIXTURES = Path(__file__).parent / "fixtures"


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.src = self.tmp / "src"
        shutil.copytree(FIXTURES, self.src)
        self.jar = self.tmp / "server.jar"
        self.jar.write_bytes(b"jar")
        self.store = self.tmp / ".cobolgraph"
        self.parsed = []

    def fake_parse(self, jar, source, target, options=(), **kwargs):
        self.parsed.append(source.name)
        text = (FIXTURES / "SAMPLE.json").read_text().replace("/FIXTURE", str(self.src))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return json.loads(text)

    def parse(self, *copybook_dirs):
        self.parsed = []
        with mock.patch.object(store, "parse_one", self.fake_parse):
            return store.parse(self.store, self.jar, [self.src / "SAMPLE.cbl"],
                               copybook_dirs or [self.src / "cpy"], jobs=1)

    def db(self):
        conn = store.connect(self.store)
        self.addCleanup(conn.close)
        return conn

    def test_records_results_and_reuses_unchanged_files(self):
        first = self.parse()
        conn = self.db()
        row = conn.execute("SELECT status, errors, run_id FROM files").fetchone()
        self.assertEqual(tuple(row), ("clean", 0, first))
        self.assertEqual(conn.execute("SELECT name FROM programs").fetchall()[0][0], "SAMPLE")
        calls = conn.execute("SELECT via, target, resolved, line FROM calls ORDER BY line").fetchall()
        self.assertEqual([tuple(c) for c in calls], [
            ("CALL", "SAMPUTIL", "literal", 40), ("CALL", "SAMPSUB", "value", 41),
            ("LINK", "SAMPLNK", "literal", 77), ("XCTL", None, "unresolved", 79)])
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM access").fetchone()[0], 11)
        self.assertEqual(conn.execute("SELECT status FROM runs").fetchone()[0], "finished")

        second = self.parse()
        self.assertEqual(self.parsed, [])
        cached = conn.execute("SELECT cached FROM run_files WHERE run_id = ?", (second,)).fetchone()[0]
        self.assertEqual(cached, 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0], 4)

    def test_changed_copybook_or_folder_order_reparses(self):
        self.parse()
        with open(self.src / "cpy" / "SAMPREC.cpy", "a") as f:
            f.write("      * changed\n")
        self.parse()
        self.assertEqual(self.parsed, ["SAMPLE.cbl"])

        earlier = self.tmp / "override"
        earlier.mkdir()
        (earlier / "SAMPREC.cpy").write_text("       01 OTHER PIC X.\n")
        self.parse(earlier, self.src / "cpy")  # SAMPREC now resolves to another file
        self.assertEqual(self.parsed, ["SAMPLE.cbl"])

    def test_dashboard_state_and_source_access(self):
        self.parse()
        dashboard = Dashboard(self.store)
        state = dashboard.state()
        self.assertEqual([p["name"] for p in state["programs"]], ["SAMPLE"])
        self.assertEqual(state["files"][0]["status"], "clean")
        self.assertIn(("ims", "PAUTSUM0"), {(a["store"], a["resource"]) for a in state["access"]})
        self.assertEqual(len(state["checks"]), 5)
        program = dashboard.program("SAMPLE")
        self.assertIn("1000-READ", [p["name"] for p in program["paragraphs"]])
        source = str(self.src / "SAMPLE.cbl")
        self.assertEqual(dashboard.source(source, 40)["lines"][12].strip(), "CALL 'SAMPUTIL' USING WS-AMOUNT")
        self.assertIsNotNone(dashboard.source(str(self.src / "cpy" / "SAMPREC.cpy"), 1))
        self.assertIsNone(dashboard.source(str(self.jar), 1))


if __name__ == "__main__":
    unittest.main()
