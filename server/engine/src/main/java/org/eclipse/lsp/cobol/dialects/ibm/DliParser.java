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
 *    Amp - recognize balanced EXEC DLI blocks without changing other EXEC handling
 *
 */
package org.eclipse.lsp.cobol.dialects.ibm;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.function.BiFunction;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.eclipse.lsp.cobol.common.model.Locality;
import org.eclipse.lsp.cobol.common.model.tree.ExecDliNode;
import org.eclipse.lsp.cobol.common.model.tree.variable.QualifiedReferenceNode;
import org.eclipse.lsp.cobol.common.model.tree.variable.VariableUsageNode;

/** Small parser for the opaque UNKNOWN_EXEC token; quoted strings and nested arguments are kept. */
final class DliParser {
  private static final Pattern BLOCK =
      Pattern.compile("(?is)^EXEC\\s+DLI\\s+([A-Z][A-Z0-9-]*)\\b(.*?)END-EXEC$");
  private static final Pattern WORD = Pattern.compile("[A-Za-z][A-Za-z0-9-]*");
  private static final Pattern HOST = Pattern.compile("\\s*([A-Za-z][A-Za-z0-9-]*)\\s*");
  private static final Pattern LITERAL = Pattern.compile("'([^']|'')*'|\"([^\"]|\"\")*\"");
  private static final Pattern WHERE_HOST =
      Pattern.compile(
          "(?:=|>=|<=|>|<|\\bEQ\\b|\\bNE\\b)\\s*([A-Za-z][A-Za-z0-9-]*)", Pattern.CASE_INSENSITIVE);

  private DliParser() {}

  static ExecDliNode parse(
      String text, Locality locality, BiFunction<Integer, Integer, Locality> location) {
    Matcher block = BLOCK.matcher(text);
    if (!block.matches()) return null;
    String body = block.group(2);
    List<ExecDliNode.Option> options = new ArrayList<>();
    List<VariableUsageNode> usages = new ArrayList<>();
    int offset = 0;
    while (offset < body.length()) {
      if (Character.isWhitespace(body.charAt(offset))) {
        offset++;
        continue;
      }
      Matcher word = WORD.matcher(body).region(offset, body.length());
      if (!word.lookingAt()) return null;
      String name = word.group().toUpperCase(Locale.ROOT);
      offset = word.end();
      while (offset < body.length() && Character.isWhitespace(body.charAt(offset))) offset++;
      String value = null;
      if (offset < body.length() && body.charAt(offset) == '(') {
        int start = ++offset;
        int depth = 1;
        char quote = 0;
        while (offset < body.length() && depth > 0) {
          char c = body.charAt(offset++);
          if (quote != 0) {
            if (c == quote) {
              if (offset < body.length() && body.charAt(offset) == quote) offset++;
              else quote = 0;
            }
          } else if (c == '\'' || c == '"') quote = c;
          else if (c == '(') depth++;
          else if (c == ')') depth--;
        }
        if (depth != 0 || quote != 0) return null;
        value = body.substring(start, offset - 1);
        if (name.equals("INTO") || name.equals("FROM")) {
          Matcher host = HOST.matcher(value);
          if (host.matches()) {
            int position = block.start(2) + start + host.start(1);
            usages.add(
                new VariableUsageNode(
                    host.group(1).toUpperCase(Locale.ROOT),
                    location.apply(position, position + host.group(1).length()),
                    false));
          }
        } else if (name.equals("WHERE")) {
          StringBuilder unquoted = new StringBuilder(value);
          Matcher literal = LITERAL.matcher(value);
          while (literal.find()) {
            for (int i = literal.start(); i < literal.end(); i++) unquoted.setCharAt(i, '~');
          }
          Matcher host = WHERE_HOST.matcher(unquoted);
          while (host.find()) {
            int position = block.start(2) + start + host.start(1);
            usages.add(
                new VariableUsageNode(
                    host.group(1).toUpperCase(Locale.ROOT),
                    location.apply(position, position + host.group(1).length()),
                    false));
          }
        }
      }
      options.add(new ExecDliNode.Option(name, value));
    }
    ExecDliNode node = new ExecDliNode(locality, block.group(1).toUpperCase(Locale.ROOT), options);
    for (VariableUsageNode usage : usages) {
      QualifiedReferenceNode reference = new QualifiedReferenceNode(usage.getLocality());
      reference.addChild(usage);
      node.addChild(reference);
    }
    return node;
  }
}
