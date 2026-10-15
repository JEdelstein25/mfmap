/*
 * Copyright (c) 2026 Amp.
 *
 * This program and the accompanying materials are made
 * available under the terms of the Eclipse Public License 2.0
 * which is available at https://www.eclipse.org/legal/epl-2.0/
 *
 * SPDX-License-Identifier: EPL-2.0
 *
 * Contributors:
 *    Amp - test embedded statement resource metadata
 */
package org.eclipse.lsp.cobol.usecases;

import static org.junit.jupiter.api.Assertions.*;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.gson.Gson;
import java.util.Arrays;
import org.antlr.v4.runtime.CharStreams;
import org.antlr.v4.runtime.CommonTokenStream;
import org.eclipse.lsp.cobol.implicitDialects.cics.CICSLexer;
import org.eclipse.lsp.cobol.implicitDialects.cics.CICSParser;
import org.eclipse.lsp.cobol.implicitDialects.cics.nodes.ExecCicsNode;
import org.eclipse.lsp.cobol.implicitDialects.sql.Db2SqlExecLexer;
import org.eclipse.lsp.cobol.implicitDialects.sql.Db2SqlExecParser;
import org.eclipse.lsp.cobol.implicitDialects.sql.node.ExecSqlNode;
import org.eclipse.lsp.cobol.test.engine.UseCaseEngine;
import org.junit.jupiter.api.Test;

/** Resource metadata must preserve arguments, table order, and cursor identities. */
class TestExecResourceMetadata {
  @Test
  void specialCicsNodesRetainMetadata() {
    String source =
        "       IDENTIFICATION DIVISION.\n"
            + "       PROGRAM-ID. METADATA.\n"
            + "       PROCEDURE DIVISION.\n"
            + "           EXEC CICS HANDLE ABEND CANCEL END-EXEC\n"
            + "           EXEC CICS RETURN END-EXEC\n"
            + "           EXEC CICS ABEND CANCEL END-EXEC.\n";
    String json =
        new Gson()
            .toJson(
                UseCaseEngine.runTest(source, ImmutableList.of(), ImmutableMap.of()).getRootNode());
    assertTrue(json.contains("\"command\":\"HANDLE ABEND\""));
    assertTrue(json.contains("\"command\":\"RETURN\""));
    assertTrue(json.contains("\"command\":\"ABEND\""));
  }

  @Test
  void cicsOptions() {
    CICSParser parser =
        new CICSParser(
            new CommonTokenStream(
                new CICSLexer(
                    CharStreams.fromString(
                        "READ DATASET('AcctDat') INTO(ACCOUNT-RECORD) UPDATE NOHANDLE"))));
    ExecCicsNode node = new ExecCicsNode(null);
    node.describe(parser.allCicsRule());
    assertEquals(0, parser.getNumberOfSyntaxErrors());
    assertEquals("READ", node.getCommand());
    assertEquals(4, node.getOptions().size());
    assertEquals("DATASET", node.getOptions().get(0).getName());
    assertEquals("'AcctDat'", node.getOptions().get(0).getValue());
    assertEquals("ACCOUNT-RECORD", node.getOptions().get(1).getValue());
    assertEquals("UPDATE", node.getOptions().get(2).getName());
    assertNull(node.getOptions().get(2).getValue());
    assertEquals("NOHANDLE", node.getOptions().get(3).getName());
    assertNull(node.getOptions().get(3).getValue());
    assertTrue(new Gson().toJson(node).contains("\"command\":\"READ\""));
  }

  @Test
  void sqlTablesAndCursor() {
    ExecSqlNode select =
        sql(
            "SELECT A.ID INTO :OUT-ID FROM FIRST.ACCOUNT A, SECOND.CARD B "
                + "WHERE A.ID = B.ID AND EXISTS (SELECT ID FROM FIRST.ACCOUNT)");
    assertEquals("SELECT INTO", select.getStatementType());
    assertEquals(Arrays.asList("FIRST.ACCOUNT", "SECOND.CARD"), select.getTables());
    ExecSqlNode cursor = sql("DECLARE C1 CURSOR FOR SELECT ID FROM CARDDEMO.TRANSACTION_TYPE");
    assertEquals("DECLARE CURSOR", cursor.getStatementType());
    assertEquals("C1", cursor.getCursorName());
    assertEquals(Arrays.asList("CARDDEMO.TRANSACTION_TYPE"), cursor.getTables());
    assertTrue(new Gson().toJson(cursor).contains("\"cursorName\":\"C1\""));
  }

  @Test
  void storedProcedureCallsAndDynamicSql() {
    ExecSqlNode call = sql("CALL PAYROLL.CALC_PAY(:EMP-ID, :PAY-AMT)");
    assertEquals("CALL", call.getStatementType());
    assertEquals("PAYROLL.CALC_PAY", call.getProcedureName());
    assertEquals(":PROC-NAME", sql("CALL :PROC-NAME").getProcedureName());

    ExecSqlNode prepare = sql("PREPARE S1 FROM :WS-STMT");
    assertEquals("PREPARE", prepare.getStatementType());
    assertEquals("S1", prepare.getStatementName());
    assertEquals(":WS-STMT", prepare.getSqlSource());
    assertEquals("S1", sql("EXECUTE S1 USING :WS-ID").getStatementName());
    ExecSqlNode cursor = sql("DECLARE C2 CURSOR FOR S1");
    assertEquals("DECLARE CURSOR", cursor.getStatementType());
    assertEquals("S1", cursor.getStatementName());
    assertNull(sql("DECLARE C3 CURSOR FOR SELECT ID FROM T1").getStatementName());

    ExecSqlNode immediate = sql("EXECUTE IMMEDIATE :WS-STMT");
    assertEquals("EXECUTE IMMEDIATE", immediate.getStatementType());
    assertEquals(":WS-STMT", immediate.getSqlSource());
    ExecSqlNode literal = sql("EXECUTE IMMEDIATE 'DELETE FROM OLD.AUDIT WHERE ID = 1'");
    assertEquals("'DELETE FROM OLD.AUDIT WHERE ID = 1'", literal.getSqlSource());
    assertTrue(new Gson().toJson(call).contains("\"procedureName\":\"PAYROLL.CALC_PAY\""));
  }

  private ExecSqlNode sql(String source) {
    Db2SqlExecParser parser =
        new Db2SqlExecParser(
            new CommonTokenStream(new Db2SqlExecLexer(CharStreams.fromString(source))));
    ExecSqlNode node = new ExecSqlNode(null);
    node.describe(parser.startSqlRule());
    assertEquals(0, parser.getNumberOfSyntaxErrors());
    return node;
  }
}
