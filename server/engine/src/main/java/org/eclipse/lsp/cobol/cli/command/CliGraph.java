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
 *    Amp - analyze many programs in one process
 *
 */
package org.eclipse.lsp.cobol.cli.command;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import com.google.inject.Guice;
import com.google.inject.Injector;
import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.concurrent.Callable;
import org.eclipse.lsp.cobol.cli.di.CliModule;
import org.eclipse.lsp.cobol.cli.modules.CliClientProvider;
import org.eclipse.lsp.cobol.common.dialects.CobolLanguageId;
import org.eclipse.lsp.cobol.common.message.MessageService;
import org.eclipse.lsp.cobol.dialects.ibm.ProcessingResult;
import picocli.CommandLine;

/**
 * Reads program paths from stdin, one per line, and prints each program's graph output (the same
 * object as {@code analysis --graph}) as one line of JSON. One process serves many programs, so
 * start-up and warm-up are paid once.
 */
@CommandLine.Command(
    name = "graph",
    description = "print graph output for each program path read from stdin, one JSON per line")
public class CliGraph implements Callable<Integer> {
  private static final Gson GSON = new GsonBuilder().disableHtmlEscaping().create();

  @CommandLine.ParentCommand private Cli parent;

  @CommandLine.Option(
      description = "Supported dialect values: ${COMPLETION-CANDIDATES}",
      names = {"-d", "--dialect"},
      defaultValue = "COBOL")
  private CobolLanguageId dialect;

  @CommandLine.Option(
      names = {"-cf", "--copybook-folder"},
      description = "Copybook folder. Relative paths resolve from the current working directory.")
  private File[] cpyPaths = {};

  @CommandLine.Option(
      names = {"-ce", "--copybook-extension"},
      description = "List of copybook extensions.")
  private String[] cpyExt = {"", ".cpy"};

  @Override
  public Integer call() throws Exception {
    // Analysis may write to stdout; keep it for the protocol and send everything else to stderr.
    PrintStream protocol = new PrintStream(System.out, true, StandardCharsets.UTF_8.name());
    System.setOut(System.err);
    Injector diCtx = Guice.createInjector(new CliModule());
    CliClientProvider client = diCtx.getInstance(CliClientProvider.class);
    client.setCpyPaths(Arrays.asList(cpyPaths));
    client.setCpyExt(Arrays.asList(cpyExt));
    MessageService messages = diCtx.getInstance(MessageService.class);
    BufferedReader input =
        new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
    for (String line = input.readLine(); line != null; line = input.readLine()) {
      if (line.trim().isEmpty()) continue;
      File src = new File(line.trim());
      JsonObject result = new JsonObject();
      result.addProperty("uri", src.toURI().toString());
      result.addProperty("language", dialect.getId());
      try {
        Cli.Result analysis = parent.runAnalysis(src, dialect, diCtx, true, false);
        result.addProperty("schemaVersion", AstGraphSerializer.SCHEMA_VERSION);
        result.add(
            "tree",
            AstGraphSerializer.serialize(
                ((ProcessingResult) analysis.pipelineResult.getLastStageResult().getData())
                    .getRootNode()));
        CliAnalysis.generateDiagnostics(analysis, result, messages);
      } catch (Exception | StackOverflowError e) {
        result = new JsonObject();
        result.addProperty("uri", src.toURI().toString());
        result.addProperty("language", dialect.getId());
        result.addProperty("crash", String.valueOf(e.getMessage() != null ? e.getMessage() : e));
      }
      protocol.println(GSON.toJson(result));
    }
    return Cli.SUCCESS;
  }
}
