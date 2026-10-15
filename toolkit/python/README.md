<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->

# cobolgraph

`cobolgraph` reads the output of `server.jar analysis --graph` and gives you typed COBOL programs:
data items with their clauses, paragraphs, typed statements, and references resolved by node ID.
It also lists calls between programs and reads and writes of Db2 tables, VSAM files, batch files,
IMS segments and CICS queues, each with its file and line. It has no dependencies beyond Python 3.9.

## Parse a source tree

Build `server.jar` first (see [server/CLI.md](../../server/CLI.md)). Then, from the root of the
application's repository, run the parser over every `.cbl` and `.cob` file:

```sh
pip install ./toolkit/python
export PARSEBOL_JAR=$PWD/server/engine/target/server.jar
cobolgraph parse app -cf app/cpy -cf app/cpy-bms -ce cpy -ce CPY -j 6
```

`-j` sets how many parser processes run at once (default 4). Each one stays up and parses program
after program, so Java start-up is paid once per process, and a separate pool of Python processes
records the results. CardDemo's 44 programs take about 9 seconds with `-j 4`; 440 take about 30.
A parser process that crashes or takes longer than 15 minutes on one program is replaced, and that
program is recorded as crashed.

Results go into a store, `.cobolgraph/` by default (`--store` to change it). The store holds `map.db`, a SQLite database, and `graphs/`, one graph
file per program. Each run records every file's status and diagnostics and the programs, calls and
data access in it, committing each file as soon as it finishes. A program that fails to analyse
still gets a graph file, with `crash` set to the error.

A later run parses only what changed: a program is reused from the store when its source, the
copybooks it used and `server.jar` are unchanged and every COPY still resolves to the same file
with the current copybook folders. Adding a folder that supplies a missing copybook re-parses just
the programs that need it. `--force` parses everything again.

## Follow along

```sh
cobolgraph serve            # http://127.0.0.1:8765/
cobolgraph report           # the Notes and Parser tabs as Markdown, for an agent to read
cobolgraph backlog          # the Backlog tab as Markdown
cobolgraph note "Added the MQ copybook folder; only the 3 MQ programs were parsed again."
cobolgraph question "Does the nightly LEDREB rebuild still run?" \
  --found "CALL 'UTP\LEDREB' at GLEDG/GLP010.CBL:212; no schedule in the repository" \
  --default "It runs nightly and moves with the ledger unit" --affects "Which wave owns it"
cobolgraph questions        # every question, open ones first, with answers
cobolgraph answer Q3 "Retired in 2019"   # an empty answer reopens it
```

The page refreshes while a parse runs or the notes change. It has three tabs:

- **Notes** is for the people the migration depends on. It starts with **Open Questions**: what the
  source cannot answer, each with what the agent found, the default it is going ahead with and
  what an answer would change. None of them block the work. Anyone with the page can type an answer;
  the agent reads answers with `cobolgraph questions`. Questions and answers are kept in
  `.cobolgraph/questions.json`. Below them are the **Agent Notes** from `.cobolgraph/notes.md`, which
  the agent (or anyone) adds to with `cobolgraph note` or edits directly.
- **Parser** shows how the map was built: the programs and the folder each copybook came from, the
  copybooks the parser supplied or could not find, parse errors grouped by message, what the parser
  found (paragraphs, statements, data items, calls by how their targets were resolved, data access
  by kind of store, calls set at run time) and the count check against the text scan.
- **Backlog** lists every unit in wave order with all of its fields from `migration-spec.json`
  (short lists on one line, longer ones and objects as nested bullets, empty fields left out)
  followed by its `units/<unit ID>.md` file. The file is looked for in the parse root and next to
  the store; `--spec` names another.

Any `file.cbl:line` reference opens the source around that line. The server binds to 127.0.0.1;
reach it from elsewhere through a tunnel or port forward. To keep the notes and questions in Git
while ignoring the rest of the store, add `.cobolgraph/*`, `!.cobolgraph/notes.md` and
`!.cobolgraph/questions.json` to `.gitignore`.

### Copybooks IBM supplies

- `DFHAID` and `DFHBMSCA` (CICS): the parser has stand-ins it uses when your copybook folders
  don't have them. Their values are the 3270 data stream bytes; check them against your CICS
  release if a program compares fields with literal bytes.
- `SQLCA` and `SQLDA` (Db2), `DFHEIBLK` (CICS) and the DL/I interface block for `EXEC DLI`
  programs are defined by the parser.
- IBM MQ copybooks (`CMQV`, `CMQODV`, ...): download them from IBM's free MQ redistributable
  client. They are IBM's files under IBM's license, so this project does not ship them:

  ```sh
  cobolgraph fetch-mq-copybooks --out mq-copybooks --accept-license
  cobolgraph parse app -cf app/cpy -cf mq-copybooks -ce cpy
  ```

  The command writes the 64-bit copybooks as `NAME.cpy`, IBM's English license files under
  `licenses/`, and `SOURCE.txt` with the download URL.

## Check the result

```sh
cobolgraph summary              # parse rate, statement counts, most common errors
cobolgraph crosscheck -cf app/cpy -cf app/cpy-bms -ce cpy -ce CPY
cobolgraph facts --root . > facts.json   # programs, calls, data access, files
```

These read the store's latest run; pass a folder of graph files instead to read those.
`crosscheck` counts CALL, PERFORM, EXEC CICS, EXEC SQL and EXEC DLI with a text scan that does
not use the parser, and lists every program where the two counts differ. Read both sides of a
difference before trusting either one.

## Use the model

```python
import cobolgraph as cg

project = cg.Project.load(".cobolgraph")   # or a folder of graph files
p = project.program("COACTUPC")

item = p.data_item("ACCT-CURR-BAL")
item.pic, item.usage, item.level, item.copybook, item.redefines, item.occurs, item.sync
[str(r.location) for r in item.references]      # every usage, with its statement

for para in p.paragraphs:
    para.performs, para.performed_by

for s in p.cics:                                 # also p.sql, p.dli, p.calls, p.file_io
    s.command, s.option("FILE"), s.paragraph, s.source

project.calls()          # CALL, LINK, XCTL and LOAD edges
project.data_access()    # store, resource, read or write, statement
```

### How names are resolved

A program name in `CALL`, `LINK` or `XCTL`, and a file name in a CICS file command, can be a
literal or a data item. `resolved` says which:

- `literal`: written in the statement.
- `value`: a data item whose `VALUE` clause is a literal. The program could change it at run time.
- `unresolved`: anything else. For calls, `candidates` lists the names the same program MOVEs into
  that data item. A value the item gets from a caller is not included.

Db2 tables come from the SQL parser (`declared`). OPEN, FETCH and CLOSE take their tables from the
cursor's DECLARE. A batch file access names the file's `ASSIGN` name, which is the JCL DD name.

### Limits

- Source text and statement verbs are read from the files named in the graph. Load graphs made on
  another machine with `path_map={"/old/root": "/new/root"}`.
- `source` assumes fixed format and drops columns 73 to 80. Pass `fixed_format=False` otherwise.
- `usage` is the parser's value; `UNDEFINED` means the item has no USAGE clause, so it is DISPLAY.
- `callers(name)` returns resolved edges only; `callers(name, candidates=True)` adds unresolved
  edges whose `candidates` include the name.
- Copybooks the parser cannot find leave their data items undefined and produce
  `semantics.notDefined` errors that name each undefined variable.

## Tests

```sh
cd toolkit/python && python -m unittest discover -s tests
```

`tests/fixtures/regenerate.sh` rebuilds the fixture from `SAMPLE.cbl` after a parser change.
Install `jsonschema` to also validate the fixture against `schema/graph-v1.schema.json`.
