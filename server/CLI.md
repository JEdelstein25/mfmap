<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0

Contributors:
   Amp - document headless analysis, copybook options and graph output
-->

# Command-line analysis

Build from `server` with `mvn -Dmaven.test.skip -pl engine -am package`.
Run `java -jar engine/target/server.jar analysis -s /path/program.cbl`.

Use `--ast` to include all eight AST snapshots, as before. Add
`--ast-phase=FINAL` to emit only the last available snapshot under its phase name.
You can also select `START`, `TRANSFORMATION`, `DEFINITION`, `POST_DEFINITION`,
`PRE_USAGE`, `USAGE`, `ENRICHMENT`, or `VALIDATION`. The default is `ALL`.
`--ast-compact-references` keeps the tree's `children` but replaces node references
with objects containing only `nodeType`, `name` when present, and `locality`.
These options reduce output size; snapshots are still captured during analysis.

## Graph output

`--graph` prints only the final syntax tree, in the format described by
[schema/graph-v1.schema.json](../schema/graph-v1.schema.json). It does not capture the eight
snapshots, so it is faster and smaller than `--ast`. The output has `schemaVersion: 1`, `tree`
and `diagnostics`, and no timings or memory statistics, so the same input gives the same output.

- Every node has an `id`, its position in a pre-order walk of the tree (`n0` is the root), and a
  `kind`, its Java class name, such as `ElementaryItemNode` or `ExecCicsNode`.
- Children are nested in `children`.
- A field that points to another node is written as `{"ref": "n42"}`. For example, a
  `VariableUsageNode`'s `definitions` point to the data item it uses.
- A node that is not in the tree, such as an implicit CICS register, is written as its `kind`,
  `nodeType` and `locality`, without `ref`.

IDs are stable for the same source, copybooks and parser version; they change when the source
changes. [toolkit/python](../toolkit/python) reads this output.

Both `analysis` and `cfast` accept repeated `-cf/--copybook-folder` and
`-ce/--copybook-extension` options. Absolute copybook paths are used as given.
In this fork, relative paths resolve from the process's **current working
directory**, not the source file's folder. For example, when running from the
repository root, `-cf ./copybooks` searches the root's `copybooks` directory.
Extensions may include or omit the leading dot. The defaults are an empty
extension and `.cpy`.

Run the following command to write `.cfast.json` files next to `.cbl` inputs.

```sh
java -jar engine/target/server.jar cfast -sf /path/source-folder -cf /path/copybooks -ce cpy
```

The CLI client has no editor UI and returns empty results for editor requests.
