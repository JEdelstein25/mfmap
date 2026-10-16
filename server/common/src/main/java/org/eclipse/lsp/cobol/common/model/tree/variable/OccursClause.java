/*
 * Copyright (c) 2021 Broadcom.
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
 *    Amp - keep the OCCURS DEPENDING ON object
 *
 */
package org.eclipse.lsp.cobol.common.model.tree.variable;

import java.util.List;
import lombok.AllArgsConstructor;
import lombok.Value;

/** The class represents occurs clause in COBOL. */
@Value
@AllArgsConstructor
public class OccursClause {
  Integer from;
  Integer to;
  boolean isUnbounded;
  List<VariableNameAndLocality> indexed;
  /** DEPENDING ON: the data name as written, or null. */
  String dependingOn;

  public OccursClause(
      Integer from, Integer to, boolean isUnbounded, List<VariableNameAndLocality> indexed) {
    this(from, to, isUnbounded, indexed, null);
  }
}
