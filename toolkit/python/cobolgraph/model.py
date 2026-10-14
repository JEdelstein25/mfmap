# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Typed access to the graph output of ``server.jar analysis --graph`` (schema graph-v1)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Iterable, Iterator, Optional
from urllib.parse import unquote, urlparse

SCHEMA_VERSION = 1

# Node types that are procedure statements. Che4z also types EXEC CICS, SQL and DLI blocks as
# STATEMENT, and leaves most verbs (MOVE, COMPUTE, CLOSE, ...) as a generic STATEMENT. An OPEN is a
# generic STATEMENT with one OPEN_STATEMENT child per file, so OPEN_STATEMENT is not listed here.
STATEMENT_NODE_TYPES = {
    "ALTER", "DELETE_STATEMENT", "EVALUATE", "EXEC_CICS_ABEND", "EXIT", "EXIT_PARAGRAPH",
    "EXIT_PERFORM", "EXIT_SECTION", "GO_BACK", "GO_TO", "IF", "JSON_GENERATE", "JSON_PARSE",
    "MERGE", "PERFORM", "READ_STATEMENT", "REWRITE_STATEMENT", "SORT",
    "START_STATEMENT", "STATEMENT", "STOP", "SUBROUTINE", "WRITE_STATEMENT", "XML_GENERATE",
    "XML_PARSE",
}

SQL_READS = {"SELECT", "SELECT INTO", "DECLARE CURSOR", "OPEN", "FETCH"}
SQL_WRITES = {"INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE"}
CICS_FILE_READS = {"READ", "READNEXT", "READPREV", "STARTBR", "RESETBR", "ENDBR"}
CICS_FILE_WRITES = {"WRITE", "REWRITE", "DELETE", "UNLOCK"}
CICS_QUEUE_READS = {"READQ"}
CICS_QUEUE_WRITES = {"WRITEQ", "DELETEQ"}
CICS_PROGRAM_TRANSFERS = {"LINK", "XCTL", "LOAD"}
DLI_READS = {"GU", "GHU", "GN", "GHN", "GNP", "GHNP"}
DLI_WRITES = {"ISRT", "REPL", "DLET"}


@dataclass(frozen=True)
class Location:
    """A source range. Lines and columns are one-based; ``path`` is None for implicit nodes."""

    uri: str
    path: Optional[str]
    line: int
    column: int
    end_line: int
    end_column: int
    copybook: Optional[str] = None

    def __str__(self) -> str:
        return f"{os.path.basename(self.path or self.uri)}:{self.line}"


def literal(text: Optional[str]) -> Optional[str]:
    """Return the contents of a quoted COBOL literal, or None when ``text`` is not one."""
    if text and len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1].replace(text[0] * 2, text[0])
    return None


class Node:
    """One syntax tree node. ``data`` holds the raw JSON fields except children."""

    def __init__(self, graph: "SourceFile", data: dict, parent: Optional["Node"]):
        self.graph = graph
        self.parent = parent
        self.data = {k: v for k, v in data.items() if k != "children"}
        self.children = [Node(graph, child, self) for child in data["children"]]
        graph._nodes[self.id] = self

    id = property(lambda self: self.data["id"])
    kind = property(lambda self: self.data["kind"])
    node_type = property(lambda self: self.data["nodeType"])
    name = property(lambda self: self.data.get("name"))

    @cached_property
    def location(self) -> Optional[Location]:
        return self.graph._location(self.data.get("locality"))

    @property
    def source(self) -> str:
        """The node's source text, read from the file named by its location."""
        return self.graph.source_text(self.location)

    def walk(self) -> Iterator["Node"]:
        """This node and its descendants in pre-order."""
        yield self
        for child in self.children:
            yield from child.walk()

    def ancestors(self) -> Iterator["Node"]:
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    def refs(self, field: str) -> list["Node"]:
        """Nodes referenced by ``field``; references to nodes outside the tree are skipped."""
        value = self.data.get(field)
        items = value if isinstance(value, list) else [value]
        return [self.graph._nodes[v["ref"]] for v in items if isinstance(v, dict) and "ref" in v]

    def __repr__(self) -> str:
        return f"<{self.kind} {self.id} {self.name or ''} {self.location}>"


class SourceFile:
    """One graph output file: a parsed source file with its programs and diagnostics."""

    def __init__(self, data: dict, path_map: Optional[dict[str, str]] = None, fixed_format=True):
        if "crash" not in data and data.get("schemaVersion") != SCHEMA_VERSION:
            raise ValueError(f"expected schemaVersion {SCHEMA_VERSION}, got {data.get('schemaVersion')}")
        self.data = data
        self.uri = data["uri"]
        self.crash: Optional[str] = data.get("crash")
        self.diagnostics: list[dict] = data.get("diagnostics", [])
        self.fixed_format = fixed_format
        self._path_map = path_map or {}
        self._nodes: dict[str, Node] = {}
        self._lines: dict[str, list[str]] = {}
        self.root = Node(self, data["tree"], None) if "tree" in data else None

    @classmethod
    def load(cls, path: str | os.PathLike, **kwargs) -> "SourceFile":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f), **kwargs)

    @property
    def path(self) -> Optional[str]:
        return self._path(self.uri)

    @property
    def errors(self) -> list[dict]:
        return [d for d in self.diagnostics if d.get("severity") == "ERROR"]

    @property
    def clean(self) -> bool:
        """True when the file parsed and analysis reported no errors."""
        return self.root is not None and not self.errors

    @cached_property
    def programs(self) -> list["Program"]:
        if self.root is None:
            return []
        return [Program(n) for n in self.root.walk() if n.kind == "ProgramNode"]

    def node(self, node_id: str) -> Node:
        return self._nodes[node_id]

    @cached_property
    def _references(self) -> dict[str, list["Reference"]]:
        """Usages by the id of the data item they resolve to."""
        index: dict[str, list[Reference]] = {}
        programs = {p.node.id: p for p in self.programs}
        for node in self._nodes.values():
            if node.kind != "VariableUsageNode":
                continue
            found = None
            for ancestor in node.ancestors():
                if found is None and ancestor.node_type in STATEMENT_NODE_TYPES:
                    found = ancestor
                if ancestor.id in programs:
                    found = statement(programs[ancestor.id], found) if found else None
                    break
            for target in node.refs("definitions"):
                index.setdefault(target.id, []).append(Reference(node, found))
        return index

    def nodes(self, *kinds: str) -> list[Node]:
        return [n for n in self._nodes.values() if not kinds or n.kind in kinds]

    def _path(self, uri: str) -> Optional[str]:
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            return None
        path = unquote(parsed.path)
        for old, new in self._path_map.items():
            if path.startswith(old):
                return new + path[len(old):]
        return path

    def _location(self, locality: Optional[dict]) -> Optional[Location]:
        if not locality or "uri" not in locality:
            return None
        rng = locality.get("range") or {}
        start, end = rng.get("start", {}), rng.get("end", {})
        return Location(
            uri=locality["uri"],
            path=self._path(locality["uri"]),
            line=start.get("line", -1) + 1,
            column=start.get("character", -1) + 1,
            end_line=end.get("line", -1) + 1,
            end_column=end.get("character", -1) + 1,
            copybook=locality.get("copybookId"),
        )

    def source_text(self, location: Optional[Location]) -> str:
        """Source text of a range. For fixed format, drops sequence numbers and comment lines."""
        if location is None or location.path is None or location.line < 1:
            return ""
        if location.path not in self._lines:
            try:
                with open(location.path, encoding="utf-8", errors="replace", newline="") as f:
                    self._lines[location.path] = f.read().splitlines()
            except OSError:
                self._lines[location.path] = []
        lines = self._lines[location.path]
        out = []
        for index in range(location.line - 1, min(location.end_line, len(lines))):
            text = lines[index]
            first, last = index == location.line - 1, index == location.end_line - 1
            if self.fixed_format and not first and len(text) > 6 and text[6] in "*/":
                continue
            lo = location.column - 1 if first else (7 if self.fixed_format else 0)
            hi = location.end_column - 1 if last else len(text)
            if self.fixed_format:
                hi = min(hi, 72)
            out.append(text[lo:hi].rstrip())
        return "\n".join(out).strip()


class Program:
    """A COBOL program (PROGRAM-ID) with typed data items, paragraphs and statements."""

    def __init__(self, node: Node):
        self.node = node
        self.file = node.graph
        self.name: str = node.data.get("programName", "")

    def __repr__(self) -> str:
        return f"<Program {self.name}>"

    def _own(self) -> Iterator[Node]:
        """Nodes of this program, excluding nested programs."""
        stack = list(reversed(self.node.children))
        while stack:
            n = stack.pop()
            if n.kind == "ProgramNode":
                continue
            yield n
            stack.extend(reversed(n.children))

    @cached_property
    def _items(self) -> dict[str, "DataItem"]:
        return {n.id: DataItem(self, n) for n in self._own() if is_data_item(n)}

    @property
    def data_items(self) -> list["DataItem"]:
        """Top-level data items (01, 77 and FD entries), in source order."""
        return [i for i in self._items.values() if i.parent is None]

    @property
    def all_data_items(self) -> list["DataItem"]:
        return list(self._items.values())

    def data_item(self, name: str) -> Optional["DataItem"]:
        return next((i for i in self._items.values() if i.name == name.upper()), None)

    def item(self, node: Node) -> Optional["DataItem"]:
        return self._items.get(node.id)

    @cached_property
    def paragraphs(self) -> list["Paragraph"]:
        return [Paragraph(self, n) for n in self._own() if n.kind == "ParagraphNode"]

    @cached_property
    def sections(self) -> list["Paragraph"]:
        return [Paragraph(self, n) for n in self._own() if n.node_type == "PROCEDURE_SECTION"]

    def paragraph(self, name: str) -> Optional["Paragraph"]:
        name = name.upper()
        return next((p for p in self.paragraphs + self.sections if p.name == name), None)

    @cached_property
    def statements(self) -> list["Statement"]:
        """Every statement in the procedure division, nested statements included."""
        return [statement(self, n) for n in self._own() if n.node_type in STATEMENT_NODE_TYPES]

    def _of(self, cls):
        return [s for s in self.statements if isinstance(s, cls)]

    calls = property(lambda self: self._of(Call))
    performs = property(lambda self: self._of(Perform))
    cics = property(lambda self: self._of(Cics))
    sql = property(lambda self: self._of(Sql))
    dli = property(lambda self: self._of(Dli))

    @cached_property
    def file_io(self) -> list["FileIo"]:
        """READ, WRITE, REWRITE, DELETE and START statements, and one OPEN entry per file."""
        return [FileIo(self, n) for n in self._own()
                if n.kind in ("FileOperationStatementNode", "OpenStatementNode")]

    @cached_property
    def files(self) -> list["FileControl"]:
        """SELECT entries with their ASSIGN names and FD records."""
        return [FileControl(self, n) for n in self._own() if n.kind == "FileEntryNode"]

    def file_control(self, name: str) -> Optional["FileControl"]:
        return next((f for f in self.files if f.name == name.upper()), None)

    @property
    def copybooks(self) -> list[str]:
        return [n.name for n in self._own() if n.kind == "CopyNode"]

    def resolve(self, text: Optional[str]) -> tuple[Optional[str], str]:
        """Resolve a program or resource name: a literal, a data item with a literal VALUE, or
        unresolved. Returns (name, how) where how is "literal", "value" or "unresolved"."""
        if text is None:
            return None, "unresolved"
        value = literal(text)
        if value is not None:
            return value.strip(), "literal"
        item = self.data_item(text.split()[0]) if text.split() else None
        if item is not None and literal(item.value) is not None:
            return literal(item.value).strip(), "value"
        return None, "unresolved"

    def moved_values(self, name: str) -> list[str]:
        """Names this program MOVEs into a data item: literals, or data items with a literal VALUE.
        The item can also get its value from a caller, so this list may be incomplete."""
        values = []
        for s in self.statements:
            if s.verb != "MOVE":
                continue
            match = re.match(r"MOVE\s+(.+?)\s+TO\s+(.+)$", " ".join(s.source.split()), re.IGNORECASE)
            targets = re.split(r"[\s,]+", match.group(2).upper().rstrip(".")) if match else []
            if name.upper() in targets:
                value, _ = self.resolve(match.group(1))
                if value and value not in values:
                    values.append(value)
        return values


def is_data_item(node: Node) -> bool:
    return node.node_type == "VARIABLE" and "variableType" in node.data


class DataItem:
    """A data description entry: group, elementary item, table, 88 condition or FD."""

    def __init__(self, program: Program, node: Node):
        self.program = program
        self.node = node

    def __repr__(self) -> str:
        return f"<DataItem {self.level} {self.name} {self.pic or ''}>"

    name = property(lambda self: self.node.data["name"])
    level = property(lambda self: self.node.data.get("level"))
    type = property(lambda self: self.node.data["variableType"])
    pic = property(lambda self: self.node.data.get("picClause"))
    usage = property(lambda self: self.node.data.get("usageFormat"))
    occurs = property(lambda self: self.node.data.get("occursTimes"))
    sync = property(lambda self: self.node.data.get("synchronizedClause", False))
    sync_direction = property(lambda self: self.node.data.get("synchronizedDirection"))
    location = property(lambda self: self.node.location)

    @property
    def value(self) -> Optional[str]:
        value = self.node.data.get("value")
        return value or None

    @property
    def condition_values(self) -> list[dict]:
        """For an 88 level: the VALUE entries as {"from": ..., "to": ...}."""
        return self.node.data.get("valueIntervals", [])

    @property
    def copybook(self) -> Optional[str]:
        return self.location.copybook if self.location else None

    @property
    def parent(self) -> Optional["DataItem"]:
        return next((self.program.item(a) for a in self.node.ancestors() if is_data_item(a)), None)

    @property
    def children(self) -> list["DataItem"]:
        return [self.program.item(c) for c in self.node.children if is_data_item(c)]

    @property
    def redefines(self) -> Optional["DataItem"]:
        if not self.node.data.get("redefines"):
            return None
        usage = next((c for c in self.node.children if c.kind == "VariableUsageNode"), None)
        target = usage.refs("definitions") if usage else []
        return self.program.item(target[0]) if target else None

    @property
    def file(self) -> Optional[str]:
        """The FD this record belongs to, if any."""
        for node in [self.node, *self.node.ancestors()]:
            if node.kind == "FileDescriptionNode":
                return node.name
        return None

    @property
    def references(self) -> list["Reference"]:
        """Every usage of this item in the program, with the statement that contains it."""
        return self.program.file._references.get(self.node.id, [])


@dataclass(frozen=True)
class Reference:
    node: Node
    statement: Optional["Statement"]

    @property
    def location(self) -> Optional[Location]:
        return self.node.location




class Paragraph:
    """A paragraph or procedure section."""

    def __init__(self, program: Program, node: Node):
        self.program = program
        self.node = node

    def __repr__(self) -> str:
        return f"<Paragraph {self.name}>"

    @property
    def name(self) -> str:
        if self.node.name:
            return self.node.name
        named = next((c for c in self.node.children if c.kind == "SectionNameNode"), None)
        return named.name if named else ""

    location = property(lambda self: self.node.location)
    is_section = property(lambda self: self.node.node_type == "PROCEDURE_SECTION")

    @property
    def statements(self) -> list["Statement"]:
        return [s for s in self.program.statements if s.paragraph == self]

    @property
    def performs(self) -> list["Perform"]:
        return [s for s in self.statements if isinstance(s, Perform)]

    @property
    def performed_by(self) -> list["Perform"]:
        return [p for p in self.program.performs if p.target == self]

    def __eq__(self, other) -> bool:
        return isinstance(other, Paragraph) and other.node is self.node

    def __hash__(self) -> int:
        return hash(self.node.id)


class Statement:
    """A procedure statement. ``verb`` is the first word of its source text."""

    def __init__(self, program: Program, node: Node):
        self.program = program
        self.node = node

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.verb} {self.location}>"

    location = property(lambda self: self.node.location)
    source = property(lambda self: self.node.source)

    @property
    def verb(self) -> str:
        words = self.source.split(None, 1)
        return words[0].upper().rstrip(".") if words else self.node.node_type

    @property
    def paragraph(self) -> Optional[Paragraph]:
        for a in self.node.ancestors():
            if a.kind == "ParagraphNode" or a.node_type == "PROCEDURE_SECTION":
                return Paragraph(self.program, a)
        return None

    @property
    def data_items(self) -> list[DataItem]:
        """Data items this statement uses."""
        found = []
        for n in self.node.walk():
            if n.kind == "VariableUsageNode":
                found += [self.program.item(t) for t in n.refs("definitions") if self.program.item(t)]
        return found

    def __eq__(self, other) -> bool:
        return isinstance(other, Statement) and other.node is self.node

    def __hash__(self) -> int:
        return hash(self.node.id)


class Perform(Statement):
    """PERFORM of a paragraph or section, or an inline PERFORM (target is None)."""

    @property
    def target_name(self) -> Optional[str]:
        target = self.node.data.get("target")
        return target.get("name") if target else None

    @property
    def thru_name(self) -> Optional[str]:
        thru = self.node.data.get("thru")
        return thru.get("name") if thru else None

    verb = property(lambda self: "PERFORM")

    @property
    def target(self) -> Optional[Paragraph]:
        return self.program.paragraph(self.target_name) if self.target_name else None

    @property
    def thru(self) -> Optional[Paragraph]:
        return self.program.paragraph(self.thru_name) if self.thru_name else None


class GoTo(Statement):
    @property
    def targets(self) -> list[str]:
        return self.node.data.get("targets", [])


class Call(Statement):
    """CALL. ``target`` is the literal program name; a dynamic CALL has ``dynamic`` True and the
    identifier in ``expression``."""

    @property
    def target(self) -> Optional[str]:
        named = next((c for c in self.node.children if c.kind == "SubroutineNameNode"), None)
        return named.name if named else None

    @property
    def dynamic(self) -> bool:
        return self.target is None

    @property
    def expression(self) -> str:
        if self.target:
            return f"'{self.target}'"
        match = re.match(r"CALL\s+(\S+)", self.source, re.IGNORECASE)
        return match.group(1) if match else ""


class Cics(Statement):
    """EXEC CICS. ``command`` is as reported by the parser (for example ``SEND MAP``);
    ``verb`` is its first word."""

    command = property(lambda self: self.node.data.get("command", ""))
    options = property(lambda self: [(o["name"], o.get("value")) for o in self.node.data.get("options", [])])

    @property
    def verb(self) -> str:
        return self.command.split()[0] if self.command else "EXEC"

    def option(self, name: str) -> Optional[str]:
        return next((v for n, v in self.options if n == name.upper()), None)

    def has(self, name: str) -> bool:
        return any(n == name.upper() for n, _ in self.options)

    @property
    def program_name(self) -> Optional[str]:
        return self.option("PROGRAM")

    @property
    def file_name(self) -> Optional[str]:
        return self.option("FILE") or self.option("DATASET")

    @property
    def queue_name(self) -> Optional[str]:
        return self.option("QUEUE") or self.option("QNAME")


class Sql(Statement):
    """EXEC SQL. For OPEN, FETCH and CLOSE, ``tables`` comes from the cursor's DECLARE."""

    statement_type = property(lambda self: self.node.data.get("statementType", ""))
    cursor = property(lambda self: self.node.data.get("cursorName"))
    verb = property(lambda self: self.statement_type.split()[0] if self.statement_type else "EXEC")

    @property
    def tables(self) -> list[str]:
        tables = self.node.data.get("tables", [])
        if tables or not self.cursor or self.statement_type == "DECLARE CURSOR":
            return tables
        declare = next((s for s in self.program.sql
                        if s.statement_type == "DECLARE CURSOR" and s.cursor == self.cursor), None)
        return declare.node.data.get("tables", []) if declare else []


class Dli(Statement):
    """EXEC DLI. ``segments`` lists SEGMENT option values."""

    command = property(lambda self: self.node.data.get("command", ""))
    verb = property(lambda self: self.command)
    options = Cics.options
    option = Cics.option

    @property
    def segments(self) -> list[str]:
        return [v.strip("() ") for n, v in self.options if n == "SEGMENT" and v]


class FileIo(Statement):
    """OPEN, READ, WRITE, REWRITE, DELETE or START on a batch file."""

    @property
    def verb(self) -> str:
        return self.node.node_type.replace("_STATEMENT", "")

    @property
    def mode(self) -> Optional[str]:
        """OPEN mode: INPUT, OUTPUT, I_O or EXTEND."""
        return self.node.data.get("fileOperationKind")

    @property
    def file(self) -> Optional["FileControl"]:
        name = (self.node.data.get("filename") or {}).get("name")
        if not name:
            return None
        found = self.program.file_control(name)
        if found is None:  # WRITE and REWRITE name a record; find its FD.
            item = self.program.data_item(name)
            found = self.program.file_control(item.file) if item and item.file else None
        return found


def statement(program: Program, node: Node) -> Statement:
    kind = node.kind
    if kind.startswith("ExecCics"):
        return Cics(program, node)
    cls = {
        "ExecSqlNode": Sql, "ExecDliNode": Dli, "SubroutineNode": Call, "PerformNode": Perform,
        "GoToNode": GoTo, "FileOperationStatementNode": FileIo,
    }.get(kind, Statement)
    return cls(program, node)


class FileControl:
    """A SELECT entry: the program's file name, its ASSIGN name (the JCL DD name) and FD records."""

    def __init__(self, program: Program, node: Node):
        self.program = program
        self.node = node
        self.clause = node.data.get("fileControlClause", "")

    def __repr__(self) -> str:
        return f"<FileControl {self.name} -> {self.assign}>"

    name = property(lambda self: self.node.data.get("fileName", "").upper())
    location = property(lambda self: self.node.location)

    def _clause(self, pattern: str) -> Optional[str]:
        match = re.search(pattern, self.clause, re.IGNORECASE)
        return match.group(1).upper() if match else None

    @property
    def assign(self) -> Optional[str]:
        """The ASSIGN name with any device or organization prefix (UT-S-, AS-, ...) removed."""
        name = self._clause(r"ASSIGN\s+(?:TO\s+)?(\S+)")
        name = literal(name) or name
        return name.split("-")[-1] if name else None

    organization = property(lambda self: self._clause(r"ORGANIZATION\s+(?:IS\s+)?(\w+)") or "SEQUENTIAL")
    access_mode = property(lambda self: self._clause(r"ACCESS\s+(?:MODE\s+)?(?:IS\s+)?(\w+)") or "SEQUENTIAL")
    record_key = property(lambda self: self._clause(r"RECORD\s+KEY\s+(?:IS\s+)?([\w-]+)"))
    status = property(lambda self: self._clause(r"STATUS\s+(?:IS\s+)?([\w-]+)"))

    @property
    def records(self) -> list[DataItem]:
        fd = next((i for i in self.program.data_items if i.type == "FD" and i.name == self.name), None)
        return fd.children if fd else []


@dataclass(frozen=True)
class CallEdge:
    """A transfer of control to another program: CALL, or EXEC CICS LINK, XCTL or LOAD."""

    program: Program
    statement: Statement
    via: str  # CALL, LINK, XCTL or LOAD
    target: Optional[str]
    resolved: str  # literal, value or unresolved
    expression: str
    candidates: tuple = ()  # for an unresolved target: names the program MOVEs into it


@dataclass(frozen=True)
class Access:
    """A read or write of stored data."""

    program: Program
    statement: Statement
    store: str  # db2, vsam, file, ims or queue
    resource: Optional[str]
    mode: str  # read, write or read-write
    resolved: str  # literal, value, declared or unresolved
    expression: str

    @property
    def paragraph(self) -> Optional[Paragraph]:
        return self.statement.paragraph


def call_edges(program: Program) -> Iterator[CallEdge]:
    for s in program.calls:
        target, how = (s.target, "literal") if s.target else program.resolve(s.expression)
        moved = tuple(program.moved_values(s.expression)) if target is None else ()
        yield CallEdge(program, s, "CALL", target, how, s.expression, moved)
    for s in program.cics:
        if s.verb in CICS_PROGRAM_TRANSFERS and s.program_name:
            target, how = program.resolve(s.program_name)
            moved = tuple(program.moved_values(s.program_name)) if target is None else ()
            yield CallEdge(program, s, s.verb, target, how, s.program_name, moved)


def data_access(program: Program) -> Iterator[Access]:
    for s in program.sql:
        mode = "read" if s.statement_type in SQL_READS else "write" if s.statement_type in SQL_WRITES else None
        if mode and s.statement_type != "DECLARE CURSOR":
            for table in s.tables:
                yield Access(program, s, "db2", table, mode, "declared", table)
    for s in program.cics:
        if s.verb in CICS_FILE_READS | CICS_FILE_WRITES and s.file_name:
            resource, how = program.resolve(s.file_name)
            mode = "read" if s.verb in CICS_FILE_READS else "write"
            yield Access(program, s, "vsam", resource, mode, how, s.file_name)
        elif s.verb in CICS_QUEUE_READS | CICS_QUEUE_WRITES and s.queue_name:
            resource, how = program.resolve(s.queue_name)
            mode = "read" if s.verb in CICS_QUEUE_READS else "write"
            yield Access(program, s, "queue", resource, mode, how, s.queue_name)
    for s in program.dli:
        if s.verb in DLI_READS | DLI_WRITES:
            mode = "read" if s.verb in DLI_READS else "write"
            for segment in s.segments or [None]:
                yield Access(program, s, "ims", segment, mode, "literal" if segment else "unresolved",
                             segment or "")
    for s in program.file_io:
        f = s.file
        if s.verb == "OPEN":
            mode = {"INPUT": "read", "OUTPUT": "write", "EXTEND": "write"}.get(s.mode or "", "read-write")
        else:
            mode = "read" if s.verb in ("READ", "START") else "write"
        name = f.assign if f else None
        yield Access(program, s, "file", name, mode, "declared" if name else "unresolved",
                     f.name if f else "")


class Project:
    """All graph files of an application, with cross-program relationships."""

    def __init__(self, files: Iterable[SourceFile]):
        self.files = list(files)
        self.programs: dict[str, Program] = {}
        for f in self.files:
            for p in f.programs:
                self.programs.setdefault(p.name, p)

    @classmethod
    def load(cls, directory: str | os.PathLike, **kwargs) -> "Project":
        """Load a store (a folder with map.db) as of its latest run, or a folder of graph files."""
        if (Path(directory) / "map.db").is_file():
            from .store import load_project

            return load_project(directory, **kwargs)
        paths = sorted(Path(directory).glob("*.json"))
        return cls(SourceFile.load(p, **kwargs) for p in paths)

    def program(self, name: str) -> Optional[Program]:
        return self.programs.get(name.upper())

    def calls(self) -> list[CallEdge]:
        return [e for p in self.programs.values() for e in call_edges(p)]

    def callers(self, name: str, candidates: bool = False) -> list[CallEdge]:
        """Edges to a program. With ``candidates``, also unresolved edges that may reach it."""
        name = name.upper()
        return [e for e in self.calls() if e.target == name or (candidates and name in e.candidates)]

    def data_access(self) -> list[Access]:
        return [a for p in self.programs.values() for a in data_access(p)]


def load(path: str | os.PathLike, **kwargs) -> SourceFile:
    """Load one graph file."""
    return SourceFile.load(path, **kwargs)
