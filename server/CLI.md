<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0

Contributors:
   Amp - document headless analysis and copybook options
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
