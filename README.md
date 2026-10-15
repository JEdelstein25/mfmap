<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->

# mfmap

mfmap maps a mainframe COBOL application for a migration. It parses every program with its copybooks and records what a rewrite needs to know, each with the file and line it came from:

- calls between programs, CICS LINK and XCTL, and Db2 stored procedure calls matched to their `CREATE PROCEDURE` definitions
- reads and writes of Db2 tables, VSAM files, batch files, IMS segments and queues
- dynamic SQL, commit points, and every data item with its level, PICTURE and other clauses

It targets IBM Enterprise COBOL with Db2, CICS and IMS. It is a starting point to change for your codebase: when it fails on your code or leaves something out, change the parser in this checkout and build again.

## Set Up

You need JDK 17 or later, Maven, and Python 3.9 or later. From the root of the application's repository:

```sh
git clone --branch v0.2.0 https://github.com/JEdelstein25/mfmap tools/mfmap
tools/mfmap/mfmap parse app -cf app/cpy -ce cpy
tools/mfmap/mfmap serve
```

The first run builds the parser, which takes a few minutes. After changing the parser, run `tools/mfmap/mfmap build`; the next parse re-parses every program.

Add `tools/mfmap`, `.mfmap/*`, `!.mfmap/notes.md` and `!.mfmap/questions.json` to `.gitignore` to keep the notes and questions in Git and ignore the rest.

## What It Does

- `mfmap parse` runs the parser over the programs and records the results in `.mfmap/`. It re-parses only programs whose source, copybooks or parser changed.
- `mfmap serve` shows a page that updates while it works: **Notes** (open questions for people to answer, and notes on what was done), **Parser** (what was parsed, errors, and what was found) and **Backlog** (migration units from `migration-spec.json`).
- `mfmap facts` prints programs, calls, data access, files, commit points and stored procedures as JSON.
- `mfmap crosscheck` compares statement counts with a text search that does not use the parser.
- `mfmap question`, `questions` and `answer` record open questions and their answers; `mfmap note` adds a note.

[toolkit/python/README.md](toolkit/python/README.md) describes every command and the Python API. [server/CLI.md](server/CLI.md) describes the parser's own command line.

## How It Is Built

The parser is based on [Eclipse COBOL Language Support](https://github.com/eclipse-che4z/che-che4z-lsp-for-cobol) (Che4z), with changes for migration work: structured CICS, SQL and DL/I detail, a graph output format, stand-in copybooks, and a mode that parses many programs in one process. [FORK.md](FORK.md) lists every change. [CHE4Z-README.md](CHE4Z-README.md) is the original project's README.

mfmap is licensed under the Eclipse Public License 2.0, like the project it is based on. See [LICENSE.md](LICENSE.md) and [NOTICE.md](NOTICE.md). It is not an Eclipse Foundation project, and neither the Eclipse Foundation nor Broadcom endorses it.
