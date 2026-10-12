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
 *    Amp - represent IMS DL/I statements and ordered options
 *
 */
package org.eclipse.lsp.cobol.common.model.tree;

import java.util.List;
import lombok.Getter;
import lombok.Value;
import org.eclipse.lsp.cobol.common.model.Locality;
import org.eclipse.lsp.cobol.common.model.NodeType;

/** An EXEC DLI statement, preserving option arguments without interpreting IMS expressions. */
@Getter
public class ExecDliNode extends Node {
  private final String command;
  private final List<Option> options;

  /**
   * Construct a DL/I statement.
   *
   * @param locality statement location
   * @param command upper-case command
   * @param options ordered options
   */
  public ExecDliNode(Locality locality, String command, List<Option> options) {
    super(locality, NodeType.STATEMENT, "dli");
    this.command = command;
    this.options = options;
  }

  /** An option with its original argument text, or null for a flag. */
  @Value
  public static class Option {
    String name;
    String value;
  }
}
