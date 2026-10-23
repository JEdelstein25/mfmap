<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->

# Changing mfmap

When mfmap fails on your code or leaves something out, the fix goes in one of the places below. Each one has an example commit in this repository that made the same kind of change. Read it with `git show <commit>`, then make your change the same way.

| Symptom | Where the fix goes | Example |
|---|---|---|
| `Copybook not found` for a copybook IBM or another vendor supplies (CICS, Db2, IMS, MQ) | Pass the folder that has it with `-cf`. If you don't have the real copybook, add a stand-in under `server/engine/src/main/resources/implicitCopybooks/` and have the dialect supply it when the folders don't have it. Stand-ins for fields a translator or precompiler adds go in a processor such as `DliImplicitVariablesProcessor`. | `80cc631d5` (DFHAID and DFHBMSCA stand-ins, DL/I interface block) |
| `Copybook not found` for a copybook your build generates, such as a BMS symbolic map | Generate the copybooks into a folder outside the application source and pass it with `-cf`. No parser change. For BMS maps, `mfmap bms-copybooks` does it. | `toolkit/python/mfmap/bms.py` |
| A syntax error on code your compiler accepts | The COBOL grammar is `server/parser/src/main/antlr4/org/eclipse/lsp/cobol/core/CobolParser.g4` and `CobolLexer.g4`. Embedded CICS and SQL have their own grammars under `server/engine/src/main/antlr4/org/eclipse/lsp/cobol/implicitDialects/`. A whole new kind of block gets its own parser and node. | `b454c88b1` (EXEC DLI blocks, which were rejected before) |
| A clause parses but is missing from the graph output | Find the visitor that builds the node (`CobolVisitor` for data items) and keep the clause in a field on the node class. Every field of a node is written to `analysis --graph` output automatically. Add the field to `schema/graph-v1.schema.json`. | `7cc501a0a` (SYNC clause on data items) |
| An EXEC CICS, SQL or DLI option or name is missing from the graph | The node's `describe` method in `ExecCicsNode` or `ExecSqlNode` reads it from the embedded grammar's parse tree. | `c56b3c41f` (CICS options, SQL tables and cursors), `8fd1ec34d` (stored procedure names, dynamic SQL) |
| A DDL statement is listed as not parsed on the Parser tab, or a table, key or index is missing from the map | The Db2 grammar, `server/engine/src/main/antlr4/org/eclipse/lsp/cobol/implicitDialects/sql/Db2SqlExecParser.g4`, is shared with embedded SQL, so a fix there helps both. What is read from each statement is in `CliDdl`; the entities it becomes are in `toolkit/python/mfmap/resolvers/ddl.py`. | `CliDdl.java` and `CliDdlTest.java` (FOREIGN KEY constraint names and ERASE without USING) |
| A kind of relationship mfmap doesn't find, such as CICS definitions in another format, another scheduler's export, or another language's programs | Add a resolver module to `toolkit/python/mfmap/resolvers/`, following the closest one: `cics.py` or `jcl.py` for definitions, `scheduler.py` for job order, `web.py` for APIs and the pages that call them, `easytrieve.py` for programs the COBOL parser does not read. | `scheduler.py`, `web.py` and `easytrieve.py` in `toolkit/python/mfmap/resolvers/` |
| A call, read, write or commit point is missing or wrong in `mfmap facts`, but the graph has the detail | `toolkit/python/mfmap/model.py` (`call_edges`, `data_access`, `commit_points`). New kinds of facts also need a table in `store.py`, a line on the Parser tab in `report.py`, and a pattern in `crosscheck.py` if a text search can count them. | Python half of `8fd1ec34d` |

The Map tab of `mfmap serve` has two halves. What each level shows (which entities and relationships become nodes and edges, how they are grouped, their tags, counts, evidence and overlays) is decided on the server in `toolkit/python/mfmap/graph.py`, and `serve.py` answers `/api/graph` from it; the test is `test_graph_endpoint_draws_each_level_from_the_store_plan_and_questions` in `toolkit/python/tests/test_store.py`. How it is drawn (layout, cards, edges, the side panel) is the Svelte Flow app in `toolkit/map/src/`, built into `toolkit/python/mfmap/static/map.js` and `map.css`, which are committed so `mfmap serve` needs no Node or network. After changing `toolkit/map/src/`, rebuild with `npm --prefix toolkit/map ci && npm --prefix toolkit/map run build` (Node 20 or later) and commit the rebuilt files with the source; the build also writes `map.licenses.txt` for the packages in the bundle. Keep the map a view of the data: take groupings, waves and dependencies from `migration.json`, everything else from the store and the questions.

The migration plan's format is [schema/migration-v1.schema.json](schema/migration-v1.schema.json). If you change it, copy it to `toolkit/python/mfmap/`; a test fails until the copies match.

## How to Make a Change

1. **Reproduce it small.** Write the smallest program that shows the problem and look at the parser's output for it:
   ```sh
   java -jar server/engine/target/server.jar analysis -s sample.cbl -cf copybooks --graph > sample.json
   ```
2. **Make the change** where the table says, following the example commit.
3. **Add a test** next to the example's test: a `UseCaseEngine` test under `server/engine/src/test/java/org/eclipse/lsp/cobol/usecases/` for parser changes (see `TestSynchronizedClause`), or a case in `toolkit/python/tests/` for toolkit changes. Put the sample program in it.
4. **Run the tests:**
   ```sh
   (cd server && mvn -B -q -pl engine -am test -Dtest=TestYourChange -Dsurefire.failIfNoSpecifiedTests=false)
   (cd toolkit/python && python3 -m unittest discover -s tests)
   ```
   Before relying on a parser change, run every parser test once: `(cd server && mvn -B -pl engine -am package)`, which takes several minutes.
5. **Rebuild and parse again:** `./mfmap build`, then `mfmap parse` as before. A new parser re-parses every program. Check the result with `mfmap summary` and `mfmap crosscheck`.
6. **Record it.** Add a `Contributors:` line to the license header of each Java file you change and a line to [FORK.md](FORK.md), as the Eclipse Public License expects for modified files. Commit with a message that says what now works, so the next person can use your commit as an example.
