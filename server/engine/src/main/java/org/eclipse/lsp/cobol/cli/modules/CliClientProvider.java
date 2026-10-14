/*
 * Copyright (c) 2020 Broadcom.
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
 *    Amp - provide safe defaults and headless client callbacks
 *
 */

package org.eclipse.lsp.cobol.cli.modules;

import com.google.inject.Provider;
import com.google.inject.Singleton;
import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import lombok.Setter;
import lombok.extern.slf4j.Slf4j;
import org.eclipse.lsp.cobol.common.copybook.CopyBookDTO;
import org.eclipse.lsp.cobol.core.model.extendedapi.ExtendedApiResult;
import org.eclipse.lsp.cobol.lsp.DialectItemDTO;
import org.eclipse.lsp.cobol.lsp.jrpc.CobolLanguageClient;
import org.eclipse.lsp.cobol.lsp.jrpc.DialectProcessingResult;
import org.eclipse.lsp4j.*;

@Slf4j
@Singleton
public class CliClientProvider implements Provider<CobolLanguageClient> {
  private final CliClient client = new CliClient();
  @Setter private List<File> cpyPaths = Collections.emptyList();
  @Setter private List<String> cpyExt = Collections.emptyList();

  /** The CliClientProvider class is a provider for the CobolLanguageClient interface. */
  public CliClientProvider() {}

  @Override
  public CobolLanguageClient get() {
    return client;
  }

  class CliClient implements CobolLanguageClient {

    @Override
    public void telemetryEvent(Object object) {}

    @Override
    public void publishDiagnostics(PublishDiagnosticsParams diagnostics) {}

    @Override
    public void showMessage(MessageParams messageParams) {}

    @Override
    public CompletableFuture<MessageActionItem> showMessageRequest(
        ShowMessageRequestParams requestParams) {
      return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletableFuture<List<Object>> configuration(ConfigurationParams configurationParams) {
      return CompletableFuture.completedFuture(null);
    }

    @Override
    public void logMessage(MessageParams message) {}

    @Override
    public CompletableFuture<ApplyWorkspaceEditResponse> applyEdit(ApplyWorkspaceEditParams params) {
      return CompletableFuture.completedFuture(new ApplyWorkspaceEditResponse(false));
    }

    @Override
    public CompletableFuture<Void> registerCapability(RegistrationParams params) {
      return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletableFuture<Void> unregisterCapability(UnregistrationParams params) {
      return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletableFuture<ShowDocumentResult> showDocument(ShowDocumentParams params) {
      return CompletableFuture.completedFuture(new ShowDocumentResult(false));
    }

    @Override
    public CompletableFuture<List<WorkspaceFolder>> workspaceFolders() {
      return CompletableFuture.completedFuture(Collections.emptyList());
    }

    @Override
    public CompletableFuture<Void> createProgress(WorkDoneProgressCreateParams params) {
      return CompletableFuture.completedFuture(null);
    }

    @Override
    public void notifyProgress(ProgressParams params) {}

    @Override
    public void logTrace(LogTraceParams params) {}

    @Override
    public CompletableFuture<Void> refreshSemanticTokens() {
      return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletableFuture<Void> refreshCodeLenses() {
      return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletableFuture<Void> refreshInlayHints() {
      return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletableFuture<Void> refreshInlineValues() {
      return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletableFuture<Void> refreshDiagnostics() {
      return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletableFuture<List<DialectItemDTO>> availableDialects() {
      return CompletableFuture.completedFuture(Collections.emptyList());
    }

    @Override
    public CompletableFuture<String> resolveSubroutine(String name) {
      return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletableFuture<String> getFileContent(String uri) {
      return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletableFuture<Void> downloadCopybooks(
        String uri, List<CopyBookDTO> copybooks, boolean quietMode) {
      return CompletableFuture.completedFuture(null);
    }

    @Override
    public void cfastReady(ExtendedApiResult result) {}

    @Override
    public CompletableFuture<DialectProcessingResult> processDialect(
        String dialectName, String programUri, String text) {
      return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletableFuture<String> resolveCopybookUri(
        String cobolFileUri, String copybookName, String dialectType) {
      for (File sp : cpyPaths) {
        for (String ext : cpyExt) {
          String copybookFileName =
              copybookName + (ext.isEmpty() || ext.startsWith(".") ? ext : "." + ext);
          Path spPath = sp.toPath();
          // absolute paths are used as-is
          // relative paths are resolved against the CLI process's current working directory.
          Path cpyFolder =
              spPath.isAbsolute() ? spPath : Paths.get("").toAbsolutePath().resolve(spPath);
          Path cpy = cpyFolder.resolve(copybookFileName).normalize();

          Path relativePath = cpyFolder.relativize(cpy);
          if (relativePath.startsWith("..")) {
            LOG.warn("{} is ignored for copybook resolution", cpy);
            continue;
          }
          if (Files.exists(cpy)) {
            String value = cpy.toUri().toString();
            return CompletableFuture.completedFuture(value);
          }
        }
      }
      return CompletableFuture.completedFuture(null);
    }
  }
}
