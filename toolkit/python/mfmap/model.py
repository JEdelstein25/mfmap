# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Typed access to the graph output of ``server.jar analysis --graph`` (schema graph-v1)."""

from __future__ import annotations

import collections
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
DLI_HOLDS = {"GHU", "GHN", "GHNP"}
DLI_COMMITS = {"CHKP", "SYMCHKP", "SYNC", "ROLB", "ROLL"}
DLI_INTERFACES = {"CBLTDLI", "AIBTDLI", "CEETDLI"}  # CALL interfaces to IMS DL/I, not programs
MQ_READS = {"MQGET"}
MQ_WRITES = {"MQPUT", "MQPUT1"}


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
        # The PROGRAM-ID. ``name`` differs from it only when Project names a duplicate after its file.
        self.program_id: str = self.name

    def __repr__(self) -> str:
        return f"<Program {self.name}>"

    def _own(self) -> list[Node]:
        """Nodes of this program in pre-order, excluding nested programs; walked once."""
        if "_nodes" not in self.__dict__:
            nodes, stack = [], list(reversed(self.node.children))
            while stack:
                n = stack.pop()
                if n.kind == "ProgramNode":
                    continue
                nodes.append(n)
                stack.extend(reversed(n.children))
            self.__dict__["_nodes"] = nodes
        return self.__dict__["_nodes"]

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

    @cached_property
    def _items_by_name(self) -> dict[str, "DataItem"]:
        by_name: dict[str, DataItem] = {}
        for i in self._items.values():
            by_name.setdefault(i.name, i)  # the first definition, as before
        return by_name

    def data_item(self, name: str) -> Optional["DataItem"]:
        return self._items_by_name.get(name.upper())

    def item(self, node: Node) -> Optional["DataItem"]:
        return self._items.get(node.id)

    @cached_property
    def paragraphs(self) -> list["Paragraph"]:
        return [Paragraph(self, n) for n in self._own() if n.kind == "ParagraphNode"]

    @cached_property
    def sections(self) -> list["Paragraph"]:
        return [Paragraph(self, n) for n in self._own() if n.node_type == "PROCEDURE_SECTION"]

    @cached_property
    def _paragraphs_by_name(self) -> dict[str, "Paragraph"]:
        by_name: dict[str, Paragraph] = {}
        for p in self.paragraphs + self.sections:
            by_name.setdefault(p.name, p)
        return by_name

    @cached_property
    def _paragraphs_by_node(self) -> dict[str, "Paragraph"]:
        return {p.node.id: p for p in self.paragraphs + self.sections}

    def paragraph(self, name: str) -> Optional["Paragraph"]:
        return self._paragraphs_by_name.get(name.upper())

    @cached_property
    def _statements_by_paragraph(self) -> dict[Optional[str], list["Statement"]]:
        index: dict[Optional[str], list[Statement]] = {}
        for s in self.statements:
            index.setdefault(s.paragraph.node.id if s.paragraph else None, []).append(s)
        return index

    @cached_property
    def _performs_by_target(self) -> dict[str, list["Perform"]]:
        index: dict[str, list[Perform]] = {}
        for p in self.performs:
            if p.target is not None:
                index.setdefault(p.target.node.id, []).append(p)
        return index

    @cached_property
    def statements(self) -> list["Statement"]:
        """Every statement in the procedure division, nested statements included."""
        return [statement(self, n) for n in self._own() if n.node_type in STATEMENT_NODE_TYPES]

    @cached_property
    def _by_class(self) -> dict[type, list["Statement"]]:
        index: dict[type, list[Statement]] = {}
        for s in self.statements:
            index.setdefault(type(s), []).append(s)
        return index

    def _of(self, cls):
        return self._by_class.get(cls, [])

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
            source, targets = move_parts(s)
            if name.upper() in targets:
                value, _ = self.resolve(source)
                if value and value not in values:
                    values.append(value)
        return values


def move_parts(s: "Statement") -> tuple[Optional[str], list[str]]:
    """For a MOVE: the sending text and the upper-case words of the receiving list (names, OF
    qualifiers). Otherwise (None, [])."""
    if s.verb != "MOVE":
        return None, []
    match = re.match(r"MOVE\s+(.+?)\s+TO\s+(.+)$", " ".join(s.source.split()), re.IGNORECASE)
    return (match.group(1), re.split(r"[\s,]+", match.group(2).upper().rstrip("."))) if match else (None, [])


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
    @property
    def _occurs_clause(self) -> dict:
        return self.node.data.get("occursClause") or {}

    @property
    def occurs(self) -> Optional[int]:
        """How many times the item occurs: the TO value of OCCURS n TO m, otherwise n."""
        clause = self._occurs_clause
        return clause.get("to") or clause.get("from") or self.node.data.get("occursTimes")

    @property
    def occurs_min(self) -> Optional[int]:
        """n of OCCURS n TO m; None for a fixed table."""
        clause = self._occurs_clause
        return clause.get("from") if clause.get("to") is not None else None

    depending_on = property(lambda self: self._occurs_clause.get("dependingOn"))
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
        return self.program._statements_by_paragraph.get(self.node.id, [])

    @property
    def performs(self) -> list["Perform"]:
        return [s for s in self.statements if isinstance(s, Perform)]

    @property
    def performed_by(self) -> list["Perform"]:
        return self.program._performs_by_target.get(self.node.id, [])

    def __eq__(self, other) -> bool:
        return isinstance(other, Paragraph) and other.node is self.node

    def __hash__(self) -> int:
        return hash(self.node.id)


class Statement:
    """A procedure statement. ``verb`` is the first word of its source text. ``condition`` is an
    IF's condition, a PERFORM's UNTIL condition or an EVALUATE's subject, as written."""

    def __init__(self, program: Program, node: Node):
        self.program = program
        self.node = node

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.verb} {self.location}>"

    location = property(lambda self: self.node.location)
    source = property(lambda self: self.node.source)

    def _text(self, node: Node, field: str) -> Optional[str]:
        """Source text at a locality field of a node, on one line."""
        location = node.graph._location(node.data.get(field))
        return " ".join(node.graph.source_text(location).split()) if location else None

    @property
    def condition(self) -> Optional[str]:
        if self.node.kind == "EvaluateNode":
            return self._text(self.node, "subjectLocality")
        if self.node.kind == "IfNode":
            return self._text(self.node, "conditionLocality")
        pending = list(self.node.children)
        while pending:  # an inline PERFORM's UNTIL, but not a nested statement's
            node = pending.pop(0)
            if node.kind == "PerformUntilNode":
                return self._text(node, "conditionLocality")
            if node.node_type not in STATEMENT_NODE_TYPES:
                pending.extend(node.children)
        return None

    @property
    def when(self) -> list[str]:
        """An EVALUATE's WHEN conditions as written, in order; WHEN OTHER is "OTHER"."""
        return [self._text(c, "conditionLocality") if c.kind == "EvaluateWhenNode" else "OTHER"
                for c in self.node.children if c.kind in ("EvaluateWhenNode", "EvaluateWhenOtherNode")]

    @property
    def verb(self) -> str:
        words = self.source.split(None, 1)
        return words[0].upper().rstrip(".") if words else self.node.node_type

    @cached_property
    def paragraph(self) -> Optional[Paragraph]:
        for a in self.node.ancestors():
            if a.kind == "ParagraphNode" or a.node_type == "PROCEDURE_SECTION":
                return self.program._paragraphs_by_node.get(a.id) or Paragraph(self.program, a)
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


    @property
    def arguments(self) -> list[Node]:
        """The data names in USING, in order (for a dynamic CALL, after the program's)."""
        refs = [c for c in self.node.children if c.kind == "QualifiedReferenceNode"]
        return refs[1:] if self.dynamic else refs


class DliCall:
    """A CALL 'CBLTDLI' (or AIBTDLI, CEETDLI) USING [count,] function, PCB, I/O area, SSAs.

    ``functions`` are the codes the function argument can hold: its VALUE (``how`` "value"), or
    else what the program MOVEs into it (``how`` "unresolved"). ``segment`` is named by the last
    SSA: the first 8 bytes of its VALUE, or of its first subordinate item's VALUE."""

    def __init__(self, call: "Call"):
        self.call = call
        program = call.program
        refs = call.arguments
        items = [program.item((a.refs("variableDefinitionNode") or [None])[0]) if a.refs("variableDefinitionNode")
                 else None for a in refs]
        names = [i.name if i else a.source.strip() for i, a in zip(items, refs)]
        if items and items[0] is not None and items[0].pic and re.fullmatch(r"S?9[\d()]*", items[0].pic.upper()) \
                and items[0].value and literal(items[0].value) is None:
            items, names = items[1:], names[1:]  # an optional argument count comes first
        self.expression = " ".join(names)
        function, self.how = program.resolve(names[0]) if names else (None, "unresolved")
        self.functions = (function.upper(),) if function else \
            tuple(dict.fromkeys(v.strip().upper() for v in program.moved_values(names[0]))) if names else ()
        self.pcb = names[1].upper() if len(names) > 1 else None
        self.area = names[2].upper() if len(names) > 2 else None
        self.ssas = names[3:]
        self.segment = self._segment(items[-1]) if len(items) > 3 else None

    @staticmethod
    def _segment(item: Optional["DataItem"]) -> Optional[str]:
        while item is not None:
            value = literal(item.value)
            if value:
                return value[:8].strip() or None
            item = item.children[0] if item.children else None
        return None


def dli_calls(program: "Program") -> list[DliCall]:
    """The program's DL/I calls: CALL 'CBLTDLI', or a dynamic CALL whose item holds that name."""
    return [DliCall(s) for s in program.calls
            if (s.target or program.resolve(s.expression)[0] or "").upper() in DLI_INTERFACES]


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
    """EXEC SQL. For OPEN, FETCH and CLOSE, ``tables`` comes from the cursor's DECLARE.
    ``procedure`` is a CALL's procedure name or host variable (with its colon); ``statement_name``
    names a prepared statement; ``sql_source`` is where PREPARE or EXECUTE IMMEDIATE gets its SQL
    text: a host variable (with its colon) or a string literal. ``columns`` are the INSERT columns,
    the SELECT list or the UPDATE SET columns; ``values`` the INSERT VALUES, UPDATE SET or SET
    values in the same order; ``into`` the host variables that receive values (SELECT INTO, FETCH
    INTO, SET); ``where``, ``order_by`` and ``fetch_first`` the statement's own WHERE, ORDER BY
    and FETCH FIRST; ``table_columns`` a DECLARE TABLE's column definitions. All are as written."""

    statement_type = property(lambda self: self.node.data.get("statementType", ""))
    cursor = property(lambda self: self.node.data.get("cursorName"))
    procedure = property(lambda self: self.node.data.get("procedureName"))
    statement_name = property(lambda self: self.node.data.get("statementName"))
    sql_source = property(lambda self: self.node.data.get("sqlSource"))
    columns = property(lambda self: self.node.data.get("columns", []))
    values = property(lambda self: self.node.data.get("values", []))
    into = property(lambda self: self.node.data.get("into", []))
    where = property(lambda self: self.node.data.get("where"))
    order_by = property(lambda self: self.node.data.get("orderBy"))
    fetch_first = property(lambda self: self.node.data.get("fetchFirst"))
    table_columns = property(lambda self: self.node.data.get("tableColumns", []))
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
    """A transfer of control to another program: CALL, EXEC CICS LINK, XCTL or LOAD, or a Db2
    stored procedure CALL (via ``SQL CALL``; the target is the procedure name, not its program)."""

    program: Program
    statement: Statement
    via: str  # CALL, LINK, XCTL, LOAD or SQL CALL
    target: Optional[str]
    resolved: str  # literal, value or unresolved
    expression: str
    candidates: tuple = ()  # for an unresolved target: names the program MOVEs into it


@dataclass(frozen=True)
class Access:
    """A read or write of stored data."""

    program: Program
    statement: Statement
    store: str  # db2, vsam, file, ims, ims-message, queue (CICS TS/TD) or mq
    resource: Optional[str]
    mode: str  # read, write, read-write, or unknown for dynamic SQL
    resolved: str  # literal, value, declared, inferred or unresolved
    expression: str
    candidates: tuple = ()  # for dynamic SQL or an MQ queue: what the program MOVEs into the item

    @property
    def paragraph(self) -> Optional[Paragraph]:
        return self.statement.paragraph


def call_edges(program: Program) -> Iterator[CallEdge]:
    dli = {c.call.node.id for c in dli_calls(program)}
    for s in program.calls:
        if s.node.id in dli:
            continue  # a DL/I call is data access or a commit point, not a call to another program
        target, how = (s.target, "literal") if s.target else program.resolve(s.expression)
        moved = tuple(program.moved_values(s.expression)) if target is None else ()
        yield CallEdge(program, s, "CALL", target, how, s.expression, moved)
    for s in program.cics:
        if s.verb in CICS_PROGRAM_TRANSFERS and s.program_name:
            target, how = program.resolve(s.program_name)
            moved = tuple(program.moved_values(s.program_name)) if target is None else ()
            yield CallEdge(program, s, s.verb, target, how, s.program_name, moved)
    for s in program.sql:
        if s.statement_type == "CALL" and s.procedure:
            if s.procedure.startswith(":"):
                name = s.procedure[1:]
                target, how = program.resolve(name)
                moved = tuple(program.moved_values(name)) if target is None else ()
                yield CallEdge(program, s, "SQL CALL", target, how, name, moved)
            else:
                yield CallEdge(program, s, "SQL CALL", s.procedure, "literal", s.procedure)


def mq_queues(program: Program) -> dict["Call", list[str]]:
    """The queue-name items each MQGET, MQPUT and MQPUT1 uses. MQPUT1 names its queue in the object
    descriptor; MQGET and MQPUT use a handle from MQOPEN. A queue name is the last item MOVEd into
    MQOD-OBJECTNAME in the paragraph before the MQOPEN or MQPUT1, else any item MOVEd into it. A handle
    keeps its queue through MOVEs later in the MQOPEN's paragraph, and a MOVE into the handle earlier
    in the MQGET's or MQPUT's paragraph says which handle it uses."""

    def before(s):
        siblings = s.paragraph.statements if s.paragraph else program.statements
        return [m for m in siblings if m.location and s.location and m.location.line < s.location.line]

    def object_names(s, od):
        def into(targets):
            if "MQOD-OBJECTNAME" not in targets:
                return False
            rest = targets[targets.index("MQOD-OBJECTNAME") + 1:]
            return not rest or rest[0] not in ("OF", "IN") or rest[1:2] == [od.upper()]
        near = [move_parts(m)[0] for m in before(s) if into(move_parts(m)[1])]
        if near:
            return near[-1:]
        return list(dict.fromkeys(src for src, t in map(move_parts, program.statements) if into(t)))

    def arg_names(s):
        return [(program.item(a.refs("variableDefinitionNode")[0]).name if a.refs("variableDefinitionNode")
                 and program.item(a.refs("variableDefinitionNode")[0]) else a.source.strip()) for a in s.arguments]

    calls = [(s, (s.target or "").upper(), arg_names(s)) for s in program.calls]
    handles = collections.defaultdict(list)
    for s, target, args in calls:
        if target == "MQOPEN" and len(args) >= 4:
            names = object_names(s, args[1])
            handles[args[3].upper()] += names
            siblings = s.paragraph.statements if s.paragraph else program.statements
            for m in siblings:
                src, targets = move_parts(m)
                if m.location and s.location and m.location.line > s.location.line and (src or "").upper() == args[3].upper():
                    for t in targets:
                        handles[t] += names
    out = {}
    for s, target, args in calls:
        if target == "MQPUT1" and len(args) >= 2:
            out[s] = object_names(s, args[1])
        elif target in MQ_READS | MQ_WRITES and len(args) >= 2:
            handle = args[1].upper()
            moved = [src for src, t in map(move_parts, before(s)) if handle in t]
            out[s] = list(dict.fromkeys(handles[(moved[-1] if moved else handle).upper()]))
    return out


def data_access(program: Program) -> Iterator[Access]:
    for s in program.sql:
        mode = "read" if s.statement_type in SQL_READS else "write" if s.statement_type in SQL_WRITES else None
        if mode and s.statement_type != "DECLARE CURSOR":
            for table in s.tables:
                yield Access(program, s, "db2", table, mode, "declared", table)
        elif s.statement_type in ("PREPARE", "EXECUTE IMMEDIATE") and s.sql_source:
            # Dynamic SQL: the tables are only known at run time.
            source = s.sql_source
            if source.startswith(":"):
                source = source[1:]
                moved = tuple(program.moved_values(source))
            else:
                moved = (literal(source) or source,)
            yield Access(program, s, "db2", None, "unknown", "unresolved", source, moved)
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
    yield from dli_access(program)
    for s, names in mq_queues(program).items():
        mode = "read" if s.target.upper() in MQ_READS else "write"
        for name in names or [None]:
            resource, how = program.resolve(name)
            moved = tuple(program.moved_values(name)) if name and resource is None else ()
            yield Access(program, s, "mq", resource, mode, how, name or s.arguments[1].source.strip(), moved)
    for s in program.file_io:
        f = s.file
        if s.verb == "OPEN":
            mode = {"INPUT": "read", "OUTPUT": "write", "EXTEND": "write"}.get(s.mode or "", "read-write")
        else:
            mode = "read" if s.verb in ("READ", "START") else "write"
        name = f.assign if f else None
        yield Access(program, s, "file", name, mode, "declared" if name else "unresolved",
                     f.name if f else "")


def dli_access(program: Program) -> Iterator[Access]:
    """Reads and writes by DL/I calls. With an SSA, the access is of the segment the last SSA
    names. Without one, the segment is "inferred": REPL and DLET act on the segment a GHU, GHN or
    GHNP on the same PCB held, preferring one read into the same I/O area; other calls take the
    segment of an SSA call on the same PCB and I/O area. A call on a PCB that no call qualifies
    with an SSA is taken as a message call on the I/O or an alternate PCB (store ``ims-message``,
    resource the PCB); a GSAM PCB looks the same."""
    calls = dli_calls(program)
    qualified = {c.pcb for c in calls if c.ssas}
    by_area = {}
    for c in calls:
        if c.segment:
            by_area.setdefault((c.pcb, c.area), c.segment)
    for c in calls:
        modes = {"read" if f in DLI_READS else "write" for f in c.functions if f in DLI_READS | DLI_WRITES}
        if not c.functions:
            modes = {"unknown"}  # the function code is set at run time
        candidates = c.functions if c.how != "value" else ()
        for mode in sorted(modes):
            if c.ssas:
                yield Access(program, c.call, "ims", c.segment, mode, "value" if c.segment else "unresolved",
                             c.expression, candidates)
                continue
            holds = [h for h in calls if h.pcb == c.pcb and h.segment and set(h.functions) & DLI_HOLDS]
            held = tuple(dict.fromkeys(h.segment for h in [h for h in holds if h.area == c.area] or holds))
            if set(c.functions) <= {"REPL", "DLET"} and held:
                yield Access(program, c.call, "ims", held[0] if len(held) == 1 else None, mode,
                             "inferred" if len(held) == 1 else "unresolved", c.expression,
                             held if len(held) > 1 else ())
            elif (c.pcb, c.area) in by_area:
                yield Access(program, c.call, "ims", by_area[(c.pcb, c.area)], mode, "inferred", c.expression,
                             candidates)
            elif c.pcb not in qualified:
                yield Access(program, c.call, "ims-message", c.pcb, mode, "inferred", c.expression, candidates)
            else:
                yield Access(program, c.call, "ims", None, mode, "unresolved", c.expression, candidates)


@dataclass(frozen=True)
class CommitPoint:
    """Where a unit of work ends: EXEC SQL COMMIT or ROLLBACK, EXEC CICS SYNCPOINT, or an IMS
    checkpoint or rollback (CHKP, SYMCHKP, SYNC, ROLB or ROLL, by EXEC DLI or CALL 'CBLTDLI')."""

    program: Program
    statement: Statement
    kind: str  # COMMIT, ROLLBACK, SYNCPOINT, SYNCPOINT ROLLBACK, or the DL/I function


def commit_points(program: Program) -> Iterator[CommitPoint]:
    for s in program.sql:
        if s.statement_type in ("COMMIT", "ROLLBACK"):
            yield CommitPoint(program, s, s.statement_type)
    for s in program.cics:
        if s.verb == "SYNCPOINT":
            yield CommitPoint(program, s, "SYNCPOINT ROLLBACK" if s.has("ROLLBACK") or "ROLLBACK" in s.command
                              else "SYNCPOINT")
    for s in program.dli:
        if s.verb in DLI_COMMITS:
            yield CommitPoint(program, s, s.verb)
    for c in dli_calls(program):
        for f in c.functions:
            if f in DLI_COMMITS:
                yield CommitPoint(program, c.call, f)


class Project:
    """All graph files of an application, with cross-program relationships."""

    def __init__(self, files: Iterable[SourceFile]):
        self.files = list(files)
        # Programs named after their file because another file has the same PROGRAM-ID.
        self.renamed: list[Program] = []
        found: dict[str, list[tuple[str, int, Program]]] = {}
        for f in self.files:
            for i, p in enumerate(f.programs):
                found.setdefault(p.name, []).append((source_path(f), i, p))
        taken = set(found)
        for name, copies in found.items():
            # The program in the file named after it keeps the name; each other copy is named after
            # its file, as the build names the load module after the member.
            copies.sort(key=lambda c: (member_name(c[0]) != name, c[0]))
            for path, i, p in copies[1:]:
                stem = member_name(path)
                new = stem if i == 0 and stem not in taken else f"{name}@{stem or Path(path).parent.name}"
                while new in taken:
                    new += "@"
                taken.add(new)
                p.name = new
                self.renamed.append(p)
        self.programs: dict[str, Program] = {p.name: p for f in self.files for p in f.programs}

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


def source_path(f: SourceFile) -> str:
    """The source file's path as the store records it, else as the graph names it."""
    return getattr(f, "source", None) or f.path or ""


def member_name(path: str) -> str:
    """The member a source file would be built as: its name without the extension, in capitals."""
    return Path(path).stem.upper()


def load(path: str | os.PathLike, **kwargs) -> SourceFile:
    """Load one graph file."""
    return SourceFile.load(path, **kwargs)
