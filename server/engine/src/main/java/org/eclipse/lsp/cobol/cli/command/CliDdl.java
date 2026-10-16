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
 *    Amp - read tables, columns, keys, indexes and views from Db2 DDL files
 *
 */
package org.eclipse.lsp.cobol.cli.command;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import java.io.File;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.regex.Pattern;
import org.antlr.v4.runtime.BaseErrorListener;
import org.antlr.v4.runtime.CharStreams;
import org.antlr.v4.runtime.CommonTokenStream;
import org.antlr.v4.runtime.ParserRuleContext;
import org.antlr.v4.runtime.RecognitionException;
import org.antlr.v4.runtime.Recognizer;
import org.antlr.v4.runtime.misc.Interval;
import org.antlr.v4.runtime.tree.ParseTree;
import org.antlr.v4.runtime.tree.TerminalNode;
import org.eclipse.lsp.cobol.implicitDialects.sql.Db2SqlExecLexer;
import org.eclipse.lsp.cobol.implicitDialects.sql.Db2SqlExecParser;
import picocli.CommandLine;

/**
 * Parses Db2 DDL files with the same grammar as embedded SQL and prints, for each file, one line of
 * JSON with its tables (columns, primary key, unique keys and foreign keys), ALTER TABLE additions,
 * indexes and views, and the statements that did not parse.
 */
@CommandLine.Command(
    name = "ddl",
    description = "print the tables, keys, indexes and views in Db2 DDL files, one JSON per file")
public class CliDdl implements Callable<Integer> {
  private static final Pattern SCHEMA_STATEMENT =
      Pattern.compile(
          "\\s*(CREATE\\s+(UNIQUE\\s+)?(TABLE|INDEX|VIEW)|ALTER\\s+TABLE)\\b",
          Pattern.CASE_INSENSITIVE);
  private static final Gson GSON = new GsonBuilder().disableHtmlEscaping().create();

  @CommandLine.Parameters(description = "DDL files")
  private File[] files = {};

  @Override
  public Integer call() throws Exception {
    PrintStream out = new PrintStream(System.out, true, StandardCharsets.UTF_8.name());
    for (File file : files) {
      JsonObject result = describe(new String(Files.readAllBytes(file.toPath()), StandardCharsets.ISO_8859_1));
      result.addProperty("uri", file.toURI().toString());
      out.println(GSON.toJson(result));
    }
    return 0;
  }

  /** One statement of a DDL file and the line it starts on. */
  static final class Statement {
    final String text;
    final int line;

    Statement(String text, int line) {
      this.text = text;
      this.line = line;
    }
  }

  /** The tables, indexes and views a DDL file defines, and the statements that did not parse. */
  static JsonObject describe(String text) {
    JsonObject result = new JsonObject();
    JsonArray objects = new JsonArray();
    JsonArray errors = new JsonArray();
    int other = 0;
    for (Statement raw : split(text)) {
      Statement s = fromCreateOrAlter(raw);
      if (s == null) {
        other++;
        continue;
      }
      List<String> problems = new ArrayList<>();
      Db2SqlExecLexer lexer = new Db2SqlExecLexer(CharStreams.fromString(s.text));
      Db2SqlExecParser parser = new Db2SqlExecParser(new CommonTokenStream(lexer));
      BaseErrorListener listener =
          new BaseErrorListener() {
            @Override
            public void syntaxError(
                Recognizer<?, ?> recognizer, Object symbol, int line, int column, String msg,
                RecognitionException e) {
              // ANTLR lists every token it would accept; the first part says what went wrong.
              String brief = msg.replaceAll(" expecting \\{[^}]{120,}\\}", "");
              problems.add("line " + (s.line + line - 1) + ": " + brief);
            }
          };
      lexer.removeErrorListeners();
      lexer.addErrorListener(listener);
      parser.removeErrorListeners();
      parser.addErrorListener(listener);
      ParserRuleContext tree = parser.startSqlRule();
      if (!problems.isEmpty()) {
        JsonObject error = new JsonObject();
        error.addProperty("line", s.line);
        String flat = s.text.trim().replaceAll("\\s+", " ");
        error.addProperty("statement", flat.substring(0, Math.min(80, flat.length())));
        error.addProperty("message", problems.get(0));
        errors.add(error);
        continue;
      }
      JsonObject object = object(tree);
      if (object == null) {
        other++;
        continue;
      }
      object.addProperty("line", s.line);
      objects.add(object);
    }
    result.add("objects", objects);
    result.add("errors", errors);
    result.addProperty("otherStatements", other);
    return result;
  }

  /**
   * Statements split at semicolons outside quotes, with SQL comments and JCL lines removed and
   * numeric sequence numbers in columns 73 to 80 cut off.
   */
  static List<Statement> split(String text) {
    List<Statement> statements = new ArrayList<>();
    StringBuilder current = new StringBuilder();
    int start = -1;
    boolean quoted = false;
    String[] lines = text.split("\r?\n", -1);
    for (int n = 0; n < lines.length; n++) {
      String line = lines[n];
      if (line.length() > 72 && line.substring(72).trim().matches("[0-9]*")) line = line.substring(0, 72);
      if (!quoted && (line.startsWith("//") || line.trim().equals("/*"))) {
        if (start >= 0) current.append('\n');
        continue;
      }
      for (int i = 0; i < line.length(); i++) {
        char c = line.charAt(i);
        if (!quoted && c == '-' && i + 1 < line.length() && line.charAt(i + 1) == '-') break;
        if (c == '\'') quoted = !quoted;
        if (!quoted && c == ';') {
          if (start >= 0) statements.add(new Statement(current.toString(), start));
          current.setLength(0);
          start = -1;
          continue;
        }
        if (start < 0 && !Character.isWhitespace(c)) start = n + 1;
        if (start >= 0) current.append(c);
      }
      if (start >= 0) current.append('\n');
    }
    if (start >= 0 && !current.toString().trim().isEmpty()) statements.add(new Statement(current.toString(), start));
    return statements;
  }

  /**
   * The statement from its first line that starts CREATE TABLE, INDEX or VIEW or ALTER TABLE, so
   * commands that precede the SQL in a JCL in-stream data set (such as DSN and RUN) are dropped;
   * null if there is none. Procedures, functions and triggers are left to other readers: their
   * bodies hold semicolons, so they do not split into whole statements here.
   */
  static Statement fromCreateOrAlter(Statement s) {
    String[] lines = s.text.split("\n", -1);
    for (int i = 0; i < lines.length; i++) {
      if (SCHEMA_STATEMENT.matcher(lines[i]).lookingAt()) {
        return new Statement(String.join("\n", Arrays.copyOfRange(lines, i, lines.length)), s.line + i);
      }
    }
    return null;
  }

  private static JsonObject object(ParserRuleContext tree) {
    ParserRuleContext table = find(tree, "dbs_create_table");
    if (table != null) return table("TABLE", table);
    ParserRuleContext alter = find(tree, "dbs_alter_table");
    if (alter != null) return table("ALTER TABLE", alter);
    ParserRuleContext index = find(tree, "dbs_create_index");
    if (index != null) return index(index);
    ParserRuleContext view = find(tree, "dbs_create_view");
    return view == null ? null : view(view);
  }

  private static JsonObject table(String kind, ParserRuleContext rule) {
    JsonObject table = new JsonObject();
    table.addProperty("kind", kind);
    table.addProperty("name", name(child(rule, "dbs_table_name")));
    JsonArray columns = new JsonArray();
    JsonArray primaryKey = new JsonArray();
    JsonArray unique = new JsonArray();
    JsonArray foreignKeys = new JsonArray();
    for (ParserRuleContext column : all(rule, "columnn_def")) {
      JsonObject c = new JsonObject();
      c.addProperty("name", name(column.getChild(0)));
      for (ParseTree part : children(column)) {
        String partName = ruleName(part);
        if ("common_built_in_type_core3".equals(partName) || "dbs_distinct_type_name".equals(partName)) {
          c.addProperty("type", text(part));
        }
        if ("column_def_clause".equals(partName)) c.addProperty("default", text(part));
      }
      c.addProperty("notNull", hasTokens(column, "NOT", "NULL"));
      columns.add(c);
      for (ParserRuleContext constraint : all(column, "column_constraint")) {
        ParserRuleContext reference = child(constraint, "common_reference_clause");
        if (reference != null) {
          foreignKeys.add(foreignKey(c.get("name").getAsString(), reference));
        } else if (hasTokens(constraint, "PRIMARY", "KEY")) {
          primaryKey.add(c.get("name").getAsString());
        } else if (constraint.getText().toUpperCase(Locale.ROOT).contains("UNIQUE")) {
          JsonArray key = new JsonArray();
          key.add(c.get("name").getAsString());
          unique.add(key);
        }
      }
    }
    for (ParserRuleContext key : all(rule, "unique_constraint")) {
      JsonArray names = names(key, "dbs_column_name_without_alias");
      if (hasTokens(key, "PRIMARY", "KEY")) primaryKey.addAll(names);
      else unique.add(names);
    }
    for (ParserRuleContext key : all(rule, "referential_constraint")) {
      JsonObject fk = foreignKey(null, child(key, "common_reference_clause"));
      fk.add("columns", names(child(key, "referential_constraint_body"), "dbs_column_name_without_alias"));
      foreignKeys.add(fk);
    }
    table.add("columns", columns);
    table.add("primaryKey", primaryKey);
    table.add("unique", unique);
    table.add("foreignKeys", foreignKeys);
    return table;
  }

  private static JsonObject foreignKey(String column, ParserRuleContext reference) {
    JsonObject fk = new JsonObject();
    JsonArray columns = new JsonArray();
    if (column != null) columns.add(column);
    fk.add("columns", columns);
    fk.addProperty("references", name(child(reference, "dbs_table_name")));
    fk.add("referencedColumns", names(reference, "dbs_column_name_without_alias"));
    String text = text(reference).toUpperCase(Locale.ROOT);
    int onDelete = text.indexOf("ON DELETE");
    if (onDelete >= 0) fk.addProperty("onDelete", text.substring(onDelete + 10).split(" (NOT|ENFORCED|ENABLE)")[0].trim());
    return fk;
  }

  private static JsonObject index(ParserRuleContext rule) {
    JsonObject index = new JsonObject();
    index.addProperty("kind", "INDEX");
    index.addProperty("name", name(child(rule, "dbs_index_name")));
    index.addProperty("unique", rule.getChild(0) instanceof TerminalNode && "UNIQUE".equalsIgnoreCase(rule.getChild(0).getText()));
    ParserRuleContext def = child(rule, "dbs_create_index_table_def");
    index.addProperty("table", name(child(def, "dbs_table_name")));
    JsonArray columns = new JsonArray();
    for (ParserRuleContext body : all(def, "dbs_create_index_table_def_body")) columns.add(text(body));
    index.add("columns", columns);
    return index;
  }

  private static JsonObject view(ParserRuleContext rule) {
    JsonObject view = new JsonObject();
    view.addProperty("kind", "VIEW");
    view.addProperty("name", name(child(rule, "dbs_view_name")));
    Set<String> tables = new LinkedHashSet<>();
    for (ParserRuleContext table : all(rule, "dbs_table_name")) tables.add(name(table));
    JsonArray from = new JsonArray();
    tables.forEach(from::add);
    view.add("tables", from);
    return view;
  }

  private static String ruleName(ParseTree tree) {
    return tree instanceof ParserRuleContext
        ? Db2SqlExecParser.ruleNames[((ParserRuleContext) tree).getRuleIndex()]
        : null;
  }

  private static List<ParseTree> children(ParserRuleContext rule) {
    List<ParseTree> out = new ArrayList<>();
    for (int i = 0; i < rule.getChildCount(); i++) out.add(rule.getChild(i));
    return out;
  }

  /** The first rule with this name in the tree, in pre-order. */
  private static ParserRuleContext find(ParseTree tree, String name) {
    if (name.equals(ruleName(tree))) return (ParserRuleContext) tree;
    for (int i = 0; i < tree.getChildCount(); i++) {
      ParserRuleContext found = find(tree.getChild(i), name);
      if (found != null) return found;
    }
    return null;
  }

  /** The first direct child rule with this name. */
  private static ParserRuleContext child(ParserRuleContext rule, String name) {
    if (rule == null) return null;
    for (ParseTree child : children(rule)) {
      if (name.equals(ruleName(child))) return (ParserRuleContext) child;
    }
    return find(rule, name);
  }

  private static List<ParserRuleContext> all(ParseTree tree, String name) {
    List<ParserRuleContext> out = new ArrayList<>();
    if (tree == null) return out;
    if (name.equals(ruleName(tree))) {
      out.add((ParserRuleContext) tree);
      return out;
    }
    for (int i = 0; i < tree.getChildCount(); i++) out.addAll(all(tree.getChild(i), name));
    return out;
  }

  private static JsonArray names(ParserRuleContext rule, String name) {
    JsonArray out = new JsonArray();
    for (ParserRuleContext item : all(rule, name)) out.add(name(item));
    return out;
  }

  private static boolean hasTokens(ParserRuleContext rule, String first, String second) {
    List<ParseTree> parts = children(rule);
    for (int i = 0; i + 1 < parts.size(); i++) {
      if (parts.get(i) instanceof TerminalNode && parts.get(i + 1) instanceof TerminalNode
          && first.equalsIgnoreCase(parts.get(i).getText()) && second.equalsIgnoreCase(parts.get(i + 1).getText())) {
        return true;
      }
    }
    return false;
  }

  /** A name in capitals without quotes, as programs refer to it. */
  private static String name(ParseTree tree) {
    return tree == null ? null : text(tree).replace("\"", "").replaceAll("\\s+", "").toUpperCase(Locale.ROOT);
  }

  private static String text(ParseTree tree) {
    if (!(tree instanceof ParserRuleContext)) return tree.getText();
    ParserRuleContext rule = (ParserRuleContext) tree;
    if (rule.start == null || rule.stop == null || rule.stop.getStopIndex() < rule.start.getStartIndex()) return "";
    return rule.start.getInputStream()
        .getText(Interval.of(rule.start.getStartIndex(), rule.stop.getStopIndex()))
        .replaceAll("\\s+", " ")
        .trim();
  }
}
