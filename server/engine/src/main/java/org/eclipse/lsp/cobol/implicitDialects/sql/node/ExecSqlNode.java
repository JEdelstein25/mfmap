/*
 * Copyright (c) 2024 Broadcom.
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
 *    Amp - preserve SQL statement and resource metadata
 *
 */

package org.eclipse.lsp.cobol.implicitDialects.sql.node;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.ToString;
import org.antlr.v4.runtime.ParserRuleContext;
import org.antlr.v4.runtime.tree.ParseTree;
import org.eclipse.lsp.cobol.common.model.Locality;
import org.eclipse.lsp.cobol.common.model.NodeType;
import org.eclipse.lsp.cobol.common.model.tree.Node;
import org.eclipse.lsp.cobol.implicitDialects.sql.Db2SqlDialect;
import org.eclipse.lsp.cobol.implicitDialects.sql.Db2SqlExecParser;

/** EXEC SQL block node */
@ToString(callSuper = true)
@EqualsAndHashCode(callSuper = true)
public class ExecSqlNode extends Node {
  @Getter private String statementType = "";
  @Getter private final List<String> tables = new ArrayList<>();
  @Getter private String cursorName;

  /**
   * Read resources from grammar rules, excluding column qualifiers and correlation names.
   *
   * @param tree parsed SQL statement
   */
  public void describe(ParserRuleContext tree) {
    tables.clear();
    cursorName = null;
    statementType = tree.start.getText().toUpperCase(Locale.ROOT);
    collect(tree);
  }

  private void collect(ParseTree tree) {
    if (tree instanceof ParserRuleContext) {
      ParserRuleContext rule = (ParserRuleContext) tree;
      String name = Db2SqlExecParser.ruleNames[rule.getRuleIndex()];
      if ("dbs_declare_cursor".equals(name)) statementType = "DECLARE CURSOR";
      if ("dbs_declare_table".equals(name)) statementType = "DECLARE TABLE";
      if ("dbs_select_into_suffix".equals(name) && "SELECT".equals(statementType)) {
        statementType = "SELECT INTO";
      }
      if ("dbs_cursor_name".equals(name) && cursorName == null) cursorName = rule.getText();
      boolean target =
          "dbs_alias_name".equals(name)
              && rule.getParent() instanceof ParserRuleContext
              && ("dbs_insert".equals(Db2SqlExecParser.ruleNames[rule.getParent().getRuleIndex()])
                  || "dbs_update"
                      .equals(Db2SqlExecParser.ruleNames[rule.getParent().getRuleIndex()])
                  || "dbs_delete"
                      .equals(Db2SqlExecParser.ruleNames[rule.getParent().getRuleIndex()])
                  || "dbs_merge".equals(Db2SqlExecParser.ruleNames[rule.getParent().getRuleIndex()])
                  || "dbs_declare_table"
                      .equals(Db2SqlExecParser.ruleNames[rule.getParent().getRuleIndex()]));
      if ("dbs_table_name".equals(name) || "dbs_view_name".equals(name) || target) {
        String table = rule.getText();
        if (!tables.contains(table)) tables.add(table);
        return;
      }
    }
    for (int i = 0; i < tree.getChildCount(); i++) collect(tree.getChild(i));
  }

  public ExecSqlNode(Locality location) {
    super(location, NodeType.STATEMENT, Db2SqlDialect.DIALECT_NAME);
  }
}
