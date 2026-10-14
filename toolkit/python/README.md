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
application's repository, run the parser over every `.cbl` and `.cob` file, one Java process per
program:

```sh
pip install ./toolkit/python
export PARSEBOL_JAR=$PWD/server/engine/target/server.jar
cobolgraph parse app -cf app/cpy -cf app/cpy-bms -ce cpy -ce CPY -j 6
```

Results go into a store, `.cobolgraph/` by default (`--store` to change it); add it to the
application's `.gitignore`. The store holds `map.db`, a SQLite database, and `graphs/`, one graph
file per program. Each run records every file's status and diagnostics and the programs, calls and
data access in it, committing each file as soon as it finishes. A program that fails to analyse
still gets a graph file, with `crash` set to the error.

A later run parses only what changed: a program is reused from the store when its source, the
copybooks it used and `server.jar` are unchanged and every COPY still resolves to the same file
with the current copybook folders. Adding a folder that supplies a missing copybook re-parses just
the programs that need it. `--force` parses everything again.

## Follow along in the dashboard

```sh
cobolgraph serve            # http://127.0.0.1:8765/, reads .cobolgraph/map.db
```

The dashboard refreshes while a parse runs. It shows:

- **Progress:** files parsed, clean, with errors, crashed and reused, each run's results, and the
  count check against the text scan.
- **Errors:** errors grouped by message, such as `Variable DFHENTER is not defined`, with every
  location.
- **Program Map:** calls between programs in columns by call depth, programs outside the
  repository, and unresolved calls with the names the program moves into them.
- **Data Map:** which programs read and write each Db2 table, VSAM file, batch file, IMS segment
  and queue, with the statements behind each cell.
- **Backlog:** the units, waves and open questions in `migration-spec.json`, when the file exists
  next to the store or in the parse root (`--spec` to name another file).

Click a program for its paragraphs, data items, calls and data access, and any file and line for
the source around it. The server binds to 127.0.0.1; reach it from elsewhere through a tunnel or
port forward.

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
