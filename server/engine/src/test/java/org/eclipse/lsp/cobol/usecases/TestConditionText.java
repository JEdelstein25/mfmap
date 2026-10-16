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
 *    Amp - verify where IF, PERFORM UNTIL and EVALUATE conditions are
 *
 */
package org.eclipse.lsp.cobol.usecases;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.gson.Gson;
import java.util.List;
import java.util.stream.Collectors;
import org.eclipse.lsp.cobol.common.model.Locality;
import org.eclipse.lsp.cobol.common.model.tree.EvaluateNode;
import org.eclipse.lsp.cobol.common.model.tree.EvaluateWhenNode;
import org.eclipse.lsp.cobol.common.model.tree.IfNode;
import org.eclipse.lsp.cobol.common.model.tree.Node;
import org.eclipse.lsp.cobol.common.model.tree.PerformUntilNode;
import org.eclipse.lsp.cobol.test.engine.UseCaseEngine;
import org.eclipse.lsp4j.Range;
import org.junit.jupiter.api.Test;

/** Statement nodes point at their conditions in the source, operators and literals included. */
class TestConditionText {
  @Test
  void test() {
    String text =
        "       IDENTIFICATION DIVISION.\n"
            + "       PROGRAM-ID. CONDTEST.\n"
            + "       DATA DIVISION.\n"
            + "       WORKING-STORAGE SECTION.\n"
            + "       01 {$*A} PIC 9.\n"
            + "       01 {$*B} PIC 9.\n"
            + "       PROCEDURE DIVISION.\n"
            + "           IF {$A} > 1 AND\n"
            + "              NOT {$B} = 2\n"
            + "              IF {$A} < 5 CONTINUE END-IF\n"
            + "              IF {$A} = DFHRESP(NORMAL) CONTINUE END-IF\n"
            + "           END-IF\n"
            + "           PERFORM UNTIL {$A} >= {$B}\n"
            + "              ADD 1 TO {$A}\n"
            + "           END-PERFORM\n"
            + "           EVALUATE {$A} ALSO TRUE\n"
            + "              WHEN 1 THRU 3 ALSO {$B} > 0\n"
            + "                 CONTINUE\n"
            + "              WHEN OTHER\n"
            + "                 CONTINUE\n"
            + "           END-EVALUATE\n"
            + "           GOBACK.\n";
    Node root = UseCaseEngine.runTest(text, ImmutableList.of(), ImmutableMap.of()).getRootNode();
    String[] lines = text.replaceAll("\\{\\$\\*?([^}]*)}", "$1").split("\n");
    List<String> ifs =
        root.getDepthFirstStream()
            .filter(IfNode.class::isInstance)
            .map(n -> source(lines, ((IfNode) n).getConditionLocality()))
            .collect(Collectors.toList());
    assertEquals(ImmutableList.of("A > 1 AND NOT B = 2", "A < 5", "A = DFHRESP(NORMAL)"), ifs);
    PerformUntilNode until =
        (PerformUntilNode)
            root.getDepthFirstStream().filter(PerformUntilNode.class::isInstance).findFirst().get();
    assertEquals("A >= B", source(lines, until.getConditionLocality()));
    EvaluateNode evaluate =
        (EvaluateNode)
            root.getDepthFirstStream().filter(EvaluateNode.class::isInstance).findFirst().get();
    assertEquals("A ALSO TRUE", source(lines, evaluate.getSubjectLocality()));
    EvaluateWhenNode when =
        (EvaluateWhenNode)
            root.getDepthFirstStream().filter(EvaluateWhenNode.class::isInstance).findFirst().get();
    assertEquals("1 THRU 3 ALSO B > 0", source(lines, when.getConditionLocality()));
    assertTrue(new Gson().toJson(until).contains("\"conditionLocality\":{"));
  }

  /** The text of a range, joined into one line, as a reader of the graph would take it. */
  private static String source(String[] lines, Locality locality) {
    Range range = locality.getRange();
    StringBuilder text = new StringBuilder();
    for (int line = range.getStart().getLine(); line <= range.getEnd().getLine(); line++) {
      int from = line == range.getStart().getLine() ? range.getStart().getCharacter() : 0;
      int to = line == range.getEnd().getLine() ? range.getEnd().getCharacter() : lines[line].length();
      text.append(lines[line], from, to).append(' ');
    }
    return text.toString().replaceAll("\\s+", " ").trim();
  }
}
