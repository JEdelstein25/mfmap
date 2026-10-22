# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Store and report tests. The parser is replaced by a copy of fixtures/SAMPLE.json whose
/FIXTURE paths point at a temporary copy of the fixtures, so no Java is needed."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mfmap import plan, questions, resolvers, store
from mfmap.__main__ import main
from mfmap.run import find_sources
from mfmap.report import add_note, backlog, report, report_markdown
from mfmap.serve import source

FIXTURES = Path(__file__).parent / "fixtures"


class StoreTest(unittest.TestCase):
    def setUp(self):
        # Resolved, because on macOS the temporary folder is a symlink and the store resolves paths.
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.src = self.tmp / "src"
        shutil.copytree(FIXTURES, self.src, ignore=shutil.ignore_patterns("DLICALL.*"))
        self.jar = self.tmp / "server.jar"
        self.jar.write_bytes(b"jar")
        self.store = self.tmp / ".mfmap"
        self.parsed = []

    def fake_parse(self, jar, source, target, options=(), **kwargs):
        self.parsed.append(source.name)
        graph = FIXTURES / f"{Path(source).stem}.json"
        text = (graph if graph.is_file() else FIXTURES / "SAMPLE.json").read_text().replace("/FIXTURE", str(self.src))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return text

    def fake_read_ddl(self, jar, files):
        """The parser's ddl output for the fixtures (DDL.jsonl), for the files mfmap chose."""
        self.ddl_files = [Path(f).relative_to(self.src).as_posix() for f in files]
        lines = (FIXTURES / "DDL.jsonl").read_text().replace("/FIXTURE", str(self.src)).splitlines()
        by_path = {json.loads(line)["uri"].removeprefix("file:"): line for line in lines}
        return [(str(f), by_path[str(f)]) for f in files if str(f) in by_path]

    def parse(self, *copybook_dirs, programs=("SAMPLE",)):
        self.parsed = []
        cwd = os.getcwd()
        os.chdir(self.src)  # the parse root, as when run from the application's repository
        self.addCleanup(os.chdir, cwd)
        with mock.patch.object(store, "parse_one", self.fake_parse), \
                mock.patch.object(store, "read_ddl", self.fake_read_ddl):
            return store.parse(self.store, self.jar, [self.src / f"{name}.cbl" for name in programs],
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
            ("SQL CALL", "BANK.POST_TRAN", "literal", 88), ("SQL CALL", "SAMPSUB", "value", 91)])
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM access").fetchone()[0], 13)
        self.assertEqual([tuple(c) for c in conn.execute("SELECT kind, line FROM commits ORDER BY line")],
                         [("COMMIT", 96), ("SYNCPOINT ROLLBACK", 97)])
        self.assertEqual([tuple(r) for r in conn.execute("SELECT name, program FROM procedures ORDER BY line")],
                         [("BANK.POST_TRAN", "POSTTRN"), ("BANK.SAMPSUB", "SAMPSUB"),
                          ("BANK.PURGE_AUDIT", None)])
        self.assertEqual(conn.execute("SELECT status FROM runs").fetchone()[0], "finished")

        second = self.parse()
        self.assertEqual(self.parsed, [])
        cached = conn.execute("SELECT cached FROM run_files WHERE run_id = ?", (second,)).fetchone()[0]
        self.assertEqual(cached, 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0], 6)

    def test_facts_and_crosscheck_read_a_store(self):
        self.parse()
        def run(*command):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                main(list(command))
            return out.getvalue()

        facts = json.loads(run("facts", str(self.store), "--root", str(self.src)))
        self.assertIn("SAMPLE", [p["name"] for p in facts["programs"]])
        self.assertIn("relationships", facts)
        self.assertRegex(run("crosscheck", str(self.store), "-cf", str(self.src / "cpy")), r"(?m)^CALL\s+\d+\s+\d+$")
        # Without -cf, crosscheck expands COPY from the folders the parse used: a PERFORM added to
        # the copybook after the parse shows up as a text-only difference.
        with open(self.src / "cpy" / "SAMPREC.cpy", "a") as f:
            f.write("           PERFORM 1000-READ\n")
        self.assertIn("PERFORM text", run("crosscheck", str(self.store)))

    def test_programs_sharing_a_program_id_are_both_kept(self):
        # Every fake parse returns PROGRAM-ID SAMPLE, so SAMPCOPY.cbl copies it under another file name.
        shutil.copy(self.src / "SAMPLE.cbl", self.src / "SAMPCOPY.cbl")

        cwd = os.getcwd()
        os.chdir(self.src)
        self.addCleanup(os.chdir, cwd)

        def parse(*names):
            with mock.patch.object(store, "parse_one", self.fake_parse), \
                    mock.patch.object(store, "read_ddl", self.fake_read_ddl):
                store.parse(self.store, self.jar, [self.src / n for n in names], [self.src / "cpy"], jobs=1)
            conn = self.db()
            rows = {(Path(r["file"]).name, r["name"]) for r in conn.execute("SELECT file, name FROM programs")}
            callers = {(Path(r["file"]).name, r["program"]) for r in conn.execute("SELECT file, program FROM calls")}
            notes = {(r["entity"], r["kind"]) for r in conn.execute("SELECT entity, kind FROM entities")}
            return rows, callers, notes, store.load_project(self.store).programs

        rows, callers, notes, programs = parse("SAMPLE.cbl", "SAMPCOPY.cbl")
        self.assertEqual(rows, {("SAMPLE.cbl", "SAMPLE"), ("SAMPCOPY.cbl", "SAMPCOPY")})
        self.assertEqual(callers, rows)
        self.assertEqual(sorted(programs), ["SAMPCOPY", "SAMPLE"])
        self.assertIn(("program:SAMPCOPY", "duplicate-program-id"), notes)
        self.assertIn("**SAMPCOPY** (`SAMPCOPY.cbl`): PROGRAM-ID SAMPLE is also in another file",
                      report(self.store)["parser"])

        # Alone, the copy takes its PROGRAM-ID again, and its file name is flagged instead.
        rows, callers, notes, programs = parse("SAMPCOPY.cbl")
        self.assertIn(("SAMPCOPY.cbl", "SAMPLE"), rows)
        self.assertIn(("SAMPCOPY.cbl", "SAMPLE"), callers)
        self.assertEqual(sorted(programs), ["SAMPLE"])
        self.assertIn(("program:SAMPLE", "program-id-differs-from-file"), notes)
        self.assertNotIn(("program:SAMPCOPY", "duplicate-program-id"), notes)

    def test_finds_named_files_and_members_without_extensions(self):
        members = self.tmp / "members"
        (members / ".old").mkdir(parents=True)
        for name in ("PPCAL215", "PPDRV215", "README.txt", ".old/PPCAL200"):
            (members / name).write_text("")
        self.assertEqual([p.name for p in find_sources([members])], [])
        self.assertEqual([p.name for p in find_sources([members], [""])], ["PPCAL215", "PPDRV215"])
        self.assertEqual([p.name for p in find_sources([members / "PPCAL215"])], ["PPCAL215"])
        self.assertEqual([p.name for p in find_sources([self.src])],
                         ["MQCALL.cbl", "ONLINE.cbl", "SAMPLE.cbl", "SAMPUTIL.cbl"])

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
        add_note(self.store, "Added MQ copybooks; ACCTUPD still fails at app/x.cbl:12.")
        page = report(self.store)
        markdown = page["parser"]
        self.assertEqual(page["run"]["status"], "finished")
        self.assertIn("1 clean, 0 with errors, 0 crashed, 0 reused", markdown)
        self.assertIn("- 1 program (`.cbl` and `.cob` files).", markdown)
        self.assertIn("4 calls between programs: 2 name the program, 1 use a data item's VALUE, "
                      "1 are set at run time (1 with names the program MOVEs into them).", markdown)
        self.assertIn("- SAMPLE XCTL `WS-NEXT-PGM` at SAMPLE.cbl:79, maybe SAMPNXT", markdown)
        self.assertIn("- 2 stored procedure calls (EXEC SQL CALL) to 2 procedures.", markdown)
        self.assertIn("- **BANK.POST_TRAN**, called by SAMPLE (SAMPLE.cbl:88): COBOL, program POSTTRN, "
                      "2 parameters, defined at ddl/PROCS.sql:2", markdown)
        self.assertIn("- Defined but not called from COBOL: BANK.PURGE_AUDIT (ddl/PROCS.sql:14)", markdown)
        self.assertIn("- SAMPLE PREPARE from `WS-CUST-NAME` at SAMPLE.cbl:93; SQL text: "
                      "`DELETE FROM BANK.TEMP_TRAN`", markdown)
        self.assertIn("- 2 commit and rollback points in 1 program: COMMIT 1, SYNCPOINT ROLLBACK 1.", markdown)
        self.assertIn("Copybooks found in folders: `cpy` (1)", markdown)
        self.assertIn("ACCTUPD still fails", page["notes"])
        self.assertIn("_Not ready.", backlog(self.store))

        (self.src / "migration.json").write_text(json.dumps({"version": 1, "units": [
            {"id": "U2", "name": "Later", "wave": 2, "programs": ["program:SAMPLE"], "status": "building",
             "threads": [{"url": "https://ampcode.com/threads/T-2", "task": "build"}],
             "writes": ["db2:BANK.AUDIT_LOG"],
             "dependencies": [{"unit": "U1", "on": "vsam:ACCTFIL", "handling": "Calls U1's account service"}]},
            {"id": "U1", "name": "First", "wave": 1, "programs": ["program:SAMPLE2"], "status": "built",
             "threads": [{"url": "https://ampcode.com/threads/T-1", "task": "build", "finished": True}],
             "interfaces": [{"direction": "provides", "name": "account record", "layout": "copybook:SAMPREC",
                             "with": "U2"}],
             "acceptanceChecks": [{"description": "Balances match the batch report for every account"}]}]}))
        (self.src / "units").mkdir()
        (self.src / "units" / "U1.md").write_text("# Business Rules\n\n- Rejects a zero amount at SAMPLE.cbl:40.\n")
        full = backlog(self.store)
        self.assertLess(full.index("### U1 First"), full.index("### U2 Later"))
        self.assertIn("- **Programs:** `SAMPLE` (program)", full)
        self.assertIn("Progress: 0 verified, 1 built, 1 building, 0 to do.", full)
        # Only threads that haven't reported back are active; every unit links all of its threads.
        active = full[full.index("## Active Threads"):full.index("## Wave 1")]
        self.assertEqual(active.strip().splitlines()[1:],
                         ["", "- [U2 build](https://ampcode.com/threads/T-2): Later, building"])
        self.assertIn("- **Status:** built\n- **Threads:** [build](https://ampcode.com/threads/T-1) (finished)", full)
        self.assertIn("- **Depends on:**\n  - U1 for `ACCTFIL` (vsam): Calls U1's account service", full)
        self.assertIn("- **Interfaces:**\n  - Provides account record with U2: `SAMPREC` (copybook)", full)
        self.assertIn("- **Acceptance checks:**\n  - Balances match the batch report for every account", full)
        self.assertIn("#### Business Rules", full)
        self.assertNotIn("Rejects a zero amount", full[full.index("### U2 Later"):])
        # SAMPLE2 was never parsed, so the check flags it; U2 has no notes file yet.
        self.assertIn("program:SAMPLE2 is not in the map", full)
        self.assertIn("units/U2.md does not exist yet", full)

        source_file = str(self.src / "SAMPLE.cbl")
        self.assertEqual(source(self.store, source_file, 40)["lines"][12].strip(),
                         "CALL 'SAMPUTIL' USING WS-AMOUNT")
        self.assertIsNotNone(source(self.store, str(self.src / "cpy" / "SAMPREC.cpy"), 1))
        self.assertIsNone(source(self.store, str(self.jar), 1))

    def test_resolvers_connect_transactions_screens_jobs_and_datasets(self):
        # Notes and patches that quote a DBD are not sources.
        for name in ("notes.md", "fix.patch"):
            (self.src / name).write_text((FIXTURES / "ims" / "SAMPDBD.dbd").read_text().replace("SAMPDBD", "QUOTED"))
        self.parse(programs=("SAMPLE", "ONLINE", "SAMPUTIL"))  # runs every resolver at the end
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
            # An IMS batch step names its program in DFSRRC00's PARM.
            ("runs", "job:SAMPIMS", "program:SAMPLE"),
            ("read", "program:SAMPLE", "dataset:PROD.SAMPLE.IMSACCT"),
            # SELECT ... ASSIGN names matched to the DD statements of the step that runs the program.
            ("read", "program:SAMPLE", "dataset:PROD.SAMPLE.ACCOUNTS"),
            ("write", "program:SAMPLE", "dataset:PROD.SAMPLE.REPORT(+1)"),
            # A program SAMPLE calls reads through the DD of the step that runs SAMPLE.
            ("read", "program:SAMPUTIL", "dataset:PROD.SAMPLE.RATES"),
            ("performs", "paragraph:SAMPLE.0000-MAIN", "paragraph:SAMPLE.1000-READ"),
            ("calls", "program:SAMPLE", "program:SAMPUTIL"),
            ("transfers", "program:SAMPLE", None),
            ("includes", "program:SAMPLE", "copybook:SAMPREC"),
            # PERFORM chains continue into called programs.
            ("invokes", "paragraph:SAMPLE.0000-MAIN", "program:SAMPUTIL"),
            # CSD: the online file's dataset is the one the batch job reads; plans; TD queues.
            ("stored-in", "vsam:ACCTFIL", "dataset:PROD.SAMPLE.ACCOUNTS"),
            ("uses-plan", "transaction:SAMP", "plan:SAMPPLN"),
            # IMS: DBD segments and datasets, PSB databases, programs' PSBs, GSAM output.
            ("contains", "database:SAMPDBD", "ims:PAUTDTL1"),
            ("uses", "psb:SAMPPSB", "database:SAMPGSAM"),
            ("uses", "program:ONLINE", "psb:SAMPPSB"),
            ("uses", "program:SAMPLE", "psb:SAMPPSB"),
            ("stored-in", "database:SAMPDBD", "dataset:PROD.SAMPLE.IMSDB"),
            ("write", "program:SAMPLE", "dataset:PROD.SAMPLE.UNLOAD"),
            # Schedulers: Control-M folders and conditions, CA-7 triggers.
            ("schedules", "schedule:DAILY-Sample", "job:SAMPJOB"),
            ("precedes", "job:SAMPJOB", "job:SAMPIMS"),
            ("triggers", "job:SAMPJOB", "job:SAMPIMS"),
            # z/OS Connect: API operation, asset and program; a page calling the API through a client
            ("invokes", "api:GET /accounts/{id}", "zosasset:ACCTINQ"),
            ("links", "zosasset:ACCTINQ", "program:SAMPLE"),
            ("calls", "page:web/page.html", "api:GET /accounts/{id}"),
            ("calls", "page:web/page.html", "api:DELETE /accounts/{id}"),
            ("calls", "page:web/page.html", None),  # closeAccount builds no URL
            # Easytrieve Plus: files by FILE name (the DD), the report, the macro and the call.
            ("read", "program:SAMPEZT", "file:OLDMAST"),
            ("read", "program:SAMPEZT", "file:TRANS"),
            ("write", "program:SAMPEZT", "file:NEWMAST"),
            ("read", "program:SAMPEZT", "file:NEWMAST"),
            ("write", "program:SAMPEZT", "file:SORTED"),
            ("prints", "program:SAMPEZT", "report:SAMPEZT.RPT1"),
            ("includes", "program:SAMPEZT", "macro:SAMPMAC"),
            ("calls", "program:SAMPEZT", "program:SAMPUTIL"),
            # EZTPA00 runs the member in SYSIN; its FILE names are DD names.
            ("runs", "job:SAMPEZTJ", "program:SAMPEZT"),
            ("read", "program:SAMPEZT", "dataset:PROD.SAMPLE.OLDMAST"),
            ("read-write", "program:SAMPEZT", "dataset:PROD.SAMPLE.NEWMAST"),
            # Ways in: terminal users, an MQ service, a script that submits jobs, JCL a program submits.
            ("starts", "interface:3270", "transaction:SAMP"),
            ("serves", "api:ONLINE", "program:ONLINE"),
            ("submits", "script:nightly.sh", "job:SAMPJOB"),
            ("submits", "program:ONLINE", "job:SAMPRPT"),
            ("runs", "job:SAMPRPT", "proc:SAMPPROC"),
        ]:
            self.assertIn(expected, rows)
        menu = next(r for r in conn.execute("SELECT * FROM relationships WHERE kind = 'invokes' AND source LIKE '%ONLINE%' AND target IS NULL"))
        self.assertEqual((menu["source"], menu["note"]), ("paragraph:ONLINE.0000-MAIN", "maybe SAMPACCT, SAMPRPT"))
        include = next(r for r in conn.execute("SELECT * FROM relationships WHERE kind = 'includes' AND source = 'program:SAMPLE'"))
        self.assertEqual(include["line"], 21)
        self.assertFalse([r for r in rows if "QUOTED" in str(r)])
        self.assertNotIn(("runs", "job:SAMPJOB", "program:IKJEFT01"), rows)
        self.assertNotIn(("runs", "job:SAMPIMS", "program:DFSRRC00"), rows)
        self.assertNotIn(("calls", "page:web/page.html", "api:GET /accounts/{id}/x"), rows)
        self.assertNotIn(("read", "program:SAMPEZT", "file:ACCT"), rows)  # a KEY field, not a file
        # Control flow: where the program starts, which paragraphs fall into the next, and the
        # paragraph that makes each call.
        for expected in [
            ("enters", "program:SAMPLE", "paragraph:SAMPLE.0000-MAIN"),
            ("falls-through", "paragraph:SAMPLE.1000-READ", "paragraph:SAMPLE.1000-EXIT"),
            ("falls-through", "paragraph:SAMPLE.1000-EXIT", "paragraph:SAMPLE.2000-DB2"),
            # A GO TO inside an IF does not end the paragraph, and fall-through crosses sections.
            ("falls-through", "paragraph:SAMPLE.8010-REGISTER", "paragraph:SAMPLE.8020-WORK"),
            ("falls-through", "paragraph:SAMPLE.8020-WORK", "paragraph:SAMPLE.8900-RECOVER"),
            ("contains", "paragraph:SAMPLE.8000-GUARDED", "paragraph:SAMPLE.8010-REGISTER"),
            ("contains", "program:SAMPLE", "paragraph:SAMPLE.8020-WORK"),
            ("handles", "paragraph:SAMPLE.8010-REGISTER", "paragraph:SAMPLE.8900-RECOVER"),
            ("invokes", "paragraph:SAMPLE.0000-MAIN", "program:SAMPUTIL"),
            ("invokes", "paragraph:SAMPLE.3000-CICS", "program:SAMPLNK"),
        ]:
            self.assertIn(expected, rows)
        # GOBACK and EXEC CICS RETURN end their paragraphs; nothing falls out of them.
        self.assertNotIn(("falls-through", "paragraph:SAMPLE.0000-MAIN", "paragraph:SAMPLE.1000-READ"), rows)
        self.assertNotIn(("falls-through", "paragraph:SAMPLE.6000-SCREEN", "paragraph:SAMPLE.8010-REGISTER"), rows)
        self.assertNotIn(("contains", "paragraph:SAMPLE.8000-GUARDED", "paragraph:SAMPLE.8900-RECOVER"), rows)
        entities = {(e["entity"], e["kind"], e["note"]) for e in conn.execute("SELECT * FROM entities")}
        self.assertIn(("transaction:SAMP", "defined", "SAMPLE ACCOUNT INQUIRY"), entities)
        self.assertIn(("screen:SAMPSET.SAMPMAP", "defined", None), entities)
        self.assertIn(("job:SAMPJOB", "defined", None), entities)
        self.assertIn(("paragraph:SAMPLE.1000-READ", "business-logic", "Copies each account to the report"),
                      entities)
        self.assertIn("## Relationships", report(self.store)["parser"])

    def test_ddl_tables_keys_and_views_meet_the_programs_tables(self):
        self.parse()
        # The JCL that runs DSNTIAD is read for its CREATE TABLE statements; programs are not.
        self.assertEqual(self.ddl_files, ["ddl/PROCS.sql", "jcl/SAMPDDL.jcl"])
        conn = self.db()
        entities = {(e["entity"], e["kind"], e["note"])
                    for e in conn.execute("SELECT * FROM entities WHERE resolver = 'ddl'")}
        rows = {(r["kind"], r["source"], r["target"], r["note"])
                for r in conn.execute("SELECT * FROM relationships WHERE resolver = 'ddl'")}
        # The programs say BANK.AUDIT_LOG; the DDL says AUDIT_LOG. They are the same table.
        self.assertIn(("db2:BANK.AUDIT_LOG", "defined", "3 columns; primary key ID; defined as AUDIT_LOG"), entities)
        self.assertIn(("db2:BANK.CUSTOMER", "defined", "2 columns; primary key CUST_ID"), entities)
        self.assertIn(("column:BANK.AUDIT_LOG.AGE", "column", "SMALLINT NOT NULL WITH DEFAULT"), entities)
        self.assertIn(("references", "db2:BANK.AUDIT_LOG", "db2:BANK.CUSTOMER",
                       "CUST_ID -> CUST_ID; ON DELETE CASCADE"), rows)
        self.assertIn(("indexes", "index:BANK.AUDIT_CUST", "db2:BANK.AUDIT_LOG", "on CUST_ID"), rows)
        # The programs qualify their tables with BANK, so the view keeps its schema too.
        self.assertIn(("selects-from", "db2:BANK.CUSTOMER_AUDIT", "db2:BANK.CUSTOMER", None), rows)
        self.assertEqual([e for e in entities if e[1] in ("no-definition", "parse-error")], [])
        self.assertIn("- 2 tables defined in DDL; 0 used by programs with no definition; 0 DDL statements "
                      "not parsed.", report(self.store)["parser"])
        # And the program's own access reaches the defined table.
        self.assertIn(("db2:BANK.AUDIT_LOG", "defined"),
                      {(r["target"], "defined") for r in conn.execute(
                          "SELECT target FROM relationships WHERE source = 'program:SAMPLE'")})

    def test_check_catches_plan_mistakes(self):
        self.parse()
        path = self.src / "migration.json"

        def problems(data):
            path.write_text(json.dumps(data))
            conn = store.connect(self.store)
            try:
                return plan.check(path, conn).errors
            finally:
                conn.close()

        unit = {"id": "U1", "name": "Accounts", "wave": 1, "programs": ["program:SAMPLE"]}
        self.assertEqual(problems({"version": 1, "units": [unit]}), [])
        # Schema: required fields, typed endpoints, no extra fields.
        self.assertIn("units[0]: missing wave", problems({"version": 1, "units": [
            {k: v for k, v in unit.items() if k != "wave"}]}))
        self.assertIn('units[0].programs[0]: "SAMPLE" does not match ^(program:.+|paragraph:[^.]+\\..+)$',
                      problems({"version": 1, "units": [{**unit, "programs": ["SAMPLE"]}]}))
        self.assertIn("units[0]: unknown field dependsOn",
                      problems({"version": 1, "units": [{**unit, "dependsOn": ["U0"]}]}))
        # A dependency in the same wave, or on a unit that doesn't exist.
        later = {"id": "U2", "name": "Reports", "wave": 1, "programs": ["program:SAMPUTIL"],
                 "dependencies": [{"unit": "U1", "on": "program:SAMPLE", "handling": "Reads its output"}]}
        errors = problems({"version": 1, "units": [unit, later]})
        self.assertTrue(any("depends on U1, which is in wave 1" in e for e in errors), errors)
        later["dependencies"][0]["unit"] = "U9"
        self.assertTrue(any("depends on U9, which is not a unit" in e for e in problems(
            {"version": 1, "units": [unit, {**later, "wave": 2}]})))
        # Every parsed program in exactly one unit, or excluded with a reason.
        self.assertIn("program:SAMPLE is not in any unit; add it to one or to excluded with a reason",
                      problems({"version": 1, "units": []}))
        self.assertEqual(problems({"version": 1, "units": [], "excluded": [
            {"program": "program:SAMPLE", "reason": "Replaced by the platform's scheduler"}]}), [])
        self.assertIn("program:SAMPLE is in more than one unit: U1, U2", problems({"version": 1, "units": [
            unit, {**unit, "id": "U2"}]}))
        # A program split by paragraph is covered when every paragraph is in exactly one unit; the unit
        # that also lists the program owns the code before its first paragraph.
        conn = store.connect(self.store)
        paragraphs = [r["target"] for r in conn.execute(
            "SELECT target FROM relationships WHERE kind = 'contains' AND source = 'program:SAMPLE' ORDER BY line")]
        conn.close()
        self.assertEqual(paragraphs[:2], ["paragraph:SAMPLE.0000-MAIN", "paragraph:SAMPLE.1000-READ"])
        main = {**unit, "programs": ["program:SAMPLE", paragraphs[0]]}
        rest = {"id": "U2", "name": "Reading", "wave": 1, "programs": paragraphs[1:]}
        self.assertEqual(problems({"version": 1, "units": [main, rest]}), [])
        errors = problems({"version": 1, "units": [main, {**rest, "programs": paragraphs[2:]}]})
        self.assertIn(f"program:SAMPLE is split by paragraph, but 1 of its {len(paragraphs)} paragraphs are in "
                      "no unit: 1000-READ", errors)
        self.assertIn("paragraph:SAMPLE.0000-MAIN is in more than one unit: U1, U2", problems(
            {"version": 1, "units": [main, {**rest, "programs": paragraphs}]}))
        self.assertIn("unit U2: paragraph:SAMPLE.9999-NONE is not in the map; check the name, or record it with "
                      "mfmap record if it is real", problems(
            {"version": 1, "units": [main, {**rest, "programs": [*paragraphs[1:], "paragraph:SAMPLE.9999-NONE"]}]}))
        path.write_text(json.dumps({"version": 1, "units": [{**main, "programs": paragraphs[:1]}, rest]}))
        self.assertIn("program:SAMPLE is split by paragraph, but no unit lists program:SAMPLE to own the code "
                      "before its first paragraph", plan.check(path).warnings)
        # Endpoints must be in the map, but anything recorded with mfmap record counts.
        bad = {**unit, "reads": ["db2:BANK.CUSTOMR"]}
        self.assertIn("unit U1: db2:BANK.CUSTOMR is not in the map; check the name, or record it with "
                      "mfmap record if it is real", problems({"version": 1, "units": [bad]}))
        self.assertEqual(problems({"version": 1, "units": [{**unit, "reads": ["db2:BANK.CUSTOMER"]}]}), [])
        resolvers.record(self.store, "exposes", "api:/accounts", "program:SAMPLE")
        self.assertEqual(problems({"version": 1, "units": [{**unit, "entryPoints": ["api:/accounts"]}]}), [])
        self.assertIn('units[0].status: must be one of "todo", "building", "built", "verified"',
                      problems({"version": 1, "units": [{**unit, "status": "done"}]}))
        # Starting a unit before what it depends on is built is a warning, not an error.
        later = {"id": "U2", "name": "Reports", "wave": 2, "programs": ["program:SAMPUTIL"], "status": "building",
                 "dependencies": [{"unit": "U1", "on": "program:SAMPLE", "handling": "Reads its output"}]}
        path.write_text(json.dumps({"version": 1, "units": [{**unit, "status": "building"}, later]}))
        self.assertIn("unit U2 is building, but it depends on U1, which is building", plan.check(path).warnings)
        path.write_text(json.dumps({"version": 1, "units": [{**unit, "status": "built"}, later]}))
        self.assertFalse(any("depends on" in w for w in plan.check(path).warnings))

    def test_schema_copy_matches(self):
        shipped = Path(plan.__file__).with_name("migration-v1.schema.json").read_text()
        source = (Path(__file__).parents[3] / "schema" / "migration-v1.schema.json").read_text()
        self.assertEqual(shipped, source, "copy schema/migration-v1.schema.json to toolkit/python/mfmap/")

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
