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
 *    Amp - stored procedure names and dynamic SQL statement sources
 *    Amp - columns, values, INTO host variables and WHERE condition
 *    Amp - ORDER BY, FETCH FIRST and DECLARE TABLE columns
 *
 */

package org.eclipse.lsp.cobol.implicitDialects.sql.node;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.ToString;
import org.antlr.v4.runtime.ParserRuleContext;
import org.antlr.v4.runtime.misc.Interval;
import org.antlr.v4.runtime.tree.ParseTree;
import org.antlr.v4.runtime.tree.TerminalNode;
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
  /** CALL: the procedure name as written, or the host variable (with its colon) that holds it. */
  @Getter private String procedureName;
  /** PREPARE, EXECUTE and DECLARE CURSOR FOR a prepared statement: the statement name. */
  @Getter private String statementName;
  /** PREPARE and EXECUTE IMMEDIATE: the host variable or string the SQL text comes from. */
  @Getter private String sqlSource;
  /** INSERT column list, SELECT list or UPDATE SET columns, as written. */
  @Getter private final List<String> columns = new ArrayList<>();
  /** INSERT VALUES, UPDATE SET and SET assignment values as written, in the order of the columns. */
  @Getter private final List<String> values = new ArrayList<>();
  /** Host variables that receive values: SELECT INTO, FETCH INTO and SET targets, with colons. */
  @Getter private final List<String> into = new ArrayList<>();
  /** The statement's own WHERE condition as written, not a subquery's. */
  @Getter private String where;
  /** The statement's own ORDER BY sort keys as written, such as "ACCT_ID DESC". */
  @Getter private String orderBy;
  /** The statement's own row limit as written, such as "FETCH FIRST 10 ROWS ONLY". */
  @Getter private String fetchFirst;
  /** DECLARE TABLE column definitions as written, such as "ACCT_ID CHAR(11) NOT NULL". */
  @Getter private final List<String> tableColumns = new ArrayList<>();

  /** Rules whose contents belong to a subquery or expression, not to the statement itself. */
  private static final Set<String> NESTED =
      new HashSet<>(
          Arrays.asList(
              "dbs_select_clause",
              "dbs_from_clause",
              "dbs_search_condition",
              "dbs_insert_values",
              "dbs_update_assignment",
              "target_variable_opts"));

  /**
   * Read resources from grammar rules, excluding column qualifiers and correlation names.
   *
   * @param tree parsed SQL statement
   */
  public void describe(ParserRuleContext tree) {
    tables.clear();
    cursorName = null;
    procedureName = null;
    statementName = null;
    sqlSource = null;
    columns.clear();
    values.clear();
    into.clear();
    where = null;
    orderBy = null;
    fetchFirst = null;
    tableColumns.clear();
    statementType = tree.start.getText().toUpperCase(Locale.ROOT);
    collect(tree, false);
  }

  private void collect(ParseTree tree, boolean nested) {
    if (tree instanceof ParserRuleContext) {
      ParserRuleContext rule = (ParserRuleContext) tree;
      String name = Db2SqlExecParser.ruleNames[rule.getRuleIndex()];
      if (!nested) clauses(rule, name);
      nested |= NESTED.contains(name);
      if ("dbs_declare_cursor".equals(name)) statementType = "DECLARE CURSOR";
      if ("dbs_declare_table".equals(name)) statementType = "DECLARE TABLE";
      if ("dbs_select_into_suffix".equals(name) && "SELECT".equals(statementType)) {
        statementType = "SELECT INTO";
      }
      if ("dbs_cursor_name".equals(name) && cursorName == null) cursorName = rule.getText();
      if ("dbs_call".equals(name)) procedureName = rule.getChild(1).getText();
      if ("dbs_prepare".equals(name)) {
        statementName = rule.getChild(1).getText();
        sqlSource = rule.getChild(rule.getChildCount() - 1).getText();
      }
      if ("dbs_execute_statement".equals(name)) statementName = rule.getChild(0).getText();
      if ("dbs_execute_immediate".equals(name)) {
        statementType = "EXECUTE IMMEDIATE";
        sqlSource = text((ParserRuleContext) rule.getChild(1));
      }
      if ("dbs_declare_cursor".equals(name)) {
        ParseTree last = rule.getChild(rule.getChildCount() - 1);
        if (last instanceof ParserRuleContext
            && "dbs_sql_identifier"
                .equals(Db2SqlExecParser.ruleNames[((ParserRuleContext) last).getRuleIndex()])) {
          statementName = last.getText();
        }
      }
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
    for (int i = 0; i < tree.getChildCount(); i++) collect(tree.getChild(i), nested);
  }

  private void clauses(ParserRuleContext rule, String name) {
    switch (name) {
      case "dbs_insert":
        add(columns, rule, "dbs_column_name");
        break;
      case "dbs_select_clause":
        if (columns.isEmpty()) {
          add(columns, rule, "dbs_select_item");
          if (columns.isEmpty() && rule.getChild(rule.getChildCount() - 1) instanceof TerminalNode) {
            columns.add(rule.getChild(rule.getChildCount() - 1).getText());
          }
        }
        break;
      case "dbs_insert_values":
        if (!(rule.getChild(1) instanceof ParserRuleContext)) break; // INSERT ... SELECT
        ParserRuleContext single = (ParserRuleContext) rule.getChild(1);
        if (single.getChild(0) instanceof TerminalNode && "(".equals(single.getChild(0).getText())) {
          ParserRuleContext list = (ParserRuleContext) single.getChild(1);
          for (ParseTree item : list.children) {
            boolean comma =
                item instanceof ParserRuleContext
                    && "dbs_comma_separator"
                        .equals(Db2SqlExecParser.ruleNames[((ParserRuleContext) item).getRuleIndex()]);
            if (!comma) values.add(clean(item));
          }
        } else {
          values.add(unwrap(clean(single))); // VALUES (:X) parses as one parenthesized expression
        }
        break;
      case "dbs_update_assignment":
        add(columns, rule, "dbs_column_name");
        for (ParseTree item : rule.children) {
          String child = item instanceof ParserRuleContext
              ? Db2SqlExecParser.ruleNames[((ParserRuleContext) item).getRuleIndex()]
              : item.getText().toUpperCase(Locale.ROOT);
          if (Arrays.asList("dbs_expressions", "dbs_fullselect", "DEFAULT", "NULL").contains(child)) {
            values.add(clean(item));
          }
        }
        break;
      case "target_variable_opts":
        if (rule.getChildCount() == 3
            && "dbs_sql_variable_reference"
                .equals(Db2SqlExecParser.ruleNames[((ParserRuleContext) rule.getChild(0)).getRuleIndex()])) {
          into.add(clean(rule.getChild(0)));
          values.add(clean(rule.getChild(2)));
        } else {
          add(into, (ParserRuleContext) rule.getChild(0), "dbs_sql_variable_reference");
          values.add(clean(rule.getChild(2)));
        }
        break;
      case "dbs_fetch_singlerow":
      case "dbs_fetch_multirow":
      case "target_variable_names_loop":
        add(into, rule, "dbs_sql_variable_reference");
        break;
      case "dbs_orderby_clause":
        if (orderBy == null) orderBy = clean(rule).replaceFirst("(?i)^ORDER\\s+BY\\s+", "");
        break;
      case "dbs_fetch_clause":
        if (fetchFirst == null) fetchFirst = clean(rule);
        break;
      case "dbs_declare_table_loop":
        tableColumns.add(clean(rule));
        break;
      case "dbs_search_condition":
        ParseTree before = previousSibling(rule);
        if (where == null && before != null && "WHERE".equalsIgnoreCase(before.getText())) {
          where = clean(rule);
        }
        break;
      default:
        break;
    }
  }

  private static void add(List<String> list, ParserRuleContext rule, String childRule) {
    if (rule.children == null) return;
    for (ParseTree child : rule.children) {
      if (child instanceof ParserRuleContext
          && childRule.equals(Db2SqlExecParser.ruleNames[((ParserRuleContext) child).getRuleIndex()])) {
        list.add(clean(child));
      }
    }
  }

  /** "(X)" without its outer parentheses, when they enclose the whole text. */
  private static String unwrap(String text) {
    if (!text.startsWith("(") || !text.endsWith(")")) return text;
    int depth = 0;
    for (int i = 0; i < text.length(); i++) {
      if (text.charAt(i) == '(') depth++;
      if (text.charAt(i) == ')') depth--;
      if (depth == 0 && i < text.length() - 1) return text;
    }
    return text.substring(1, text.length() - 1).trim();
  }

  private static ParseTree previousSibling(ParserRuleContext rule) {
    ParserRuleContext parent = rule.getParent();
    if (parent == null) return null;
    int index = parent.children.indexOf(rule);
    return index > 0 ? parent.getChild(index - 1) : null;
  }

  private static String clean(ParseTree tree) {
    if (!(tree instanceof ParserRuleContext)) return tree.getText();
    return text((ParserRuleContext) tree).replaceAll("\\s+", " ").trim();
  }

  private static String text(ParserRuleContext rule) {
    return rule.start.getInputStream()
        .getText(Interval.of(rule.start.getStartIndex(), rule.stop.getStopIndex()));
  }

  public ExecSqlNode(Locality location) {
    super(location, NodeType.STATEMENT, Db2SqlDialect.DIALECT_NAME);
  }
}
