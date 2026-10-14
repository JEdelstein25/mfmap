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
 *    Amp - serialize the final syntax tree with node IDs and references by ID
 *
 */
package org.eclipse.lsp.cobol.cli.command;

import com.google.gson.ExclusionStrategy;
import com.google.gson.FieldAttributes;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.TypeAdapter;
import com.google.gson.TypeAdapterFactory;
import com.google.gson.reflect.TypeToken;
import com.google.gson.stream.JsonReader;
import com.google.gson.stream.JsonWriter;
import java.io.IOException;
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;
import org.eclipse.lsp.cobol.common.model.Locality;
import org.eclipse.lsp.cobol.common.model.tree.Node;

/**
 * Serializes a syntax tree as the graph output described in {@code schema/graph-v1.schema.json}.
 *
 * <p>Every node gets an {@code id} (its pre-order position, for example {@code n42}) and a {@code
 * kind} (its Java class name). Children are nested in {@code children}. A field that points to
 * another node is written as {@code {"ref": "n42"}}; a node outside the tree is written as {@code
 * {"kind", "nodeType", "locality"}} without a {@code ref}.
 */
final class AstGraphSerializer {
  static final int SCHEMA_VERSION = 1;

  private final Map<Node, String> ids = new IdentityHashMap<>();
  private final Map<Class<?>, TypeAdapter<Node>> fieldAdapters = new HashMap<>();
  private final TypeAdapterFactory references = new ReferenceAdapterFactory();
  private final Gson gson =
      new GsonBuilder()
          .disableHtmlEscaping()
          .setExclusionStrategies(new ChildrenExclusion())
          .registerTypeAdapterFactory(references)
          .create();

  private AstGraphSerializer(Node root) {
    root.getDepthFirstStream().forEach(node -> ids.put(node, "n" + ids.size()));
  }

  /**
   * Serialize a tree.
   *
   * @param root the tree root
   * @return the root node with nested children
   */
  static JsonObject serialize(Node root) {
    return new AstGraphSerializer(root).node(root);
  }

  private JsonObject node(Node node) {
    JsonObject result = new JsonObject();
    result.addProperty("id", ids.get(node));
    result.addProperty("kind", kind(node));
    fieldAdapter(node.getClass())
        .toJsonTree(node)
        .getAsJsonObject()
        .entrySet()
        .forEach(entry -> result.add(entry.getKey(), entry.getValue()));
    JsonArray children = new JsonArray();
    node.getChildren().forEach(child -> children.add(node(child)));
    result.add("children", children);
    return result;
  }

  @SuppressWarnings("unchecked")
  private TypeAdapter<Node> fieldAdapter(Class<?> type) {
    // The delegate is Gson's reflective adapter; node-valued fields inside it use the reference
    // adapter.
    return fieldAdapters.computeIfAbsent(
        type, t -> (TypeAdapter<Node>) gson.getDelegateAdapter(references, TypeToken.get(t)));
  }

  private static String kind(Node node) {
    String name = node.getClass().getSimpleName();
    return name.isEmpty() ? node.getClass().getName() : name;
  }

  private static final class ChildrenExclusion implements ExclusionStrategy {
    @Override
    public boolean shouldSkipField(FieldAttributes field) {
      return field.getDeclaringClass() == Node.class && "children".equals(field.getName());
    }

    @Override
    public boolean shouldSkipClass(Class<?> type) {
      return false;
    }
  }

  private final class ReferenceAdapterFactory implements TypeAdapterFactory {
    @Override
    @SuppressWarnings("unchecked")
    public <T> TypeAdapter<T> create(Gson gson, TypeToken<T> type) {
      if (!Node.class.isAssignableFrom(type.getRawType())) return null;
      TypeAdapter<Locality> locality = gson.getAdapter(Locality.class);
      return (TypeAdapter<T>)
          new TypeAdapter<Node>() {
            @Override
            public void write(JsonWriter out, Node node) throws IOException {
              if (node == null) {
                out.nullValue();
                return;
              }
              out.beginObject();
              String id = ids.get(node);
              if (id != null) {
                out.name("ref").value(id);
              } else {
                out.name("kind").value(kind(node));
                out.name("nodeType").value(node.getNodeType().name());
                out.name("locality");
                locality.write(out, node.getLocality());
              }
              out.endObject();
            }

            @Override
            public Node read(JsonReader in) {
              throw new UnsupportedOperationException("graph output is write-only");
            }
          };
    }
  }
}
