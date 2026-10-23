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
package org.eclipse.lsp.cobol.common.model.tree;

import java.util.List;
import lombok.Getter;

/**
 * The grammar structure of one statement or clause, so that no part of the source is lost.
 *
 * <p>{@code rule} is the grammar rule, which names the role of the part (for example {@code
 * moveToSendingArea}). When a chain of rules has one child each, they become one entry: {@code
 * rule} is the outermost and {@code kind} the innermost, such as {@code variableUsageName} or
 * {@code literal}. A part with one token has {@code text}; a longer part has {@code items}, each a
 * keyword or operator string or a nested {@code Syntax}. A nested statement is written as {@code
 * {"rule": "statement", "text": verb}}, since it has its own node.
 */
@Getter
public final class Syntax {
  private final String rule;
  private final String kind;
  private final String text;
  private final List<Object> items;

  public Syntax(String rule, String kind, String text, List<Object> items) {
    this.rule = rule;
    this.kind = kind;
    this.text = text;
    this.items = items;
  }
}
