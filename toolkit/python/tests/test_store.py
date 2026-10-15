# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Store and report tests. The parser is replaced by a copy of fixtures/SAMPLE.json whose
/FIXTURE paths point at a temporary copy of the fixtures, so no Java is needed."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mfmap import questions, resolvers, store
from mfmap.report import add_note, backlog, report, report_markdown
from mfmap.serve import source

FIXTURES = Path(__file__).parent / "fixtures"


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.src = self.tmp / "src"
        shutil.copytree(FIXTURES, self.src)
        self.jar = self.tmp / "server.jar"
        self.jar.write_bytes(b"jar")
        self.store = self.tmp / ".mfmap"
        self.parsed = []

    def fake_parse(self, jar, source, target, options=(), **kwargs):
        self.parsed.append(source.name)
        text = (FIXTURES / "SAMPLE.json").read_text().replace("/FIXTURE", str(self.src))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return text

    def parse(self, *copybook_dirs):
        self.parsed = []
        cwd = os.getcwd()
        os.chdir(self.src)  # the parse root, as when run from the application's repository
        self.addCleanup(os.chdir, cwd)
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
            ("LINK", "SAMPLNK", "literal", 77), ("XCTL", None, "unresolved", 79),
            ("SQL CALL", "CARDDEMO.POST_TRAN", "literal", 88), ("SQL CALL", "SAMPSUB", "value", 91)])
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM access").fetchone()[0], 13)
        self.assertEqual([tuple(c) for c in conn.execute("SELECT kind, line FROM commits ORDER BY line")],
                         [("COMMIT", 96), ("SYNCPOINT ROLLBACK", 97)])
        self.assertEqual([tuple(r) for r in conn.execute("SELECT name, program FROM procedures ORDER BY line")],
                         [("CARDDEMO.POST_TRAN", "POSTTRN"), ("CARDDEMO.SAMPSUB", "SAMPSUB"),
                          ("CARDDEMO.PURGE_AUDIT", None)])
        self.assertEqual(conn.execute("SELECT status FROM runs").fetchone()[0], "finished")

        second = self.parse()
        self.assertEqual(self.parsed, [])
        cached = conn.execute("SELECT cached FROM run_files WHERE run_id = ?", (second,)).fetchone()[0]
        self.assertEqual(cached, 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0], 6)

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

    def test_report_and_source_access(self):
        self.parse()
        add_note(self.store, "Added MQ copybooks; COPAUA0C still fails at app/x.cbl:12.")
        page = report(self.store)
        markdown = page["parser"]
        self.assertEqual(page["run"]["status"], "finished")
        self.assertIn("1 clean, 0 with errors, 0 crashed, 0 reused", markdown)
        self.assertIn("- 1 program (`.cbl` and `.cob` files).", markdown)
        self.assertIn("4 calls between programs: 2 name the program, 1 use a data item's VALUE, "
                      "1 are set at run time (1 with names the program MOVEs into them).", markdown)
        self.assertIn("- SAMPLE XCTL `WS-NEXT-PGM` at SAMPLE.cbl:79, maybe SAMPNXT", markdown)
        self.assertIn("- 2 stored procedure calls (EXEC SQL CALL) to 2 procedures.", markdown)
        self.assertIn("- **CARDDEMO.POST_TRAN**, called by SAMPLE (SAMPLE.cbl:88): COBOL, program POSTTRN, "
                      "2 parameters, defined at ddl/PROCS.sql:2", markdown)
        self.assertIn("- Defined but not called from COBOL: CARDDEMO.PURGE_AUDIT (ddl/PROCS.sql:14)", markdown)
        self.assertIn("- SAMPLE PREPARE from `WS-CUST-NAME` at SAMPLE.cbl:93; SQL text: "
                      "`DELETE FROM CARDDEMO.TEMP_TRAN`", markdown)
        self.assertIn("- 2 commit and rollback points in 1 program: COMMIT 1, SYNCPOINT ROLLBACK 1.", markdown)
        self.assertIn("Copybooks found in folders: `cpy` (1)", markdown)
        self.assertIn("COPAUA0C still fails", page["notes"])
        self.assertIn("_Not ready.", backlog(self.store))

        (self.src / "migration.json").write_text(json.dumps({"units": [
            {"id": "U2", "name": "Later", "wave": 2, "dependsOn": ["U1"]},
            {"id": "U1", "name": "First", "wave": 1, "programs": ["SAMPLE"]}]}))
        spec = json.loads((self.src / "migration.json").read_text())
        spec["units"][1]["interfaces"] = [{"name": "ACCT-REC", "layout": "CVACT01Y"}]
        spec["units"][1]["acceptanceChecks"] = ["Balances match the batch report for every account"]
        spec["units"][1]["writes"] = []
        (self.src / "migration.json").write_text(json.dumps(spec))
        (self.src / "units").mkdir()
        (self.src / "units" / "U1.md").write_text("# Business Rules\n\n- Rejects a zero amount at SAMPLE.cbl:40.\n")
        full = backlog(self.store, str(self.src / "migration.json"))
        self.assertLess(full.index("### U1 First"), full.index("### U2 Later"))
        self.assertIn("- **Programs:** SAMPLE", full)
        self.assertIn("- **Interfaces:**\n  - Name: ACCT-REC; Layout: CVACT01Y", full)
        self.assertIn("- **Acceptance checks:**\n  - Balances match the batch report for every account", full)
        self.assertNotIn("Writes", full)
        self.assertIn("#### Business Rules", full)
        self.assertIn("Rejects a zero amount at SAMPLE.cbl:40.", full)
        self.assertNotIn("Rejects a zero amount", full[full.index("### U2 Later"):])

        source_file = str(self.src / "SAMPLE.cbl")
        self.assertEqual(source(self.store, source_file, 40)["lines"][12].strip(),
                         "CALL 'SAMPUTIL' USING WS-AMOUNT")
        self.assertIsNotNone(source(self.store, str(self.src / "cpy" / "SAMPREC.cpy"), 1))
        self.assertIsNone(source(self.store, str(self.jar), 1))

    def test_resolvers_connect_transactions_screens_jobs_and_datasets(self):
        self.parse()  # runs every resolver at the end
        resolvers.record(self.store, "business-logic", "paragraph:SAMPLE.1000-READ",
                         note="Copies each account to the report", evidence=f"{self.src}/SAMPLE.cbl:46")
        resolvers.run(self.store)  # running again keeps what the agent recorded
        conn = self.db()
        rows = {(r["kind"], r["source"], r["target"]) for r in conn.execute("SELECT * FROM relationships")}
        for expected in [
            ("starts", "transaction:SAMP", "program:SAMPLE"),
            ("sends", "program:SAMPLE", "screen:SAMPSET.SAMPMAP"),
            ("returns-to", "program:SAMPLE", "transaction:SAMP"),
            # The program runs through TSO batch; its SYSTSIN comes after the DDs it uses.
            ("runs", "job:SAMPJOB", "program:SAMPLE"),
            ("runs", "job:SAMPJOB", "proc:SAMPPROC"),
            # SELECT ... ASSIGN names matched to the DD statements of the step that runs the program.
            ("read", "program:SAMPLE", "dataset:PROD.SAMPLE.ACCOUNTS"),
            ("write", "program:SAMPLE", "dataset:PROD.SAMPLE.REPORT(+1)"),
            ("performs", "paragraph:SAMPLE.0000-MAIN", "paragraph:SAMPLE.1000-READ"),
            ("calls", "program:SAMPLE", "program:SAMPUTIL"),
            ("transfers", "program:SAMPLE", None),
            ("includes", "program:SAMPLE", "copybook:SAMPREC"),
        ]:
            self.assertIn(expected, rows)
        self.assertNotIn(("runs", "job:SAMPJOB", "program:IKJEFT01"), rows)
        entities = {(e["entity"], e["kind"], e["note"]) for e in conn.execute("SELECT * FROM entities")}
        self.assertIn(("transaction:SAMP", "defined", "SAMPLE ACCOUNT INQUIRY"), entities)
        self.assertIn(("screen:SAMPSET.SAMPMAP", "defined", None), entities)
        self.assertIn(("job:SAMPJOB", "defined", None), entities)
        self.assertIn(("paragraph:SAMPLE.1000-READ", "business-logic", "Copies each account to the report"),
                      entities)
        self.assertIn("## Relationships", report(self.store)["parser"])

    def test_questions_open_first_and_answers_reopen(self):
        self.parse()
        first = questions.ask(self.store, "Does LEDREB still run nightly?", found="CALL at SAMPLE.cbl:40",
                              default="Yes; it moves with the ledger unit", affects="Which wave owns it")
        questions.ask(self.store, "Is the GL export still used?")
        questions.answer(self.store, first["id"].lower(), "No, retired in 2019", "page")

        stored = report(self.store)["questions"]
        self.assertEqual([q["id"] for q in stored], ["Q1", "Q2"])
        self.assertEqual((stored[0]["answer"], stored[0]["by"]), ("No, retired in 2019", "page"))
        markdown = report_markdown(report(self.store))
        # Open questions come before answered ones, whatever order they were asked in.
        self.assertLess(markdown.index("**Q2**"), markdown.index("**Q1**"))
        self.assertIn("1 open, 1 answered.", markdown)
        self.assertIn("  - Answer: No, retired in 2019", markdown)

        questions.answer(self.store, "Q1", "  ", "agent")
        self.assertIsNone(questions.load(self.store)[0]["answer"])
        self.assertEqual(questions.ask(self.store, "Third?")["id"], "Q3")
        with self.assertRaises(KeyError):
            questions.answer(self.store, "Q9", "x", "agent")


if __name__ == "__main__":
    unittest.main()
