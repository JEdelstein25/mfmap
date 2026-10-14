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
 *    Amp - find nodes by position without walking unrelated subtrees
 *
 */
package org.eclipse.lsp.cobol.common.utils;

import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.Optional;
import org.eclipse.lsp.cobol.common.model.Locality;
import org.eclipse.lsp.cobol.common.model.tree.CopyNode;
import org.eclipse.lsp.cobol.common.model.tree.Node;
import org.eclipse.lsp4j.Position;
import org.eclipse.lsp4j.Range;

/**
 * Gives the same answers as {@link RangeUtils#findNodeByPosition} but skips subtrees that cannot
 * contribute, so many lookups in one tree no longer walk the whole tree each time.
 *
 * <p>{@code findNodeByPosition} only returns something from a subtree when a node in it is a COPY
 * of the uri or contains the position in the uri. For each subtree this index remembers, per uri,
 * whether it holds such a COPY and the span of its nodes in the uri. A subtree with no COPY and a
 * span that excludes the position is skipped. Call {@link #added} after adding a child and {@link
 * #changed} after removing children, so what is known stays exact.
 */
public final class NodePositionIndex {
  /** What a node's descendants hold for one uri. */
  private static final class Summary {
    boolean copy;
    boolean unknown; // a descendant without a complete range; never skip it
    Position min;
    Position max;
  }

  private final Map<String, Map<Node, Summary>> summaries = new HashMap<>();

  /**
   * Find the node {@link RangeUtils#findNodeByPosition} would find.
   *
   * @param node the root of the search
   * @param uri the uri of the position
   * @param position the position
   * @return the found node
   */
  public Optional<Node> find(Node node, String uri, Position position) {
    Map<Node, Summary> byNode = summaries.computeIfAbsent(uri, u -> new IdentityHashMap<>());
    return find(node, uri, position, byNode);
  }

  /**
   * Record a child just added under {@code parent}: extend what is known about the parent and its
   * ancestors instead of recomputing them.
   *
   * @param parent the node the child was added to
   * @param child the added node
   */
  public void added(Node parent, Node child) {
    for (Map.Entry<String, Map<Node, Summary>> entry : summaries.entrySet()) {
      Summary contribution = new Summary();
      add(contribution, child, entry.getKey());
      Summary below = summary(child, entry.getKey(), entry.getValue());
      contribution.copy |= below.copy;
      contribution.unknown |= below.unknown;
      extend(contribution, below.min, below.max);
      for (Node n = parent; n != null; n = n.getParent()) {
        Summary known = entry.getValue().get(n);
        if (known == null) continue;
        known.copy |= contribution.copy;
        known.unknown |= contribution.unknown;
        extend(known, contribution.min, contribution.max);
      }
    }
  }

  /**
   * Forget what is known about a node whose children changed, and about its ancestors.
   *
   * @param node the node whose children were added or removed
   */
  public void changed(Node node) {
    for (Node n = node; n != null; n = n.getParent()) {
      for (Map<Node, Summary> byNode : summaries.values()) {
        byNode.remove(n);
      }
    }
  }

  private Optional<Node> find(
      Node node, String uri, Position position, Map<Node, Summary> byNode) {
    Node candidate = null;
    for (Node child : node.getChildren()) {
      if (isFromCopybook(uri, child)) {
        candidate = RangeUtils.getCandidate(uri, child, candidate);
      }
      if (RangeUtils.isInside(uri, position, child.getLocality())) {
        candidate = RangeUtils.getCandidate(uri, child, candidate);
      }
      if (canSkip(summary(child, uri, byNode), position)) {
        continue;
      }
      Optional<Node> nodeByPosition = find(child, uri, position, byNode);
      if (nodeByPosition.isPresent()) {
        return Optional.ofNullable(RangeUtils.getCandidate(uri, nodeByPosition.get(), candidate));
      }
    }
    return Optional.ofNullable(candidate);
  }

  private static boolean canSkip(Summary s, Position position) {
    if (s.unknown || s.copy) return false;
    return s.min == null || compare(position, s.min) < 0 || compare(position, s.max) > 0;
  }

  /** What the descendants of {@code node} (not the node itself) hold for {@code uri}. */
  private Summary summary(Node node, String uri, Map<Node, Summary> byNode) {
    Summary cached = byNode.get(node);
    if (cached != null) return cached;
    Summary s = new Summary();
    for (Node child : node.getChildren()) {
      add(s, child, uri);
      Summary below = summary(child, uri, byNode);
      s.copy |= below.copy;
      s.unknown |= below.unknown;
      extend(s, below.min, below.max);
    }
    byNode.put(node, s);
    return s;
  }

  private static void add(Summary s, Node node, String uri) {
    s.copy |= isFromCopybook(uri, node);
    Locality locality = node.getLocality();
    if (locality == null) {
      s.unknown = true;
      return;
    }
    if (!uri.equals(locality.getUri())) return;
    Range range = locality.getRange();
    if (range == null || range.getStart() == null || range.getEnd() == null) {
      s.unknown = true;
      return;
    }
    extend(s, range.getStart(), range.getEnd());
  }

  private static void extend(Summary s, Position min, Position max) {
    if (min == null) return;
    if (s.min == null || compare(min, s.min) < 0) s.min = min;
    if (s.max == null || compare(max, s.max) > 0) s.max = max;
  }

  private static boolean isFromCopybook(String uri, Node node) {
    return node instanceof CopyNode && uri.equals(((CopyNode) node).getUri());
  }

  private static int compare(Position first, Position second) {
    int lines = Integer.compare(first.getLine(), second.getLine());
    return lines == 0 ? Integer.compare(first.getCharacter(), second.getCharacter()) : lines;
  }
}
