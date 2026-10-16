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
 *    Amp - verify OCCURS DEPENDING ON on final variable nodes
 *
 */
package org.eclipse.lsp.cobol.usecases;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.gson.Gson;
import java.util.Map;
import java.util.stream.Collectors;
import org.eclipse.lsp.cobol.common.model.tree.Node;
import org.eclipse.lsp.cobol.common.model.tree.variable.MultiTableDataNameNode;
import org.eclipse.lsp.cobol.common.model.tree.variable.OccursClause;
import org.eclipse.lsp.cobol.common.model.tree.variable.TableDataNameNode;
import org.eclipse.lsp.cobol.common.model.tree.variable.VariableNode;
import org.eclipse.lsp.cobol.test.engine.UseCaseEngine;
import org.junit.jupiter.api.Test;

/** Group and elementary tables keep their OCCURS range and DEPENDING ON object. */
class TestOccursDependingOn {
  @Test
  void test() {
    String text =
        "       IDENTIFICATION DIVISION.\n"
            + "       PROGRAM-ID. ODOTEST.\n"
            + "       DATA DIVISION.\n"
            + "       WORKING-STORAGE SECTION.\n"
            + "       01 {$*COUNTS}.\n"
            + "          05 {$*NUM-MEDS} PIC 99 COMP-3.\n"
            + "       01 {$*MEDS}.\n"
            + "          05 {$*MED} OCCURS 0 TO 50 TIMES\n"
            + "                DEPENDING ON {$NUM-MEDS} OF {$COUNTS}.\n"
            + "             10 {$*MED-ID} PIC 9(10).\n"
            + "          05 {$*CODES} PIC X(2) OCCURS 1 TO 9 DEPENDING ON {$NUM-MEDS}.\n"
            + "          05 {$*FIXED} PIC X OCCURS 3.\n"
            + "       PROCEDURE DIVISION.\n"
            + "           GOBACK.\n";
    Node root = UseCaseEngine.runTest(text, ImmutableList.of(), ImmutableMap.of()).getRootNode();
    Map<String, VariableNode> variables =
        root.getDepthFirstStream()
            .filter(VariableNode.class::isInstance)
            .map(VariableNode.class::cast)
            .collect(Collectors.toMap(VariableNode::getName, v -> v));

    OccursClause med = ((MultiTableDataNameNode) variables.get("MED")).getOccursClause();
    assertEquals(0, med.getFrom());
    assertEquals(50, med.getTo());
    assertEquals("NUM-MEDS OF COUNTS", med.getDependingOn());

    OccursClause codes = ((TableDataNameNode) variables.get("CODES")).getOccursClause();
    assertEquals(1, codes.getFrom());
    assertEquals(9, codes.getTo());
    assertEquals("NUM-MEDS", codes.getDependingOn());

    OccursClause fixed = ((TableDataNameNode) variables.get("FIXED")).getOccursClause();
    assertEquals(3, fixed.getFrom());
    assertNull(fixed.getTo());
    assertNull(fixed.getDependingOn());

    String json = new Gson().toJson(variables.get("CODES"));
    assertEquals(true, json.contains("\"dependingOn\":\"NUM-MEDS\""));
  }
}
