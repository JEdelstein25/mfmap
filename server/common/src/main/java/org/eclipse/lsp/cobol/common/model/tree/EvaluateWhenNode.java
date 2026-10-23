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
 *    Amp - keep where the WHEN condition is
 *
 */
package org.eclipse.lsp.cobol.common.model.tree;

import lombok.ToString;
import lombok.Getter;
import lombok.Setter;
import org.eclipse.lsp.cobol.common.model.Locality;
import org.eclipse.lsp.cobol.common.model.NodeType;

/** The class represents evaluateWhen in COBOL. */
@ToString(callSuper = true)
public class EvaluateWhenNode extends Node {
  /** Where what follows WHEN, including ALSO objects, is in the source. */
  @Getter @Setter private Locality conditionLocality;

  public EvaluateWhenNode(Locality location) {
    super(location, NodeType.EVALUATE_WHEN);
  }
}
