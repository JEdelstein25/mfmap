# About This Fork

mfmap is a modified version of Eclipse COBOL Language Support (Che4z LSP for COBOL), maintained by Amp. It is not an Eclipse Foundation project, and neither the Eclipse Foundation nor Broadcom endorses it.

- Upstream: https://github.com/eclipse-che4z/che-che4z-lsp-for-cobol
- Based on upstream commit `2bac488b85dd1574b6ffe0524870a963695b04b4` (October 9, 2026)
- License: Eclipse Public License 2.0, unchanged. See [LICENSE.md](LICENSE.md). Amp's changes are made available under the same license.
- The original project's README is [CHE4Z-README.md](CHE4Z-README.md).

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
14. **Statement syntax:** every statement node and every `EXEC SQL` node has a `syntax` field with its grammar structure: each keyword and operator, and each operand under the rule that names its role (`moveToSendingArea`, `computeStore`, `relationalOperator`, `callByContentPhrase`, `stringIntoPhrase`, `dbs_where_clause`, `target_variable_names_loop` and so on). Nested statements are written as stubs, since they have their own nodes. Text a dialect replaced inside a COBOL statement, such as `DFHRESP(NORMAL)`, is given as written. `SyntaxBuilder` builds it; `Syntax` is the node field.

## Toolkit

[toolkit/python](toolkit/python) is `mfmap`, a Python library and command line that runs the parser over a source tree and reads the graph output as typed programs, data items, paragraphs and statements, with calls and data access between programs. It records each parse in a store (`.mfmap/map.db`, SQLite) that re-parses only changed programs, runs resolvers that add entities and relationships from CICS definitions, BMS maps, JCL, Db2 DDL, Control-M and CA-7 schedules, OpenAPI and z/OS Connect definitions with the web pages that call them, and Easytrieve programs, counts `CALL 'CBLTDLI'` as IMS data access, and `mfmap serve` shows a page, refreshed while a parse runs, with three tabs: Notes (open questions for people to answer, and the agent's notes), Parser (how the map was built) and Backlog. It is part of this fork and uses the same license. Its `fetch-mq-copybooks` command downloads IBM MQ's COBOL copybooks from IBM's public MQ redistributable client; those files stay under IBM's license and are not part of this repository. Its `bms-copybooks` command writes COBOL symbolic map copybooks from BMS map source for builds that do not keep them.

## Set Up

You need JDK 17 or later, Maven, and Python 3.9 or later. From the root of the application's repository:

```sh
git clone --branch v0.5.2 https://github.com/JEdelstein25/mfmap tools/mfmap
tools/mfmap/mfmap parse src -cf src/copybooks -ce cpy
tools/mfmap/mfmap serve
```

The first run builds the parser, which takes a few minutes. After changing the parser, run `tools/mfmap/mfmap build`; the next parse re-parses every program.

Add `tools/mfmap`, `.mfmap/*`, `!.mfmap/notes.md` and `!.mfmap/questions.json` to `.gitignore` to keep the notes and questions in Git and ignore the rest.

## What It Does

mfmap maps a mainframe COBOL application for a migration. It parses every program with its copybooks and records what a rewrite needs to know, each with the file and line it came from:

- calls between programs, CICS LINK and XCTL, and Db2 stored procedure calls matched to their `CREATE PROCEDURE` definitions
- reads and writes of Db2 tables, VSAM files, batch files, IMS segments and queues
- dynamic SQL, commit points, and every data item with its level, PICTURE and other clauses

It targets IBM Enterprise COBOL with Db2, CICS and IMS. It is a starting point to change for your codebase: when it fails on your code or leaves something out, change it in this checkout and build again. [CUSTOMIZING.md](CUSTOMIZING.md) shows where each kind of change goes, with an example commit for each.

- `mfmap parse` runs the parser over the programs and records the results in `.mfmap/`. It re-parses only programs whose source, copybooks or parser changed.
- `mfmap serve` shows a page that updates while it works: **Notes** (open questions for people to answer, and notes on what was done), **Parser** (what was parsed, errors, and what was found) and **Backlog** (migration units from `migration.json`).
- Resolvers then connect what the parser found to the rest of the repository: CICS transactions to the programs they start, programs to the screens they send, jobs to the programs they run and the datasets they use, and paragraphs to the paragraphs they perform. Everything goes into `.mfmap/map.db`. `mfmap record` adds what needs judgment, such as which paragraphs hold business logic.
- `mfmap facts` prints programs, calls, data access, files, commit points, stored procedures, entities and relationships as JSON.
- `mfmap crosscheck` compares statement counts with a text search that does not use the parser.
- `mfmap check` validates the migration plan, `migration.json`, against [its schema](schema/migration-v1.schema.json) and the map.
- `mfmap question`, `questions` and `answer` record open questions and their answers; `mfmap note` adds a note.

[toolkit/python/README.md](toolkit/python/README.md) describes every command and the Python API. [server/CLI.md](server/CLI.md) describes the parser's own command line.

## Distributing This Fork

- Keep [LICENSE.md](LICENSE.md), [NOTICE.md](NOTICE.md), this file, and the copyright and license headers in every file.
- When distributing a build, tell recipients where to get the source code, as EPL-2.0 section 3 requires.
- The EPL does not license the Eclipse or Che4z names and logos. Do not use them in a way that suggests this fork is an official or endorsed release.
