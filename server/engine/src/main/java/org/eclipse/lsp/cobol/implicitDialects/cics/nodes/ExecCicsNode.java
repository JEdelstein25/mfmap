/*
 * Copyright (c) 2023 Broadcom.
 * The term "Broadcom" refers to Broadcom Inc. and/or its subsidiaries.
 *
 * This program and the accompanying materials are made
 * available under the terms of the Eclipse Public License 2.0
 * which is available at https://www.eclipse.org/legal/epl-2.0/
 *
 * SPDX-License-Identifier: EPL-2.0
 *
 * Contributors:
 *    Broadcom - initial API and implementation
 *    Amp - preserve CICS command and option metadata
 *
 */

package org.eclipse.lsp.cobol.implicitDialects.cics.nodes;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.ToString;
import org.antlr.v4.runtime.ParserRuleContext;
import org.antlr.v4.runtime.tree.ParseTree;
import org.antlr.v4.runtime.tree.TerminalNode;
import org.eclipse.lsp.cobol.common.model.Locality;
import org.eclipse.lsp.cobol.common.model.NodeType;
import org.eclipse.lsp.cobol.common.model.tree.Node;
import org.eclipse.lsp.cobol.implicitDialects.cics.CICSDialect;
import org.eclipse.lsp.cobol.implicitDialects.cics.CICSParser;

/** EXEC CICS block node */
@ToString(callSuper = true)
@EqualsAndHashCode(callSuper = true)
public class ExecCicsNode extends Node {
  @Getter private String command = "";
  @Getter private final List<Option> options = new ArrayList<>();

  /** An ordered command option, with a null value for flag options. */
  @Getter
  public static class Option {
    private final String name;
    private final String value;

    public Option(String name, String value) {
      this.name = name;
      this.value = value;
    }
  }

  /**
   * Populate metadata from the matched command rule without changing semantic children.
   *
   * @param rule matched CICS command
   */
  public void describe(ParserRuleContext rule) {
    options.clear();
    List<TerminalNode> tokens = new ArrayList<>();
    collectTokens(rule, tokens);
    if (tokens.isEmpty()) return;
    command = tokens.get(0).getText().toUpperCase(Locale.ROOT);
    int index = 1;
    while (index < tokens.size()) {
      String name = tokens.get(index++).getText().toUpperCase(Locale.ROOT);
      String value = null;
      if (index < tokens.size() && "(".equals(tokens.get(index).getText())) {
        int start = tokens.get(index++).getSymbol().getStopIndex() + 1;
        int depth = 1;
        while (index < tokens.size() && depth > 0) {
          String text = tokens.get(index++).getText();
          if ("(".equals(text)) depth++;
          if (")".equals(text)) depth--;
        }
        int end = tokens.get(index - 1).getSymbol().getStartIndex() - 1;
        value =
            rule.start.getInputStream().getText(org.antlr.v4.runtime.misc.Interval.of(start, end));
      }
      options.add(new Option(name, value));
    }
    String qualifier = commandQualifier(rule, "cics_" + command.toLowerCase(Locale.ROOT) + "_");
    if (qualifier != null) {
      command += " " + qualifier;
      options.removeIf(option -> qualifier.equals(option.name) && option.value == null);
    }
  }

  private String commandQualifier(ParseTree tree, String prefix) {
    if (tree instanceof ParserRuleContext) {
      String name = CICSParser.ruleNames[((ParserRuleContext) tree).getRuleIndex()];
      if (name.startsWith(prefix)) {
        String[] parts = name.substring(prefix.length()).toUpperCase(Locale.ROOT).split("_");
        for (String part : parts) {
          for (Option option : options) {
            if (part.equals(option.name)) return part;
          }
        }
      }
    }
    for (int i = 0; i < tree.getChildCount(); i++) {
      String qualifier = commandQualifier(tree.getChild(i), prefix);
      if (qualifier != null) return qualifier;
    }
    return null;
  }

  private static void collectTokens(ParseTree tree, List<TerminalNode> tokens) {
    if (tree instanceof TerminalNode) tokens.add((TerminalNode) tree);
    else for (int i = 0; i < tree.getChildCount(); i++) collectTokens(tree.getChild(i), tokens);
  }

  public ExecCicsNode(Locality location) {
    super(location, NodeType.STATEMENT, CICSDialect.DIALECT_NAME);
  }
}
