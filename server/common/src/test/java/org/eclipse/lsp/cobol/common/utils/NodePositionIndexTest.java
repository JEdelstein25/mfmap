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
 *    Amp - check NodePositionIndex against RangeUtils.findNodeByPosition
 *
 */
package org.eclipse.lsp.cobol.common.utils;

import static org.junit.jupiter.api.Assertions.assertSame;

import java.util.Random;
import org.eclipse.lsp.cobol.common.model.Locality;
import org.eclipse.lsp.cobol.common.model.NodeType;
import org.eclipse.lsp.cobol.common.model.tree.CopyNode;
import org.eclipse.lsp.cobol.common.model.tree.Node;
import org.eclipse.lsp4j.Location;
import org.eclipse.lsp4j.Position;
import org.eclipse.lsp4j.Range;
import org.junit.jupiter.api.Test;

/** The index must return exactly what the full tree walk returns, also after insertions. */
class NodePositionIndexTest {
  private static final String PROGRAM = "file:///PROGRAM.cbl";
  private static final String COPYBOOK = "file:///COPYBOOK.cpy";

  @Test
  void matchesTheFullWalkOnRandomTreesBeforeAndAfterInsertions() {
    Random random = new Random(42);
    for (int tree = 0; tree < 200; tree++) {
      Node root = node(PROGRAM, 0, 1000);
      grow(root, PROGRAM, 0, 1000, 0, random);
      NodePositionIndex index = new NodePositionIndex();
      for (int lookup = 0; lookup < 60; lookup++) {
        String uri = random.nextInt(4) == 0 ? COPYBOOK : PROGRAM;
        Position position = new Position(random.nextInt(1100) - 50, random.nextInt(3));
        assertSame(
            RangeUtils.findNodeByPosition(root, uri, position).orElse(null),
            index.find(root, uri, position).orElse(null),
            "tree " + tree + ", lookup " + lookup);
        if (random.nextBoolean()) {
          // Insert where the lookup pointed, as the parser does with EXEC blocks and COPY nodes.
          Node parent = index.find(root, uri, position).orElse(root);
          int line = Math.max(0, position.getLine());
          Node child =
              random.nextInt(5) == 0
                  ? copy(uri, line, random.nextBoolean() ? COPYBOOK : PROGRAM)
                  : node(uri, line, line + random.nextInt(3));
          parent.addChild(child);
          index.added(parent, child);
        }
      }
    }
  }

  private static void grow(
      Node parent, String uri, int from, int to, int depth, Random random) {
    if (depth > 4 || to - from < 2) return;
    int children = 1 + random.nextInt(5);
    int width = (to - from) / children;
    for (int i = 0; i < children; i++) {
      int start = from + i * width;
      int end = start + Math.max(1, width - 1);
      Node child;
      if (random.nextInt(8) == 0) {
        child = copy(uri, start, COPYBOOK);
      } else if (random.nextInt(6) == 0) {
        // Text expanded from a copybook keeps the copybook's positions.
        child = node(COPYBOOK, random.nextInt(50), 50 + random.nextInt(50));
        grow(child, COPYBOOK, 0, 100, depth + 1, random);
      } else {
        child = node(uri, start, end);
        grow(child, uri, start, end, depth + 1, random);
      }
      parent.addChild(child);
    }
  }

  private static Node node(String uri, int startLine, int endLine) {
    return new Node(locality(uri, startLine, endLine), NodeType.STATEMENT) {};
  }

  private static Node copy(String uri, int line, String copybookUri) {
    return new CopyNode(
        locality(uri, line, line),
        new Location(uri, new Range(new Position(line, 0), new Position(line, 1))),
        "CPY",
        copybookUri);
  }

  private static Locality locality(String uri, int startLine, int endLine) {
    return Locality.builder()
        .uri(uri)
        .range(new Range(new Position(startLine, 0), new Position(endLine, 1)))
        .build();
  }
}
