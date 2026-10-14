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

Build `server.jar` first (see [server/CLI.md](../../server/CLI.md)). Then run the parser over
every `.cbl` and `.cob` file, one Java process per program:

```sh
pip install ./toolkit/python
export PARSEBOL_JAR=$PWD/server/engine/target/server.jar
cobolgraph parse app --out graphs -cf app/cpy -cf app/cpy-bms -ce cpy -ce CPY -j 6
```

A program that fails to analyse still gets a graph file, with `crash` set to the error.

## Check the result

```sh
cobolgraph summary graphs        # parse rate, statement counts, most common errors
cobolgraph crosscheck graphs -cf app/cpy -cf app/cpy-bms -ce cpy -ce CPY
cobolgraph facts graphs --root . > facts.json   # programs, calls, data access, files
```

`crosscheck` counts CALL, PERFORM, EXEC CICS, EXEC SQL and EXEC DLI with a text scan that does
not use the parser, and lists every program where the two counts differ. Read both sides of a
difference before trusting either one.

## Use the model

```python
import cobolgraph as cg

project = cg.Project.load("graphs")
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
- Copybooks the parser cannot find, such as IBM's `DFHAID`, leave their data items undefined and
  produce `semantics.notDefined` errors.

## Tests

```sh
cd toolkit/python && python -m unittest discover -s tests
```

`tests/fixtures/regenerate.sh` rebuilds the fixture from `SAMPLE.cbl` after a parser change.
Install `jsonschema` to also validate the fixture against `schema/graph-v1.schema.json`.
