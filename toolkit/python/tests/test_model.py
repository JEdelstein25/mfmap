# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Tests over fixtures/SAMPLE.json, produced from fixtures/SAMPLE.cbl by regenerate.sh."""

import copy
import json
import unittest
from pathlib import Path

import mfmap as cg
from mfmap.crosscheck import TextScan, graph_counts
from mfmap.run import output_names

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA = Path(__file__).parents[3] / "schema" / "graph-v1.schema.json"


def load():
    return cg.load(FIXTURES / "SAMPLE.json", path_map={"/FIXTURE": str(FIXTURES)})


class ModelTest(unittest.TestCase):
    def setUp(self):
        self.file = load()
        self.program = self.file.programs[0]

    def test_data_items(self):
        p = self.program
        self.assertEqual(p.data_item("WS-AMOUNT-X").redefines.name, "WS-AMOUNT")
        self.assertIsNone(p.data_item("WS-AMOUNT").redefines)
        entry = p.data_item("WS-ENTRY")
        self.assertEqual((entry.occurs, entry.sync, entry.usage, entry.pic), (12, True, "COMP", "9(4)"))
        self.assertEqual(entry.parent.name, "WS-TABLE")
        self.assertIsNone(entry.occurs_min)
        item = p.data_item("SAMP-ITEM")
        self.assertEqual((item.occurs, item.occurs_min, item.depending_on), (20, 1, "SAMP-COUNT"))
        self.assertEqual(p.data_item("SAMP-NAME").copybook, "SAMPREC")
        self.assertIsNone(p.data_item("WS-CUST-NAME").copybook)
        ok = p.data_item("WS-FILE-OK")
        self.assertEqual((ok.level, ok.parent.name, ok.condition_values), (88, "WS-FILE-STATUS", [{"from": "'00'"}]))
        self.assertEqual([i.name for i in p.file_control("ACCT-FILE").records], ["ACCT-REC"])

    def test_references_carry_their_statements(self):
        refs = self.program.data_item("WS-CUST-ID").references
        self.assertEqual(
            [(r.location.line, type(r.statement).__name__, r.statement.verb) for r in refs],
            [(61, "Sql", "DECLARE"), (69, "Sql", "INSERT"), (82, "Dli", "GU"), (89, "Sql", "CALL")],
        )

    def test_paragraphs_and_performs(self):
        p = self.program
        read = p.paragraph("1000-READ")
        self.assertEqual([s.verb for s in read.statements], ["OPEN", "OPEN", "READ", "IF", "MOVE", "WRITE", "CLOSE"])
        self.assertEqual([s.location.line for s in read.performed_by], [36])
        first = p.performs[0]
        self.assertEqual((first.target.name, first.thru.name), ("1000-READ", "1000-EXIT"))
        inline = [s for s in p.performs if s.target_name is None]
        self.assertEqual([s.location.line for s in inline], [42])

    def test_statement_source_drops_sequence_area(self):
        read = next(s for s in self.program.cics if s.verb == "READ")
        self.assertEqual(
            read.source,
            "EXEC CICS READ DATASET('ACCTFIL') INTO(ACCT-REC)\n        RIDFLD(ACCT-KEY) RESP(WS-RESP)\n    END-EXEC",
        )

    def test_call_edges(self):
        edges = [(e.via, e.target, e.resolved, e.expression, e.candidates) for e in cg.call_edges(self.program)]
        self.assertEqual(edges, [
            ("CALL", "SAMPUTIL", "literal", "'SAMPUTIL'", ()),
            ("CALL", "SAMPSUB", "value", "WS-PGM-NAME", ()),
            ("LINK", "SAMPLNK", "literal", "'SAMPLNK'", ()),
            ("XCTL", None, "unresolved", "WS-NEXT-PGM", ("SAMPNXT",)),
            ("SQL CALL", "BANK.POST_TRAN", "literal", "BANK.POST_TRAN", ()),
            # A procedure named by a host variable resolves through the item's VALUE.
            ("SQL CALL", "SAMPSUB", "value", "WS-PGM-NAME", ()),
        ])

    def test_data_access(self):
        access = {(a.store, a.resource, a.mode, a.statement.verb, a.paragraph.name)
                  for a in cg.data_access(self.program)}
        self.assertEqual(access, {
            ("db2", "BANK.CUSTOMER", "read", "OPEN", "2000-DB2"),
            ("db2", "BANK.CUSTOMER", "read", "FETCH", "2000-DB2"),
            ("db2", "BANK.AUDIT_LOG", "write", "INSERT", "2000-DB2"),
            ("vsam", "ACCTFIL", "read", "READ", "3000-CICS"),
            ("vsam", "ACCTFIL", "write", "REWRITE", "3000-CICS"),
            ("ims", "PAUTSUM0", "read", "GU", "4000-IMS"),
            ("ims", "PAUTDTL1", "write", "ISRT", "4000-IMS"),
            ("file", "ACCTDD", "read", "OPEN", "1000-READ"),
            ("file", "RPTDD", "write", "OPEN", "1000-READ"),
            ("file", "ACCTDD", "read", "READ", "1000-READ"),
            ("file", "RPTDD", "write", "WRITE", "1000-READ"),
            # Dynamic SQL: tables unknown; EXECUTE of a prepared statement adds no second row.
            ("db2", None, "unknown", "PREPARE", "5000-SQL-PROC"),
            ("db2", None, "unknown", "EXECUTE", "5000-SQL-PROC"),
        })
        dynamic = [a for a in cg.data_access(self.program) if a.mode == "unknown"]
        self.assertEqual({(a.resolved, a.expression, a.candidates) for a in dynamic},
                         {("unresolved", "WS-CUST-NAME", ("DELETE FROM BANK.TEMP_TRAN",))})

    def test_sql_columns_values_into_and_where(self):
        sql = {s.location.line: s for s in self.program.sql}
        self.assertEqual((sql[58].columns, sql[58].where), (["CUST_NAME"], "CUST_ID > :WS-CUST-ID"))
        self.assertEqual(sql[64].into, [":WS-CUST-NAME"])
        self.assertEqual((sql[67].columns, sql[67].values), (["CUST_ID"], [":WS-CUST-ID"]))

    def test_conditions(self):
        read = self.program.paragraph("1000-READ")
        self.assertEqual(next(s for s in read.statements if s.verb == "IF").condition, "WS-FILE-OK")
        loop = next(s for s in self.program.performs if s.target_name is None)
        self.assertEqual(loop.condition, "WS-RESP > 3")

    def test_commit_points(self):
        self.assertEqual([(c.kind, c.statement.location.line) for c in cg.commit_points(self.program)],
                         [("COMMIT", 96), ("SYNCPOINT ROLLBACK", 97)])

    def test_procedures_from_ddl(self):
        from mfmap import procedures as sp
        defined = {d.name: d for d in sp.procedures(sp.find_ddl(FIXTURES / "ddl"))}
        post = defined["BANK.POST_TRAN"]
        self.assertEqual((post.language, post.program, post.result_sets, post.line), ("COBOL", "POSTTRN", 1, 2))
        self.assertEqual(post.parameters, ("IN CUST_ID INTEGER", "INOUT AMOUNT DECIMAL(9, 2)"))
        # A bare EXTERNAL means the program has the procedure's name; EXTERNAL SECURITY does not.
        self.assertEqual(defined["BANK.SAMPSUB"].program, "SAMPSUB")
        purge = defined["BANK.PURGE_AUDIT"]
        self.assertEqual((purge.language, purge.program), ("SQL", None))
        self.assertEqual(purge.writes, ("BANK.AUDIT_LOG", "BANK.PURGE_HIST"))
        self.assertEqual(purge.reads, ("BANK.AUDIT_LOG", "BANK.AUDIT_ARCH"))
        self.assertEqual(purge.calls, ("BANK.POST_TRAN",))
        # An unqualified CALL gets its schema from bind options, so it matches by name alone.
        self.assertIs(sp.match("SAMPSUB", defined.values()), defined["BANK.SAMPSUB"])
        self.assertIsNone(sp.match("OTHER.SAMPSUB", defined.values()))

    def test_crosscheck_counts_match(self):
        scan = TextScan([FIXTURES / "cpy"])
        self.assertEqual(scan.counts(FIXTURES / "SAMPLE.cbl"), graph_counts(self.program))
        self.assertEqual(graph_counts(self.program)["PERFORM"], 5)  # END-PERFORM is not a PERFORM
        # EXEC SQL CALL is a stored procedure call, not a COBOL CALL.
        self.assertEqual((graph_counts(self.program)["CALL"], graph_counts(self.program)["SQL CALL"]), (2, 2))

    def test_output_names_disambiguate_shared_stems(self):
        names = output_names([Path("a/x/P.cbl"), Path("a/y/P.cbl"), Path("a/Q.cbl")])
        self.assertEqual(sorted(names.values()), ["P.json", "P@y.json", "Q.json"])

    def test_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text()))
        data = json.loads((FIXTURES / "SAMPLE.json").read_text())
        self.assertEqual(list(validator.iter_errors(data)), [])
        broken = copy.deepcopy(data)
        usage = next(n for n in self.file.nodes("VariableUsageNode") if n.refs("definitions"))
        node = find(broken["tree"], usage.id)
        node["definitions"] = [{"ref": "x1"}]
        self.assertNotEqual(list(validator.iter_errors(broken)), [])


def find(node, node_id):
    if node["id"] == node_id:
        return node
    for child in node["children"]:
        found = find(child, node_id)
        if found:
            return found
    return None


if __name__ == "__main__":
    unittest.main()
