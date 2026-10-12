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

## Distributing This Fork

- Keep [LICENSE.md](LICENSE.md), [NOTICE.md](NOTICE.md), this file, and the copyright and license headers in every file.
- When distributing a build, tell recipients where to get the source code, as EPL-2.0 section 3 requires.
- The EPL does not license the Eclipse or Che4z names and logos. Do not use them in a way that suggests this fork is an official or endorsed release.
