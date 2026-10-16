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
 *    Amp - keep the grammar structure of statements
 *
 */
package org.eclipse.lsp.cobol.usecases;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import org.eclipse.lsp.cobol.common.model.tree.Node;
import org.eclipse.lsp.cobol.common.model.tree.Syntax;
import org.eclipse.lsp.cobol.test.engine.UseCaseEngine;
import org.junit.jupiter.api.Test;

/** Statements keep their operators, operand roles and replaced CICS text in {@code syntax}. */
class TestStatementSyntax {
  private static final String TEXT =
      "       IDENTIFICATION DIVISION.\n"
          + "       PROGRAM-ID. SYN.\n"
          + "       DATA DIVISION.\n"
          + "       WORKING-STORAGE SECTION.\n"
          + "       01 {$*WS-A} PIC 9(4) VALUE 5.\n"
          + "       01 {$*WS-B} PIC 9(4).\n"
          + "       01 {$*WS-C} PIC X(10).\n"
          + "       01 {$*WS-RESP} PIC S9(8) COMP.\n"
          + "       01 {$*WS-FLAG} PIC X.\n"
          + "          88 {$*FLAG-ON} VALUE 'Y'.\n"
          + "       PROCEDURE DIVISION.\n"
          + "           MOVE {$WS-A} TO {$WS-B} {$WS-C}(2:3)\n"
          + "           COMPUTE {$WS-B} = {$WS-A} - {$WS-B} * 2\n"
          + "           IF {$WS-A} > 1 AND NOT {$FLAG-ON}\n"
          + "              MOVE 'X' TO {$WS-C}\n"
          + "           ELSE\n"
          + "              SET {$FLAG-ON} TO FALSE\n"
          + "           END-IF\n"
          + "           EVALUATE {$WS-RESP}\n"
          + "              WHEN DFHRESP(NOTFND)\n"
          + "                 CONTINUE\n"
          + "           END-EVALUATE\n"
          + "           PERFORM VARYING {$WS-B} FROM 1 BY 1 UNTIL {$WS-B} > 3\n"
          + "              CONTINUE\n"
          + "           END-PERFORM\n"
          + "           IF {$WS-A} > 1\n"
          + "              EXEC CICS SYNCPOINT\n"
          + "              END-EXEC\n"
          + "           END-IF\n"
          + "           CALL {%'SUBPGM'} USING BY CONTENT {$WS-A} BY REFERENCE {$WS-C}\n"
          + "           GOBACK.\n";

  @Test
  void statementsKeepEveryToken() {
    List<Node> statements =
        UseCaseEngine.runTest(TEXT, ImmutableList.of(), ImmutableMap.of())
            .getRootNode()
            .getDepthFirstStream()
            .filter(node -> node.getSyntax() != null)
            .collect(Collectors.toList());
    List<String> flat = statements.stream().map(n -> flat(n.getSyntax())).collect(Collectors.toList());
    assertEquals(
        ImmutableList.of(
            "MOVE moveToSendingArea:WS-A TO generalIdentifier:WS-B"
                + " [variableUsageName:WS-C [( characterPosition:2 : length:3 )]]",
            "COMPUTE computeStore:WS-B = [multDivs:WS-A [- [powers:WS-B [* powers:2]]]]",
            "IF [[arithmeticExpression:WS-A [relationalOperator:> arithmeticExpression:1]]"
                + " AND NOT simpleCondition:FLAG-ON] [statement:MOVE] [ELSE statement:SET] END-IF",
            "MOVE moveToSendingArea:'X' TO generalIdentifier:WS-C",
            "SET [receivingField:FLAG-ON TO booleanLiteral:FALSE]",
            "EVALUATE evaluateSelect:WS-RESP [[WHEN evaluateCondition:DFHRESP(NOTFND)]"
                + " statement:CONTINUE] END-EVALUATE",
            "continueStatement:CONTINUE",
            "PERFORM [[VARYING [generalIdentifier:WS-B [FROM literal:1] [BY literal:1]"
                + " [UNTIL [arithmeticExpression:WS-B [relationalOperator:> arithmeticExpression:3]]]]]"
                + " statement:CONTINUE END-PERFORM]",
            "continueStatement:CONTINUE",
            "IF [arithmeticExpression:WS-A [relationalOperator:> arithmeticExpression:1]]"
                + " [statement:EXEC CICS] END-IF",
            "CALL constantName:'SUBPGM' [USING [BY CONTENT generalIdentifier:WS-A]"
                + " [BY REFERENCE callByReference:WS-C]]",
            "gobackStatement:GOBACK"),
        flat);
  }

  /** Writes a part as "rule:text" or as its items in brackets, dropping the outer statement rule. */
  private static String flat(Syntax syntax) {
    List<String> parts = new ArrayList<>();
    if (syntax.getText() != null) return syntax.getRule() + ":" + syntax.getText();
    for (Object item : syntax.getItems()) {
      if (item instanceof String) parts.add((String) item);
      else {
        Syntax part = (Syntax) item;
        parts.add(part.getText() != null ? flat(part) : "[" + flat(part) + "]");
      }
    }
    String text = String.join(" ", parts);
    // moveStatement wraps moveToStatement; unwrap one level so the expectation stays readable
    return text.startsWith("MOVE [") ? "MOVE " + text.substring(6, text.length() - 1) : text;
  }
}
