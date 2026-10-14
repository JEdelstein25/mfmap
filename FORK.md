# About This Fork

This repository is a modified version of Eclipse COBOL Language Support (Che4z LSP for COBOL), maintained by Amp. It is not an Eclipse Foundation project, and neither the Eclipse Foundation nor Broadcom endorses it.

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
3. **SQL detail:** each `EXEC SQL` node records its statement type, the tables and views it references, and its cursor name.
4. **SYNC clause:** variable nodes record `SYNCHRONIZED` and its optional `LEFT` or `RIGHT` direction.
5. **IMS DL/I:** `EXEC DLI` blocks become `ExecDliNode` statements with their command, options and host variable references, instead of "Unknown EXEC block" diagnostics.
6. **CICS stand-in copybooks:** when the copybook folders have no `DFHAID` or `DFHBMSCA`, the parser uses stand-ins written for this fork (`server/engine/src/main/resources/implicitCopybooks/`). Their names follow IBM's public CICS documentation and their values are the EBCDIC bytes of the IBM 3270 data stream. They are not IBM's copybooks. A copybook with the same name in the copybook folders takes precedence.
7. **DL/I interface block:** programs with `EXEC DLI` get the DIB fields (`DIBSTAT`, `DIBSEGM` and the others in IBM's documented COBOL layout) in working storage, as the IMS translator adds them.
8. **`graph` command:** analyzes many programs in one process, reading paths from stdin and printing one graph per line, so Java start-up is paid once.
9. **Graph output:** `analysis --graph` prints the final syntax tree with an ID and class name on every node and references to other nodes by ID. [schema/graph-v1.schema.json](schema/graph-v1.schema.json) describes the format.

## Toolkit

[toolkit/python](toolkit/python) is `cobolgraph`, a Python library and command line that runs the parser over a source tree and reads the graph output as typed programs, data items, paragraphs and statements, with calls and data access between programs. It records each parse in a store (`.cobolgraph/map.db`, SQLite) that re-parses only changed programs, and `cobolgraph serve` shows a Notes page on how the map was built, with the agent's notes, and a Backlog page, refreshed while a parse runs. It is part of this fork and uses the same license. Its `fetch-mq-copybooks` command downloads IBM MQ's COBOL copybooks from IBM's public MQ redistributable client; those files stay under IBM's license and are not part of this repository.

## Set Up

You need JDK 17 or later, Maven, and Python 3.9 or later. From the root of the application's repository:

```sh
git clone --branch v0.1.1 https://github.com/JEdelstein25/parsebol tools/cobol-parser
(cd tools/cobol-parser/server && mvn -B -q -Dmaven.test.skip -pl engine -am package)
tools/cobol-parser/toolkit/cobolgraph parse app -cf app/cpy -ce cpy
tools/cobol-parser/toolkit/cobolgraph serve
```

The build writes `server/engine/target/server.jar`; the first build downloads Maven dependencies and takes a few minutes. `toolkit/cobolgraph` runs the toolkit from the checkout with that jar, so nothing else needs installing. After changing the parser, build again; the next parse re-parses every program because the jar changed. [toolkit/python/README.md](toolkit/python/README.md) describes every command.

## Distributing This Fork

- Keep [LICENSE.md](LICENSE.md), [NOTICE.md](NOTICE.md), this file, and the copyright and license headers in every file.
- When distributing a build, tell recipients where to get the source code, as EPL-2.0 section 3 requires.
- The EPL does not license the Eclipse or Che4z names and logos. Do not use them in a way that suggests this fork is an official or endorsed release.
