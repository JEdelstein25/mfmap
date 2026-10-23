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
 *    Amp - keep the parse tree of a statement in the syntax tree
 *
 */
package org.eclipse.lsp.cobol.core.visitor;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;
import org.antlr.v4.runtime.ParserRuleContext;
import org.antlr.v4.runtime.Token;
import org.antlr.v4.runtime.tree.ParseTree;
import org.antlr.v4.runtime.tree.TerminalNode;
import org.eclipse.lsp.cobol.common.model.tree.Syntax;

/** Turns a parse tree into a {@link Syntax}, keeping every token and the rule it belongs to. */
public final class SyntaxBuilder {
  private final String[] ruleNames;
  private final Predicate<ParserRuleContext> nested;
  private final Function<ParserRuleContext, String> verb;
  private final Function<Token, String> tokenText;

  /**
   * @param ruleNames the parser's rule names
   * @param nested rules that have their own node and are written as a stub
   * @param verb the text of a stub, or null to leave out a rule that continues the previous one
   * @param tokenText the text of a token
   */
  public SyntaxBuilder(
      String[] ruleNames,
      Predicate<ParserRuleContext> nested,
      Function<ParserRuleContext, String> verb,
      Function<Token, String> tokenText) {
    this.ruleNames = ruleNames;
    this.nested = nested;
    this.verb = verb;
    this.tokenText = tokenText;
  }

  /**
   * Build the syntax of a rule.
   *
   * @param rule the root rule
   * @return its syntax, or null if it has no tokens
   */
  public Syntax build(ParserRuleContext rule) {
    return rule(rule, true);
  }

  private Syntax rule(ParserRuleContext rule, boolean root) {
    String outer = ruleNames[rule.getRuleIndex()];
    if (!root && nested.test(rule)) {
      String text = verb.apply(rule);
      return text == null ? null : new Syntax("statement", null, text, null);
    }
    ParserRuleContext current = rule;
    String kind = outer;
    while (current.getChildCount() == 1
        && current.getChild(0) instanceof ParserRuleContext
        && !nested.test((ParserRuleContext) current.getChild(0))) {
      current = (ParserRuleContext) current.getChild(0);
      String name = ruleNames[current.getRuleIndex()];
      if (!"cobolWord".equals(name)) kind = name;
    }
    if (kind.equals(outer)) kind = null;
    if (current.getChildCount() == 1 && current.getChild(0) instanceof TerminalNode) {
      String text = token((TerminalNode) current.getChild(0));
      return text == null ? null : new Syntax(outer, kind, text, null);
    }
    List<Object> items = new ArrayList<>();
    for (int i = 0; i < current.getChildCount(); i++) {
      ParseTree child = current.getChild(i);
      Object item =
          child instanceof TerminalNode
              ? token((TerminalNode) child)
              : child instanceof ParserRuleContext ? rule((ParserRuleContext) child, false) : null;
      if (item != null) items.add(item);
    }
    return items.isEmpty() ? null : new Syntax(outer, kind, null, items);
  }

  private String token(TerminalNode node) {
    Token token = node.getSymbol();
    if (token.getType() == Token.EOF) return null;
    return tokenText.apply(token);
  }
}
