# About This Fork

mfmap is a modified version of Eclipse COBOL Language Support (Che4z LSP for COBOL), maintained by Amp. It is not an Eclipse Foundation project, and neither the Eclipse Foundation nor Broadcom endorses it.

- Upstream: https://github.com/eclipse-che4z/che-che4z-lsp-for-cobol
- Based on upstream commit `2bac488b85dd1574b6ffe0524870a963695b04b4` (October 9, 2026)
- License: Eclipse Public License 2.0, unchanged. See [LICENSE.md](LICENSE.md). Amp's changes are made available under the same license.

## Changes in This Fork

All changes are in the language server under `server/`. Each modified file lists the change under `Contributors:` in its license header.

1. **Command line output** (`cli/`):
   - `analysis --ast-phase=<ALL|FINAL|START|...>` selects which syntax tree snapshots to print. The default is still all of them.
   - `analysis --ast-compact-references` prints references to other nodes as `nodeType`, `name` and `locality` instead of full copies.
   - `cfast` accepts `-cf` and `-ce` and no longer crashes when they are missing.
   - The command line client answers editor callbacks, such as `availableDialects`, with empty results instead of throwing. This fixes analysis of programs with `CALL` statements.
   - [server/CLI.md](server/CLI.md) documents the commands, including that relative copybook folders resolve from the current working directory.
2. **CICS detail:** each `EXEC CICS` node records its command (for example `SEND MAP`) and its options as name and value pairs.
3. **SQL detail:** each `EXEC SQL` node records its statement type, the tables and views it references, and its cursor name. A stored procedure `CALL` records the procedure name (or the host variable holding it); `PREPARE`, `EXECUTE` and `DECLARE CURSOR FOR` a prepared statement record the statement name; `PREPARE` and `EXECUTE IMMEDIATE` record where the SQL text comes from. INSERT, SELECT, UPDATE, FETCH and SET record their columns, values and receiving host variables, the statement's own WHERE condition, ORDER BY and FETCH FIRST, as written. `DECLARE TABLE` records each column definition as written.
4. **SYNC clause:** variable nodes record `SYNCHRONIZED` and its optional `LEFT` or `RIGHT` direction.
5. **IMS DL/I:** `EXEC DLI` blocks become `ExecDliNode` statements with their command, options and host variable references, instead of "Unknown EXEC block" diagnostics. The lexer gives a terminated `EXEC DLI` block its own token, `EXEC_DLI`, which the grammar accepts as a statement, so an `IF`, `ELSE` or other branch that holds only `EXEC DLI` parses.
6. **CICS stand-in copybooks:** when the copybook folders have no `DFHAID` or `DFHBMSCA`, the parser uses stand-ins written for this fork (`server/engine/src/main/resources/implicitCopybooks/`). Their names follow IBM's public CICS documentation and their values are the EBCDIC bytes of the IBM 3270 data stream. They are not IBM's copybooks. A copybook with the same name in the copybook folders takes precedence. Every program, whatever its dialects, also gets a Language Environment `CEEIGZCT` stand-in with only the `CEE000` condition (success), added in `DialectService`.
7. **DL/I interface block:** programs with `EXEC DLI` get the DIB fields (`DIBSTAT`, `DIBSEGM` and the others in IBM's documented COBOL layout) in working storage, as the IMS translator adds them.
8. **`graph` command:** analyzes many programs in one process, reading paths from stdin and printing one graph per line, so Java start-up is paid once.
9. **Faster position lookups:** placing EXEC blocks and COPY statements in the syntax tree used to walk the whole tree once per block, so large programs slowed down faster than they grew. `NodePositionIndex` gives the same answers while skipping subtrees that cannot contain the position.
10. **Graph output:** `analysis --graph` prints the final syntax tree with an ID and class name on every node and references to other nodes by ID. [schema/graph-v1.schema.json](schema/graph-v1.schema.json) describes the format.
11. **OCCURS DEPENDING ON:** OCCURS clauses record their DEPENDING ON object, and elementary tables keep their whole OCCURS clause (`TO` and `DEPENDING ON`), not just the first count.
12. **Conditions:** `IF`, `PERFORM ... UNTIL` and `EVALUATE ... WHEN` nodes record where their condition is in the source, and `EVALUATE` where its subject is. (The parser's working text has CICS and SQL fragments such as `DFHRESP(NORMAL)` blanked out, so the text is read from the source.)
13. **`ddl` command:** parses Db2 DDL files (including DDL inside JCL) with the embedded SQL grammar and prints their tables, columns, keys, indexes and views as JSON ([server/CLI.md](server/CLI.md)).

## Toolkit

[toolkit/python](toolkit/python) is `mfmap`, a Python library and command line that runs the parser over a source tree and reads the graph output as typed programs, data items, paragraphs and statements, with calls and data access between programs. It records each parse in a store (`.mfmap/map.db`, SQLite) that re-parses only changed programs, runs resolvers that add entities and relationships from CICS definitions, BMS maps, JCL, Db2 DDL, Control-M and CA-7 schedules, OpenAPI and z/OS Connect definitions with the web pages that call them, and Easytrieve programs, counts `CALL 'CBLTDLI'` as IMS data access, and `mfmap serve` shows a page, refreshed while a parse runs, with three tabs: Notes (open questions for people to answer, and the agent's notes), Parser (how the map was built) and Backlog. It is part of this fork and uses the same license. Its `fetch-mq-copybooks` command downloads IBM MQ's COBOL copybooks from IBM's public MQ redistributable client; those files stay under IBM's license and are not part of this repository. Its `bms-copybooks` command writes COBOL symbolic map copybooks from BMS map source for builds that do not keep them.

## Set Up

See [README.md](README.md#set-up).

## Distributing This Fork

- Keep [LICENSE.md](LICENSE.md), [NOTICE.md](NOTICE.md), this file, and the copyright and license headers in every file.
- When distributing a build, tell recipients where to get the source code, as EPL-2.0 section 3 requires.
- The EPL does not license the Eclipse or Che4z names and logos. Do not use them in a way that suggests this fork is an official or endorsed release.
