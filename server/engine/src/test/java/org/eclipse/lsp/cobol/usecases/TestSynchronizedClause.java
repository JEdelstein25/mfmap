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
 *    Amp - verify synchronized metadata on final variable nodes
 *
 */
package org.eclipse.lsp.cobol.usecases;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.util.List;
import java.util.stream.Collectors;
import org.eclipse.lsp.cobol.common.model.tree.variable.VariableNode;
import org.eclipse.lsp.cobol.test.engine.UseCaseEngine;
import org.junit.jupiter.api.Test;

/** Checks preservation of SYNC clauses through variable conversion. */
class TestSynchronizedClause {
  @Test
  void test() {
    String text =
        "       IDENTIFICATION DIVISION.\n"
            + "       PROGRAM-ID. SYNCTEST.\n"
            + "       DATA DIVISION.\n"
            + "       WORKING-STORAGE SECTION.\n"
            + "       01 {$*RESP} PIC S9(8) COMP SYNC.\n"
            + "       01 {$*RESP2} PIC S9(8) COMP SYNCHRONIZED LEFT.\n"
            + "       77 {$*RIGHT-FIELD} PIC S9(8) COMP SYNC RIGHT.\n"
            + "       01 {$*PLAIN} PIC S9(8) COMP.\n"
            + "       PROCEDURE DIVISION.\n"
            + "           GOBACK.\n";
    List<VariableNode> variables =
        UseCaseEngine.runTest(text, ImmutableList.of(), ImmutableMap.of())
            .getRootNode()
            .getDepthFirstStream()
            .filter(VariableNode.class::isInstance)
            .map(VariableNode.class::cast)
            .collect(Collectors.toList());
    for (VariableNode variable : variables) {
      if (variable.getName().equals("RESP")) {
        assertEquals(true, variable.isSynchronizedClause());
        assertNull(variable.getSynchronizedDirection());
      } else if (variable.getName().equals("RESP2")) {
        assertEquals(true, variable.isSynchronizedClause());
        assertEquals("LEFT", variable.getSynchronizedDirection());
      } else if (variable.getName().equals("RIGHT-FIELD")) {
        assertEquals(true, variable.isSynchronizedClause());
        assertEquals("RIGHT", variable.getSynchronizedDirection());
      } else if (variable.getName().equals("PLAIN")) {
        assertEquals(false, variable.isSynchronizedClause());
        assertNull(variable.getSynchronizedDirection());
      }
    }
    assertEquals(4, variables.size());
  }
}
