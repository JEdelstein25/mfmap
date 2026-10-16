<!--
Copyright (c) 2026 Amp.

This program and the accompanying materials are made
available under the terms of the Eclipse Public License 2.0
which is available at https://www.eclipse.org/legal/epl-2.0/

SPDX-License-Identifier: EPL-2.0
-->

# mfmap

`mfmap` reads the output of `server.jar analysis --graph` and gives you typed COBOL programs:
data items with their clauses, paragraphs, typed statements, and references resolved by node ID.
It also lists calls between programs, Db2 stored procedure calls with their definitions, reads
and writes of Db2 tables, VSAM files, batch files, IMS segments and CICS queues, dynamic SQL, and
commit points, each with its file and line. It has no dependencies beyond Python 3.9.

## Parse a source tree

Build `server.jar` first (see [server/CLI.md](../../server/CLI.md)). Then, from the root of the
application's repository, run the parser over every `.cbl` and `.cob` file:

```sh
pip install ./toolkit/python
export MFMAP_JAR=$PWD/server/engine/target/server.jar
mfmap parse src -cf src/copybooks -cf src/maps -ce cpy -ce CPY -j 6
```

A program is named by its PROGRAM-ID. When two files have the same PROGRAM-ID, as when a program
was copied and the copy never renamed, the one in the file named after it keeps the name and each
other copy is named after its file, as the build names its load module. The Parser tab lists these
under Program Names, along with files whose PROGRAM-ID differs from the file name.

Files named on the command line are parsed whatever their extension. In folders, `-se` picks
other program extensions, and `-se ''` picks members with no extension, as in a PDS copied off
the mainframe. Hidden folders such as `.git` are skipped.

`-j` sets how many parser processes run at once (default 4). Each one stays up and parses program
after program, so Java start-up is paid once per process, and a separate pool of Python processes
records the results. 44 programs take about 9 seconds with `-j 4`; 440 take about 30.
A parser process that crashes or takes longer than 15 minutes on one program is replaced, and that
program is recorded as crashed.

Results go into a store, `.mfmap/` by default (`--store` to change it). The store holds `map.db`, a SQLite database, and `graphs/`, one graph
file per program. Each run records every file's status and diagnostics and the programs, calls and
data access in it, committing each file as soon as it finishes. A program that fails to analyse
still gets a graph file, with `crash` set to the error.

A later run parses only what changed: a program is reused from the store when its source, the
copybooks it used and `server.jar` are unchanged and every COPY still resolves to the same file
with the current copybook folders. Adding a folder that supplies a missing copybook re-parses just
the programs that need it. `--force` parses everything again.

## Follow along

```sh
mfmap serve            # http://127.0.0.1:8765/
mfmap report           # the Notes and Parser tabs as Markdown, for an agent to read
mfmap backlog          # the Backlog tab as Markdown
mfmap note "Added the MQ copybook folder; only the 3 MQ programs were parsed again."
mfmap question "Does the nightly LEDREB rebuild still run?" \
  --found "CALL 'UTP\LEDREB' at GLEDG/GLP010.CBL:212; no schedule in the repository" \
  --default "It runs nightly and moves with the ledger unit" --affects "Which wave owns it"
mfmap questions        # every question, open ones first, with answers
mfmap answer Q3 "Retired in 2019"   # an empty answer reopens it
```

The page refreshes while a parse runs or the notes change. It has three tabs:

- **Notes** is for the people the migration depends on. It starts with **Open Questions**: what the
  source cannot answer, each with what the agent found, the default it is going ahead with and
  what an answer would change. None of them block the work. Anyone with the page can type an answer;
  the agent reads answers with `mfmap questions`. Questions and answers are kept in
  `.mfmap/questions.json`. Below them are the **Agent Notes** from `.mfmap/notes.md`, which
  the agent (or anyone) adds to with `mfmap note` or edits directly.
- **Parser** shows how the map was built: the programs and the folder each copybook came from, the
  copybooks the parser supplied or could not find, parse errors grouped by message, what the parser
  found (paragraphs, statements, data items, calls by how their targets were resolved, data access
  by kind of store, calls set at run time) and the count check against the text scan.
- **Backlog** lists every unit in `migration.json` in wave order with its status, its threads
  and its `units/<unit ID>.md` file, and any problems `mfmap check` finds. Above the waves are the
  progress counts and the threads still working on a unit. The file is looked for in the
  parse root and next to the store; `--plan` names another.

Any `file.cbl:line` reference opens the source around that line. The server binds to 127.0.0.1;
reach it from elsewhere through a tunnel or port forward. To keep the notes and questions in Git
while ignoring the rest of the store, add `.mfmap/*`, `!.mfmap/notes.md` and
`!.mfmap/questions.json` to `.gitignore`.

### Copybooks your build generates

BMS symbolic maps are written by the build, not kept in source. Generate them from the map source
into a folder outside the application source and pass it to `parse`:

```sh
mfmap bms-copybooks src/maps --out .mfmap/copybooks/bms
mfmap parse src -cf src/copybooks -cf .mfmap/copybooks/bms -ce cpy
```

Each `NAME.bms` becomes `NAME.cpy`, named after the file as builds name the member. Names, lengths
and `PICIN`/`PICOUT` follow the map; byte offsets follow IBM's documented layout, so check them
against your build's copybooks before relying on them.

### Copybooks IBM supplies

- `DFHAID` and `DFHBMSCA` (CICS): the parser has stand-ins it uses when your copybook folders
  don't have them. Their values are the 3270 data stream bytes; check them against your CICS
  release if a program compares fields with literal bytes.
- `SQLCA` and `SQLDA` (Db2), `DFHEIBLK` (CICS) and the DL/I interface block for `EXEC DLI`
  programs are defined by the parser.
- `CEEIGZCT` (Language Environment): the parser has a stand-in with only `CEE000`, the success
  condition. Pass the folder with IBM's copybook (`SCEESAMP`) if a program tests other conditions.
- IBM MQ copybooks (`CMQV`, `CMQODV`, ...): download them from IBM's free MQ redistributable
  client. They are IBM's files under IBM's license, so this project does not ship them:

  ```sh
  mfmap fetch-mq-copybooks --out mq-copybooks --accept-license
  mfmap parse src -cf src/copybooks -cf mq-copybooks -ce cpy
  ```

  The command writes the 64-bit copybooks as `NAME.cpy`, IBM's English license files under
  `licenses/`, and `SOURCE.txt` with the download URL.

## Check the result

```sh
mfmap summary              # parse rate, statement counts, most common errors
mfmap crosscheck -cf src/copybooks -cf src/maps -ce cpy -ce CPY
mfmap facts --root . > facts.json   # programs, calls, data access, files, commits, procedures
```

These read the store's latest run; pass a folder of graph files instead to read those.
`crosscheck` counts CALL, PERFORM, EXEC CICS, EXEC SQL, EXEC SQL CALL and EXEC DLI with a text
scan that does not use the parser (a CALL inside EXEC SQL is counted as an SQL CALL only), and lists every program where the two counts differ. Read both sides of a
difference before trusting either one.

## Use the model

```python
import mfmap as cg

project = cg.Project.load(".mfmap")   # or a folder of graph files
p = project.program("ACCTUPD")

item = p.data_item("ACCT-CURR-BAL")
item.pic, item.usage, item.level, item.copybook, item.redefines, item.occurs, item.sync
item.occurs_min, item.depending_on                # OCCURS 1 TO 20 DEPENDING ON N: 1, "N"
[str(r.location) for r in item.references]      # every usage, with its statement

for para in p.paragraphs:
    para.performs, para.performed_by

for s in p.cics:                                 # also p.sql, p.dli, p.calls, p.file_io
    s.command, s.option("FILE"), s.paragraph, s.source

for s in p.sql:
    s.columns, s.values, s.into, s.where           # as written, in column order
    s.order_by, s.fetch_first, s.table_columns     # DECLARE TABLE: "ACCT_ID CHAR(11) NOT NULL", ...

for s in p.statements:
    s.condition                                  # IF, PERFORM UNTIL, EVALUATE subject
    s.when                                       # EVALUATE: each WHEN, as written

project.calls()          # CALL, LINK, XCTL, LOAD and SQL CALL edges
project.data_access()    # store, resource, read or write, statement
cg.commit_points(p)      # EXEC SQL COMMIT and ROLLBACK, EXEC CICS SYNCPOINT
```

### Stored procedures

`EXEC SQL CALL` is an edge with `via` `SQL CALL` whose target is the procedure name as written;
a name in a host variable resolves like a dynamic CALL. `parse` and `facts` read `CREATE
PROCEDURE` statements from the `.sql`, `.ddl` and `.db2` files under the current folder (and from
`--ddl` files or folders, for DDL with other names) and match each CALL to its definition: the same
qualified name, or for an unqualified CALL, whose schema comes from the package's bind options, the
only definition with that name. For each procedure, `facts` gives its language, parameters, result
sets and, for an external procedure, the program that implements it (from `EXTERNAL NAME`, or the
procedure's own name for a bare `EXTERNAL`). That program is an entry point called from SQL. A
native SQL procedure keeps its logic in the DDL; its `reads`, `writes` and `calls` come from a text
scan of the body, so check them against it. The Parser tab lists every called procedure and flags
the ones with no `CREATE PROCEDURE` in the repository.

### Resolvers

Resolvers write entities and relationships to the store's `entities` and `relationships` tables,
each with the file and line it came from and the resolver that wrote it. `mfmap parse` runs them
all at the end; `mfmap resolve [names]` runs them again, replacing what each one wrote before.
Endpoints are written `type:name`, such as `program:ACCTUPD`, `transaction:AUPD`,
`screen:ACCTSET.ACCTMAP`, `job:NIGHTLY`, `dataset:PROD.ACCOUNTS` or
`paragraph:ACCTUPD.2000-PROCESS`.

- `programs`: copybooks each program includes, calls between programs, data access, PERFORM and GO TO between paragraphs, CICS
  screens sent and received, and transactions started or returned to.
- `cics`: transactions and the programs they start, from CSD `DEFINE` statements, and screens from
  BMS map source.
- `jcl`: which job or procedure runs which program in each step (including programs run through
  TSO batch with `RUN PROGRAM`), the datasets their DD statements name, and each program's batch
  file reads and writes matched to those datasets through its `ASSIGN` names.
- `ddl`: Db2 tables with their columns (`column:TABLE.COLUMN`), primary keys, foreign keys
  (`references`), indexes and views (`selects-from`), from the parser's `ddl` command on the DDL
  files under the current folder and `--ddl` paths, and on any other text file, such as a DSNTIAD
  job, with a `CREATE TABLE`, `INDEX` or `VIEW` at the start of a line. Tables are named as the
  programs name them, qualified or not. A table the programs use that no DDL defines is a
  `no-definition` entity, and a statement the grammar rejects is a `parse-error` entity; the Parser
  tab lists both.

To resolve something else, such as API definitions or a scheduler's job order, add a module to
`mfmap/resolvers/` with a `NAME` and a `resolve(ctx)` function that yields `Entity` and
`Relationship` facts; `ctx` gives the store connection, the parsed programs and the repository's
files. For what needs judgment, such as which paragraphs hold business logic, record it:

```sh
mfmap record business-logic paragraph:ACCTUPD.2000-PROCESS --note "Applies the interest rate" \
  --evidence src/cobol/ACCTUPD.cbl:812
mfmap record exposes api:/accounts program:ACCTINQ --evidence src/api/accounts.yaml:12
```

Recorded facts belong to the resolver `agent` and stay when resolvers run again. `mfmap facts`
includes all entities and relationships, and the Parser tab counts them.

### The migration plan

`migration.json` holds the units the application is rewritten in, in build order. It follows
[schema/migration-v1.schema.json](../../schema/migration-v1.schema.json):

```json
{
  "version": 1,
  "target": "Java on Kubernetes",
  "units": [{
    "id": "accounts",
    "name": "Account maintenance",
    "wave": 2,
    "programs": ["program:ACCTUPD", "program:ACCTINQ"],
    "entryPoints": ["transaction:AUPD"],
    "reads": ["db2:BANK.ACCOUNT"],
    "writes": ["db2:BANK.ACCOUNT"],
    "dependencies": [{"unit": "customers", "on": "program:CUSTINQ", "handling": "Call the customer service"}],
    "interfaces": [{"direction": "provides", "name": "account record", "layout": "copybook:ACCTREC"}],
    "acceptanceChecks": [{"description": "Balances match the current system for every sample account"}],
    "status": "building",
    "threads": [{"url": "https://ampcode.com/threads/T-...", "task": "build"}]
  }],
  "excluded": [{"program": "program:OLDRPT", "reason": "No job or transaction runs it"}]
}
```

Endpoints use the same `type:name` IDs as the store, and a unit has only these fields; anything
else about a unit goes in `units/<unit ID>.md`. `mfmap check` validates the file against the schema
and checks what a schema cannot: unit IDs are unique, a unit depends only on units in earlier
waves, every parsed program is in exactly one unit or excluded with a reason, and every endpoint is
in the map. It exits with status 1 when there are problems, and the Backlog tab lists them.

While the units are built, `status` records how far each has got: `todo` (the default),
`building`, `built` (merged, and its acceptance checks pass) or `verified` (its rules checked
against the cited source and its outputs compared with the current system). `threads` links the
threads working on a unit; set `finished` once a thread reports back, and it leaves the Backlog
tab's Active Threads list. `mfmap check` warns when a unit has started before the units it depends
on are built.

### Dynamic SQL and commit points

`PREPARE` and `EXECUTE IMMEDIATE` become Db2 access with mode `unknown` and `resolved`
`unresolved`, since the tables are only known at run time. `expression` names the host variable
that holds the SQL text and `candidates` lists the literals the program MOVEs into it. `EXECUTE` of
a prepared statement adds no second row. Commit points (`COMMIT`, `ROLLBACK`, `SYNCPOINT` and
`SYNCPOINT ROLLBACK`) mark where units of work end.

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
