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
 *    Amp - verify IMS statement options and host references
 *
 */
package org.eclipse.lsp.cobol.usecases;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.util.List;
import java.util.stream.Collectors;
import org.eclipse.lsp.cobol.common.error.ErrorSource;
import org.eclipse.lsp.cobol.common.model.tree.ExecDliNode;
import org.eclipse.lsp.cobol.common.model.tree.variable.VariableUsageNode;
import org.eclipse.lsp.cobol.test.engine.UseCaseEngine;
import org.eclipse.lsp4j.Diagnostic;
import org.eclipse.lsp4j.DiagnosticSeverity;
import org.eclipse.lsp4j.Range;
import org.junit.jupiter.api.Test;

/** Checks DL/I statements through the public analysis pipeline. */
class TestExecDli {
  @Test
  void test() {
    String text =
        "       IDENTIFICATION DIVISION.\n"
            + "       PROGRAM-ID. DLITEST.\n"
            + "       DATA DIVISION.\n"
            + "       WORKING-STORAGE SECTION.\n"
            + "       01 {$*BUFFER} PIC X(10).\n"
            + "       01 {$*KEY-VALUE} PIC X(10).\n"
            + "       PROCEDURE DIVISION.\n"
            + "           EXEC DLI GU USING PCB(1)\n"
            + "             SEGMENT (CUSTOMER) INTO ({$BUFFER})\n"
            + "             WHERE (ID = {$KEY-VALUE}) NODHABEND\n"
            + "           END-EXEC\n"
            + "           EXEC DLI SCHD PSB((PSB-NAME)) END-EXEC\n"
            + "           EXEC DLI REPL FROM ( {$BUFFER} )\n"
            + "             WHERE (ID = 'A = B)') END-EXEC\n"
            + "           GOBACK.\n";
    List<ExecDliNode> nodes =
        UseCaseEngine.runTest(text, ImmutableList.of(), ImmutableMap.of())
            .getRootNode()
            .getDepthFirstStream()
            .filter(ExecDliNode.class::isInstance)
            .map(ExecDliNode.class::cast)
            .collect(Collectors.toList());
    assertEquals(3, nodes.size());
    ExecDliNode node = nodes.get(0);
    assertEquals("GU", node.getCommand());
    assertEquals("dli", node.getDialect());
    assertEquals(6, node.getOptions().size());
    assertEquals("USING", node.getOptions().get(0).getName());
    assertNull(node.getOptions().get(0).getValue());
    assertEquals("PCB", node.getOptions().get(1).getName());
    assertEquals("1", node.getOptions().get(1).getValue());
    assertEquals("ID = KEY-VALUE", node.getOptions().get(4).getValue());
    assertEquals("NODHABEND", node.getOptions().get(5).getName());
    assertNull(node.getOptions().get(5).getValue());
    assertEquals(2, node.getDepthFirstStream().filter(VariableUsageNode.class::isInstance).count());
    assertEquals("(PSB-NAME)", nodes.get(1).getOptions().get(0).getValue());
    assertEquals(
        1, nodes.get(2).getDepthFirstStream().filter(VariableUsageNode.class::isInstance).count());
  }

  @Test
  void dliIsTheOnlyStatementInABranch() {
    String text =
        "       IDENTIFICATION DIVISION.\n"
            + "       PROGRAM-ID. DLIIF.\n"
            + "       DATA DIVISION.\n"
            + "       WORKING-STORAGE SECTION.\n"
            + "       01 {$*WS-FLAG} PIC X.\n"
            + "          88 {$*FOUND-SEG} VALUE 'Y'.\n"
            + "       01 {$*SUMREC} PIC X(10).\n"
            + "       PROCEDURE DIVISION.\n"
            + "           IF {$FOUND-SEG}\n"
            + "              EXEC DLI REPL SEGMENT (PAUTSUM0) FROM ({$SUMREC})\n"
            + "              END-EXEC\n"
            + "           ELSE\n"
            + "              EXEC DLI ISRT SEGMENT (PAUTSUM0) FROM ({$SUMREC})\n"
            + "              END-EXEC\n"
            + "           END-IF\n"
            + "           IF {$FOUND-SEG}\n"
            + "              EXEC DLI TERM END-EXEC\n"
            + "           END-IF\n"
            + "           GOBACK.\n";
    List<String> commands =
        UseCaseEngine.runTest(text, ImmutableList.of(), ImmutableMap.of())
            .getRootNode()
            .getDepthFirstStream()
            .filter(ExecDliNode.class::isInstance)
            .map(n -> ((ExecDliNode) n).getCommand())
            .collect(Collectors.toList());
    assertEquals(ImmutableList.of("REPL", "ISRT", "TERM"), commands);
  }

  @Test
  void malformedDliRemainsUnknown() {
    String text =
        "       IDENTIFICATION DIVISION.\n"
            + "       PROGRAM-ID. BAD-DLI.\n"
            + "       PROCEDURE DIVISION.\n"
            + "           {_EXEC DLI GU INTO (BUFFER END-EXEC|1_}\n"
            + "           GOBACK.\n";
    UseCaseEngine.runTest(
        text,
        ImmutableList.of(),
        ImmutableMap.of(
            "1",
            new Diagnostic(
                new Range(),
                "Unknown EXEC block",
                DiagnosticSeverity.Hint,
                ErrorSource.PARSING.getText())));
  }
}
