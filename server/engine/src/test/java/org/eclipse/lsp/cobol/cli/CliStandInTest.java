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
 *    Amp - verify the DFHAID and DFHBMSCA stand-ins and the DL/I interface block
 *
 */
package org.eclipse.lsp.cobol.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import org.eclipse.lsp.cobol.cli.command.Cli;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import picocli.CommandLine;

/** Analyses programs through the command line and checks which names resolve. */
class CliStandInTest {
  private static final String HEADER =
      "       IDENTIFICATION DIVISION.\n"
          + "       PROGRAM-ID. STANDIN.\n"
          + "       DATA DIVISION.\n"
          + "       WORKING-STORAGE SECTION.\n"
          + "       COPY DFHAID.\n"
          + "       COPY DFHBMSCA.\n"
          + "       01 WS-ATTR PIC X.\n"
          + "       01 WS-SEG PIC X(8).\n"
          + "       PROCEDURE DIVISION.\n";

  @Test
  void standInsAndDibResolveWithoutCopybookFolders(@TempDir Path dir) throws Exception {
    JsonObject output =
        analyze(
            dir,
            HEADER
                + "           IF EIBAID = DFHPF3\n"
                + "              MOVE DFHBMPRF TO WS-ATTR\n"
                + "           END-IF\n"
                + "           EXEC DLI GU SEGMENT(ROOT) INTO(WS-SEG) END-EXEC\n"
                + "           IF DIBSTAT = SPACES\n"
                + "              MOVE DIBSEGM TO WS-SEG\n"
                + "           END-IF\n"
                + "           GOBACK.\n");
    assertEquals(Collections.emptyList(), errors(output));
    JsonObject pf3 = find(output.getAsJsonObject("tree"), "DFHPF3");
    assertEquals("X'F3'", pf3.get("value").getAsString());
    assertEquals("DFHAID", pf3.getAsJsonObject("locality").get("copybookId").getAsString());
  }

  @Test
  void dibIsDefinedOnlyForProgramsWithExecDli(@TempDir Path dir) throws Exception {
    JsonObject output =
        analyze(dir, HEADER + "           IF DIBSTAT = SPACES\n           GOBACK.\n");
    assertEquals(Collections.singletonList("Variable DIBSTAT is not defined"), errors(output));
  }

  @Test
  void copybookInFolderTakesPrecedence(@TempDir Path dir) throws Exception {
    Path copybooks = Files.createDirectory(dir.resolve("cpy"));
    Files.write(
        copybooks.resolve("DFHAID.cpy"),
        "       01 DFHAID.\n           02 MY-AID PIC X.\n".getBytes(StandardCharsets.UTF_8));
    JsonObject output =
        analyze(
            dir,
            HEADER
                + "           IF EIBAID = MY-AID OR EIBAID = DFHPF3\n"
                + "              GOBACK\n"
                + "           END-IF.\n",
            "-cf",
            copybooks.toString());
    assertEquals(Collections.singletonList("Variable DFHPF3 is not defined"), errors(output));
  }

  private static JsonObject analyze(Path dir, String text, String... options) throws Exception {
    Path source = dir.resolve("STANDIN.cbl");
    Files.write(source, text.getBytes(StandardCharsets.UTF_8));
    List<String> args =
        new ArrayList<>(Arrays.asList("analysis", "-s", source.toString(), "--graph"));
    args.addAll(Arrays.asList(options));
    ByteArrayOutputStream output = new ByteArrayOutputStream();
    PrintStream original = System.out;
    try (PrintStream stream = new PrintStream(output)) {
      System.setOut(stream);
      new CommandLine(new Cli()).execute(args.toArray(new String[0]));
    } finally {
      System.setOut(original);
    }
    return JsonParser.parseString(output.toString()).getAsJsonObject();
  }

  private static List<String> errors(JsonObject output) {
    List<String> messages = new ArrayList<>();
    for (JsonElement diagnostic : output.getAsJsonArray("diagnostics")) {
      JsonObject d = diagnostic.getAsJsonObject();
      if ("ERROR".equals(d.get("severity").getAsString())) {
        messages.add(d.has("message") ? d.get("message").getAsString() : d.toString());
      }
    }
    return messages;
  }

  private static JsonObject find(JsonObject node, String name) {
    if (node.has("name") && name.equals(node.get("name").getAsString()) && node.has("level")) {
      return node;
    }
    for (JsonElement child : node.getAsJsonArray("children")) {
      JsonObject found = find(child.getAsJsonObject(), name);
      if (found != null) return found;
    }
    return null;
  }
}
