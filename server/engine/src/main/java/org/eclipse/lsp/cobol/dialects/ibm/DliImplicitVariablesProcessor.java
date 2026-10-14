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
 *    Amp - define the DL/I interface block for programs with EXEC DLI
 *
 */
package org.eclipse.lsp.cobol.dialects.ibm;

import org.eclipse.lsp.cobol.common.model.Locality;
import org.eclipse.lsp.cobol.common.model.SectionType;
import org.eclipse.lsp.cobol.common.model.tree.ExecDliNode;
import org.eclipse.lsp.cobol.common.model.tree.ProgramNode;
import org.eclipse.lsp.cobol.common.model.tree.SectionNode;
import org.eclipse.lsp.cobol.common.model.tree.variable.ElementaryItemNode;
import org.eclipse.lsp.cobol.common.model.tree.variable.GroupItemNode;
import org.eclipse.lsp.cobol.common.model.tree.variable.UsageFormat;
import org.eclipse.lsp.cobol.common.model.tree.variable.VariableNode;
import org.eclipse.lsp.cobol.common.processor.ProcessingContext;
import org.eclipse.lsp.cobol.common.processor.Processor;
import org.eclipse.lsp.cobol.common.utils.ImplicitCodeUtils;

/**
 * Defines the DL/I interface block (DIB) fields in the working storage of a program that uses EXEC
 * DLI, as the IMS translator does. The field layout is IBM's documented COBOL layout; the group name
 * DIB is this fork's, since programs refer only to the fields.
 */
public class DliImplicitVariablesProcessor implements Processor<SectionNode> {
  private static final String[][] FIELDS = {
    {"DIBVER", "X(2)"},
    {"DIBSTAT", "X(2)"},
    {"DIBSEGM", "X(8)"},
    {"DIBFIL01", "X"},
    {"DIBFIL02", "X"},
    {"DIBSEGLV", "X(2)"},
    {"DIBKFBL", "S9(4)"},
    {"DIBDBDNM", "X(8)"},
    {"DIBDBORG", "X(8)"},
    {"DIBFIL03", "X(6)"}
  };

  @Override
  public void accept(SectionNode section, ProcessingContext ctx) {
    ProgramNode program = ctx.getCurrentProgramNode();
    if (section.getSectionType() != SectionType.WORKING_STORAGE
        || program == null
        || program.findFirstNodeInSubtree(ExecDliNode.class::isInstance) == null) {
      return;
    }
    Locality locality =
        Locality.builder().uri(ImplicitCodeUtils.createFullUrl("implicit-code-DIB")).build();
    VariableNode dib =
        new GroupItemNode(locality, 1, "DIB", false, false, UsageFormat.UNDEFINED, false);
    for (String[] field : FIELDS) {
      UsageFormat usage = field[0].equals("DIBKFBL") ? UsageFormat.COMP : UsageFormat.UNDEFINED;
      dib.addChild(
          new ElementaryItemNode(
              locality, 2, field[0], false, field[1], null, usage, false, false, false));
    }
    ctx.getVariableAccumulator().addVariableDefinition(program, dib);
    dib.getChildren().stream()
        .map(VariableNode.class::cast)
        .forEach(field -> ctx.getVariableAccumulator().addVariableDefinition(program, field));
  }
}
