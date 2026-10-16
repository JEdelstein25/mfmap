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
 *    Amp - verify AST selection, compact references, graph output, the graph command and CFAST
 *    Amp - list the ddl command
 *    Amp - verify graph IDs name one node each
 *
 */
package org.eclipse.lsp.cobol.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.eclipse.lsp.cobol.cli.command.Cli;
import org.eclipse.lsp.cobol.cli.command.CliHelp;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.junit.jupiter.MockitoExtension;
import picocli.CommandLine;

/** Test for {@link Cli} */
@ExtendWith(MockitoExtension.class)
class CliTest {
  public static final String EXPECTED_USAGE =
      "Usage: <main class> [-hV] [COMMAND]"
          + System.lineSeparator()
          + "COBOL Analysis CLI tools."
          + System.lineSeparator()
          + "  -h, --help      Show this help message and exit."
          + System.lineSeparator()
          + "  -V, --version   Print version information and exit."
          + System.lineSeparator()
          + "Commands:"
          + System.lineSeparator()
          + "  list_sources    list sources"
          + System.lineSeparator()
          + "  list_copybooks  list copybooks"
          + System.lineSeparator()
          + "  analysis        analyse cobol source"
          + System.lineSeparator()
          + "  cfast           generate cfast from cobol source"
          + System.lineSeparator()
          + "  graph           print graph output for each program path read from stdin, one"
          + System.lineSeparator()
          + "                    JSON per line"
          + System.lineSeparator()
          + "  ddl             print the tables, keys, indexes and views in Db2 DDL files,"
          + System.lineSeparator()
          + "                    one JSON per file"
          + System.lineSeparator();

  @Test
  void testCli_srcNonNull() {
    CommandLine commandLine = new CommandLine(new Cli());
    StringWriter sw = new StringWriter();
    PrintWriter pw = new PrintWriter(sw);
    commandLine.usage(pw);
    pw.flush();
    assertEquals(EXPECTED_USAGE, sw.toString());
  }

  @Test
  void testCli_usage() {
    CommandLine commandLine = new CommandLine(new Cli());
    assertEquals(CommandLine.ExitCode.USAGE, commandLine.execute("-s", "source"));
  }

  @Test
  void testCli_srcNull() {
    CommandLine commandLine = new CommandLine(new Cli());
    assertEquals(CommandLine.ExitCode.OK, commandLine.execute());
  }

  @Test
  void testCliCommands() {
    CommandLine commandLine = new CommandLine(new Cli());
    Set<String> commandList = commandLine.getSubcommands().keySet();
    assertEquals(6, commandList.size());
    assertTrue(commandList.contains("graph"));
    assertTrue(commandList.contains("ddl"));
    assertTrue(commandList.contains("analysis"));
    assertTrue(commandList.contains("list_copybooks"));
    assertTrue(commandList.contains("list_sources"));
    assertTrue(commandList.contains("cfast"));
  }

  @Test
  void testListCopybooksHelp_optionsAreUniformlyIndented() {
    CommandLine commandLine = new CommandLine(new Cli());
    commandLine.setHelpFactory(new CliHelp.Factory());
    StringWriter sw = new StringWriter();
    PrintWriter pw = new PrintWriter(sw);
    commandLine.getSubcommands().get("list_copybooks").usage(pw);
    pw.flush();

    List<String> optionLines =
        Arrays.stream(sw.toString().split(System.lineSeparator()))
            .filter(line -> line.trim().startsWith("-"))
            .collect(Collectors.toList());
    assertEquals(7, optionLines.size());
    Set<Integer> indents =
        optionLines.stream()
            .map(line -> line.length() - line.replaceFirst("^ +", "").length())
            .collect(Collectors.toSet());
    assertEquals(
        Collections.singleton(3),
        indents,
        "every option, whether it has a true short flag (-h) or a multi-character"
            + " mnemonic (-ce, -cf, -ws), should be indented the same amount");
  }

  @Test
  void testAnalysisHelp_everyOptionFitsOnOneLine() {
    CommandLine commandLine = new CommandLine(new Cli());
    commandLine.setHelpFactory(new CliHelp.Factory());
    StringWriter sw = new StringWriter();
    PrintWriter pw = new PrintWriter(sw);
    commandLine.getSubcommands().get("analysis").usage(pw);
    pw.flush();

    // "analysis" has an option whose combined names are unusually long
    // ("-esf, -exf, --save-extended-source=<extendedSourcePath>"), which previously either pushed
    // its own description to a hanging second line, or (once that column was widened to fit it)
    // starved the description column for every other option into wrapping instead. Neither should
    // happen: every option, including this one, should render as exactly one line.
    List<String> optionLines =
        Arrays.stream(sw.toString().split(System.lineSeparator()))
            .filter(line -> line.trim().startsWith("-"))
            .collect(Collectors.toList());
    List<String> nonOptionBodyLines =
        Arrays.stream(sw.toString().split(System.lineSeparator()))
            .filter(line -> line.startsWith("   ") && !line.trim().startsWith("["))
            .filter(line -> !line.trim().isEmpty())
            .collect(Collectors.toList());

    assertEquals(16, optionLines.size());
    assertEquals(
        optionLines.size(),
        nonOptionBodyLines.size(),
        "every non-blank line in the option list should itself start with an option name;"
            + " a mismatch means some description wrapped onto its own line");
  }

  @Test
  void astSelectionAndCompactReferences(@TempDir Path directory) throws Exception {
    Path source = directory.resolve("sample.cbl");
    Files.write(
        source,
        ("       IDENTIFICATION DIVISION.\n"
                + "       PROGRAM-ID. SAMPLE.\n       DATA DIVISION.\n"
                + "       WORKING-STORAGE SECTION.\n       01 FIELD-A PIC X.\n"
                + "       PROCEDURE DIVISION.\n           DISPLAY FIELD-A.\n"
                + "           STOP RUN.\n")
            .getBytes(java.nio.charset.StandardCharsets.UTF_8));
    JsonObject all = analyze(source).getAsJsonObject("asts");
    assertEquals(8, all.size());
    JsonObject last = analyze(source, "--ast-phase=FINAL").getAsJsonObject("asts");
    assertEquals(Collections.singleton("VALIDATION"), last.keySet());
    assertEquals(all.get("VALIDATION"), last.get("VALIDATION"));
    assertEquals(
        Collections.singleton("START"),
        analyze(source, "--ast-phase=START").getAsJsonObject("asts").keySet());
    JsonObject compact =
        analyze(source, "--ast-phase=FINAL", "--ast-compact-references").getAsJsonObject("asts");
    assertTrue(compact.toString().length() < last.toString().length());
    assertTrue(checkReferences(compact.get("VALIDATION"), false) > 0);
    assertChildrenPreserved(
        last.getAsJsonObject("VALIDATION"), compact.getAsJsonObject("VALIDATION"));
    assertEquals(0, new CommandLine(new Cli()).execute("cfast", "-sf", directory.toString()));
    assertTrue(Files.size(directory.resolve("sample.cfast.json")) > 0);
  }

  @Test
  void graphOutputHasNodeIdsAndReferencesById(@TempDir Path directory) throws Exception {
    Path source = directory.resolve("sample.cbl");
    Files.write(
        source,
        ("       IDENTIFICATION DIVISION.\n"
                + "       PROGRAM-ID. SAMPLE.\n       DATA DIVISION.\n"
                + "       WORKING-STORAGE SECTION.\n       01 GROUP-A.\n"
                + "          05 FIELD-A PIC X.\n          05 FIELD-B PIC 9.\n"
                + "       PROCEDURE DIVISION.\n           DISPLAY FIELD-B.\n"
                + "           DISPLAY UNDEF-X.\n           STOP RUN.\n")
            .getBytes(java.nio.charset.StandardCharsets.UTF_8));
    JsonObject output = run("analysis", "-s", source.toString(), "--graph");
    assertEquals(1, output.get("schemaVersion").getAsInt());
    assertTrue(!output.has("asts") && !output.has("timings"));
    assertEquals(
        "Variable UNDEF-X is not defined",
        output.getAsJsonArray("diagnostics").get(0).getAsJsonObject().get("message").getAsString());
    java.util.Map<String, JsonObject> nodes = new java.util.LinkedHashMap<>();
    collectNodes(output.getAsJsonObject("tree"), nodes);
    List<String> expectedIds = new java.util.ArrayList<>();
    for (int i = 0; i < nodes.size(); i++) expectedIds.add("n" + i);
    assertEquals(expectedIds, new java.util.ArrayList<>(nodes.keySet()));

    JsonObject usage =
        nodes.values().stream()
            .filter(n -> "VariableUsageNode".equals(n.get("kind").getAsString()))
            .filter(n -> "FIELD-B".equals(n.get("name").getAsString()))
            .findFirst()
            .orElseThrow(AssertionError::new);
    String target =
        usage.getAsJsonArray("definitions").get(0).getAsJsonObject().get("ref").getAsString();
    assertEquals("ElementaryItemNode", nodes.get(target).get("kind").getAsString());
    assertEquals("FIELD-B", nodes.get(target).get("name").getAsString());
    assertEquals("9", nodes.get(target).get("picClause").getAsString());

    JsonObject last =
        run("analysis", "-s", source.toString(), "--ast", "--ast-phase=FINAL")
            .getAsJsonObject("asts")
            .getAsJsonObject("VALIDATION");
    assertSameTree(last, output.getAsJsonObject("tree"));
  }

  @Test
  void graphIdsNameOneNodeEachWhenACopybookHasValueClauses(@TempDir Path directory)
      throws Exception {
    Path copybooks = Files.createDirectory(directory.resolve("cpy"));
    Files.write(
        copybooks.resolve("CB.cpy"),
        ("       01 GROUP-A.\n          05 FIELD-A PIC X VALUE SPACES.\n"
                + "          05 FIELD-B PIC 9.\n")
            .getBytes(java.nio.charset.StandardCharsets.UTF_8));
    Path source = directory.resolve("DUP.cbl");
    Files.write(
        source,
        ("       IDENTIFICATION DIVISION.\n       PROGRAM-ID. DUP.\n       DATA DIVISION.\n"
                + "       WORKING-STORAGE SECTION.\n       COPY CB.\n"
                + "       PROCEDURE DIVISION.\n           DISPLAY FIELD-B.\n           GOBACK.\n")
            .getBytes(java.nio.charset.StandardCharsets.UTF_8));
    JsonObject output =
        run("analysis", "-s", source.toString(), "-cf", copybooks.toString(), "-ce", "cpy", "--graph");
    java.util.Map<String, List<JsonObject>> byId = new java.util.HashMap<>();
    collectAll(output.getAsJsonObject("tree"), byId);
    byId.forEach(
        (id, nodes) ->
            nodes.forEach(node -> assertEquals(nodes.get(0), node, id + " names two nodes")));
    String target =
        byId.values().stream()
            .map(nodes -> nodes.get(0))
            .filter(n -> "VariableUsageNode".equals(n.get("kind").getAsString()))
            .filter(n -> "FIELD-B".equals(n.get("name").getAsString()))
            .findFirst()
            .orElseThrow(AssertionError::new)
            .getAsJsonArray("definitions")
            .get(0)
            .getAsJsonObject()
            .get("ref")
            .getAsString();
    assertEquals("FIELD-B", byId.get(target).get(0).get("name").getAsString());
  }

  private static void collectAll(JsonObject node, java.util.Map<String, List<JsonObject>> nodes) {
    nodes
        .computeIfAbsent(node.get("id").getAsString(), id -> new java.util.ArrayList<>())
        .add(node);
    node.getAsJsonArray("children").forEach(c -> collectAll(c.getAsJsonObject(), nodes));
  }

  @Test
  void graphCommandServesManyProgramsWithTheSameOutputAsAnalysis(@TempDir Path directory)
      throws Exception {
    Path first = directory.resolve("FIRST.cbl");
    Path second = directory.resolve("SECOND.cbl");
    Files.write(
        first,
        ("       IDENTIFICATION DIVISION.\n       PROGRAM-ID. FIRST.\n"
                + "       PROCEDURE DIVISION.\n           CALL 'SECOND'.\n           GOBACK.\n")
            .getBytes(java.nio.charset.StandardCharsets.UTF_8));
    Files.write(
        second,
        ("       IDENTIFICATION DIVISION.\n       PROGRAM-ID. SECOND.\n"
                + "       PROCEDURE DIVISION.\n           DISPLAY UNDEF-Y.\n           GOBACK.\n")
            .getBytes(java.nio.charset.StandardCharsets.UTF_8));
    ByteArrayOutputStream output = new ByteArrayOutputStream();
    PrintStream originalOut = System.out;
    java.io.InputStream originalIn = System.in;
    try (PrintStream stream = new PrintStream(output)) {
      System.setOut(stream);
      System.setIn(
          new java.io.ByteArrayInputStream(
              (first + "\n\n" + second + "\n").getBytes(java.nio.charset.StandardCharsets.UTF_8)));
      assertEquals(0, new CommandLine(new Cli()).execute("graph"));
    } finally {
      System.setOut(originalOut);
      System.setIn(originalIn);
    }
    String[] lines = output.toString().trim().split("\n");
    assertEquals(2, lines.length);
    assertEquals(
        run("analysis", "-s", first.toString(), "--graph"), JsonParser.parseString(lines[0]));
    assertEquals(
        run("analysis", "-s", second.toString(), "--graph"), JsonParser.parseString(lines[1]));
  }

  private static void collectNodes(JsonObject node, java.util.Map<String, JsonObject> nodes) {
    nodes.put(node.get("id").getAsString(), node);
    node.getAsJsonArray("children").forEach(c -> collectNodes(c.getAsJsonObject(), nodes));
  }

  private static void assertSameTree(JsonObject snapshot, JsonObject graph) {
    for (String key : snapshot.keySet()) {
      assertTrue(graph.has(key), "graph node lacks " + key);
    }
    for (String key : Arrays.asList("nodeType", "name", "locality", "picClause", "level")) {
      assertEquals(snapshot.get(key), graph.get(key));
    }
    com.google.gson.JsonArray children = snapshot.getAsJsonArray("children");
    com.google.gson.JsonArray graphChildren = graph.getAsJsonArray("children");
    assertEquals(children.size(), graphChildren.size());
    for (int i = 0; i < children.size(); i++) {
      assertSameTree(children.get(i).getAsJsonObject(), graphChildren.get(i).getAsJsonObject());
    }
  }

  private static JsonObject run(String... args) {
    ByteArrayOutputStream output = new ByteArrayOutputStream();
    PrintStream original = System.out;
    try (PrintStream stream = new PrintStream(output)) {
      System.setOut(stream);
      assertEquals(0, new CommandLine(new Cli()).execute(args));
    } finally {
      System.setOut(original);
    }
    return JsonParser.parseString(output.toString()).getAsJsonObject();
  }

  private static void assertChildrenPreserved(JsonObject original, JsonObject compact) {
    for (String key : Arrays.asList("nodeType", "name", "locality")) {
      assertEquals(original.get(key), compact.get(key));
    }
    if (original.has("children")) {
      com.google.gson.JsonArray children = original.getAsJsonArray("children");
      com.google.gson.JsonArray compactChildren = compact.getAsJsonArray("children");
      assertEquals(children.size(), compactChildren.size());
      for (int i = 0; i < children.size(); i++) {
        assertChildrenPreserved(
            children.get(i).getAsJsonObject(), compactChildren.get(i).getAsJsonObject());
      }
    }
  }

  private static int checkReferences(com.google.gson.JsonElement element, boolean reference) {
    int count = 0;
    if (element.isJsonArray()) {
      for (com.google.gson.JsonElement item : element.getAsJsonArray()) {
        count += checkReferences(item, reference);
      }
    } else if (element.isJsonObject()) {
      JsonObject object = element.getAsJsonObject();
      if (reference && object.has("nodeType")) {
        assertTrue(Arrays.asList("nodeType", "name", "locality").containsAll(object.keySet()));
        return 1;
      }
      for (String key : object.keySet()) {
        count += checkReferences(object.get(key), !key.equals("children"));
      }
    }
    return count;
  }

  private static JsonObject analyze(Path source, String... options) {
    ByteArrayOutputStream output = new ByteArrayOutputStream();
    PrintStream original = System.out;
    try (PrintStream stream = new PrintStream(output)) {
      System.setOut(stream);
      List<String> args =
          new java.util.ArrayList<>(Arrays.asList("analysis", "-s", source.toString(), "--ast"));
      args.addAll(Arrays.asList(options));
      assertEquals(0, new CommandLine(new Cli()).execute(args.toArray(new String[0])));
    } finally {
      System.setOut(original);
    }
    return JsonParser.parseString(output.toString()).getAsJsonObject();
  }
}
