"""The YAML category file: a hardened parser and the export (INT-008, C-7, C-8, D6, ADR-0058 decision 1).

``parse_category_file`` is the one implementation behind the upload route and the tests. The input is untrusted:

1. The size is checked before anything is decoded, then the text (BOM, tabs, NUL) before anything is parsed.
2. Only the PyYAML *event stream* of the safe loader is read. Anchors, aliases, merge keys, tags, duplicate keys,
   complex keys, deep nesting and huge documents are refused on the events, and the tree is built from the events by
   this module itself. No YAML value is ever constructed by PyYAML, so ``no``, ``on`` and ``yes`` are the text they
   are and no object tag can run code.
3. The structure is read with fixed field names (unknown fields refused) and every rule of the policy is applied
   through the policy functions of this package, never copied.

A problem names the line and the field (``line 12, categories[0].senders[3]``) and a fixed text per rule. It never
contains a value from the file, not even a field name that the format does not define.

File format (``schema: 1``)::

    schema: 1
    generalInstructions: text          # optional
    archiveLabel: Assistant/Archive    # optional
    categories:
      - name: Huis/Energie
        kind: topic                    # optional: topic (default) or extra
        description: text
        senders:                       # optional
          - example.com                # a domain or a full address
          - entry: example.org         # a domain that also matches its subdomains
            subdomains: true
        notify: true                   # optional, default false
"""

from dataclasses import dataclass, field
from typing import Final

import yaml

from category_policy.kinds import Kind
from category_policy.policy import (
    ARCHIVE_LABEL_DEFAULT,
    Category,
    validate_archive_label,
    validate_instructions,
    validate_list,
)
from category_policy.senders import SenderCategory, SenderEntry, validate_entries

MAX_FILE_BYTES: Final = 256 * 1024
MAX_DEPTH: Final = 8
MAX_NODES: Final = 50_000
MAX_PROBLEMS: Final = 100
SCHEMA_VERSION: Final = "1"

_ROOT_KEYS: Final = frozenset({"schema", "generalInstructions", "archiveLabel", "categories"})
_CATEGORY_KEYS: Final = frozenset({"name", "kind", "description", "senders", "notify"})
_ENTRY_KEYS: Final = frozenset({"entry", "subdomains"})
_KNOWN_KEYS: Final = _ROOT_KEYS | _CATEGORY_KEYS | _ENTRY_KEYS
_UNKNOWN_SEGMENT: Final = "*"
_BOOLEANS: Final = {"true": True, "false": False}
_MERGE_KEY: Final = "<<"
_BOM: Final = "﻿"
_EXPORT_HEADER: Final = (
    "# Mail categories, schema 1. Edit this file and upload it again; see the template for every field.\n"
)
_POLICY_FIELDS: Final = {"instructions": "generalInstructions", "archive_label": "archiveLabel", "list": "categories"}

FILE_RULE_TEXT: Final[dict[str, str]] = {
    "file_too_large": "the file is larger than 256 KiB",
    "not_utf8": "the file is not valid UTF-8 text",
    "bom": "the file starts with a byte order mark; save it as plain UTF-8",
    "nul_byte": "the line contains a NUL character",
    "tab": "the line contains a tab; indent with spaces",
    "syntax": "this is not valid YAML",
    "empty_file": "the file has no content",
    "multiple_documents": "the file has more than one YAML document",
    "too_deep": "the nesting is too deep",
    "too_many_nodes": "the file has too many values",
    "too_many_problems": "more problems follow; fix these first",
    "anchor": "anchors are not allowed",
    "alias": "aliases are not allowed",
    "merge_key": "merge keys are not allowed",
    "tag": "tags are not allowed",
    "duplicate_key": "this field is written twice",
    "key_not_text": "a field name must be plain text",
    "not_mapping": "the file must be a mapping of fields",
    "unknown_field": "this field is not part of the format",
    "missing_field": "a required field is missing",
    "schema_unsupported": "schema must be exactly 1",
    "not_text": "this must be text",
    "not_list": "this must be a list",
    "not_map": "this must be a mapping of fields",
    "not_boolean": "this must be written as true or false",
    "kind_invalid": "kind must be topic or extra",
    "name_empty": "the name is empty",
    "name_segment_empty": "a part of the name between slashes is empty",
    "name_segment_too_long": "a part of the name is longer than 40 characters",
    "name_label_too_long": "the label for this name is too long",
    "name_forbidden_char": "the name has a forbidden character",
    "name_reserved": "the first part of the name is reserved",
    "name_duplicate": "another category has this name",
    "name_label_exists": "a label of this name exists already",
    "description_empty": "the description is empty",
    "description_too_long": "the description is too long",
    "instructions_too_long": "the general instructions are too long",
    "list_too_many": "the list has more categories than allowed",
    "archive_invalid": "the archive label is not a valid label name",
    "archive_system_label": "the archive label is a Gmail system label",
    "archive_inside_assistant": "the archive label may not lie inside Assistant/",
    "archive_category_label": "the archive label is a category label",
    "sender_invalid": "this is not a valid address or domain",
    "sender_too_many": "the category has more senders than allowed",
    "sender_duplicate": "this sender is listed twice",
    "sender_refused_domain": "this domain may not be listed as a domain entry",
}


@dataclass(frozen=True, slots=True)
class FileCategory:
    """One category as the file carries it.

    Attributes:
        name: The name, nested with ``/``, as typed.
        description: What mail belongs here, as typed.
        kind: ``topic`` or ``extra``.
        senders: The sender entries in file order.
        notify: Whether mail of this category is always notified.
    """

    name: str
    description: str
    kind: Kind = Kind.TOPIC
    senders: tuple[SenderEntry, ...] = ()
    notify: bool = False


@dataclass(frozen=True, slots=True)
class ParsedList:
    """A whole category list read from, or written to, a file.

    Attributes:
        general_instructions: The general instructions text ("" when absent).
        archive_label: The archive label name.
        categories: The categories in file order.
    """

    general_instructions: str
    archive_label: str
    categories: tuple[FileCategory, ...]


@dataclass(frozen=True, slots=True)
class FileProblem:
    """One refusal, with its place and a fixed text, never a value from the file.

    Attributes:
        rule: Stable rule id, a key of ``FILE_RULE_TEXT``.
        line: 1-based line in the file.
        field: The field path (``categories[0].senders[3]``), ``root`` or ``file``.
    """

    rule: str
    line: int
    field: str

    def __str__(self) -> str:
        """Return ``line 12, categories[0].senders[3]: <fixed text>``."""
        return f"line {self.line}, {self.field}: {FILE_RULE_TEXT[self.rule]}"


@dataclass(frozen=True, slots=True)
class FileProblems:
    """Every problem of a refused file."""

    problems: tuple[FileProblem, ...]

    def __str__(self) -> str:
        """Return one line per problem."""
        return "\n".join(str(problem) for problem in self.problems)


@dataclass(slots=True)
class _Scalar:
    value: str
    plain: bool
    line: int


@dataclass(slots=True)
class _Seq:
    line: int
    items: list["_Node"] = field(default_factory=list["_Node"])


@dataclass(slots=True)
class _Map:
    line: int
    pairs: list[tuple[_Scalar, "_Node"]] = field(default_factory=list[tuple[_Scalar, "_Node"]])


type _Node = _Scalar | _Seq | _Map


@dataclass(slots=True)
class _Frame:
    node: _Seq | _Map
    path: str
    pending_key: _Scalar | None = None
    seen: set[str] = field(default_factory=set[str])


class _Problems:
    """A capped collector of problems."""

    def __init__(self) -> None:
        self.items: list[FileProblem] = []
        self.full = False

    def add(self, rule: str, line: int, where: str) -> None:
        if len(self.items) >= MAX_PROBLEMS:
            self.full = True
            return
        self.items.append(FileProblem(rule, line, where))

    def result(self) -> FileProblems:
        items = sorted(self.items, key=lambda problem: problem.line)
        if self.full:
            items.append(FileProblem("too_many_problems", items[-1].line, "file"))
        return FileProblems(tuple(items))


def _segment(key: str) -> str:
    """A key as a path segment: only names the format defines are ever echoed."""
    return key if key in _KNOWN_KEYS else _UNKNOWN_SEGMENT


def _event_line(event: yaml.Event) -> int:
    return event.start_mark.line + 1 if event.start_mark is not None else 1


def _line_of(error: yaml.YAMLError, text: str) -> int:
    if isinstance(error, yaml.MarkedYAMLError) and error.problem_mark is not None:
        return error.problem_mark.line + 1
    if isinstance(error, yaml.reader.ReaderError):
        return text.count("\n", 0, max(error.position, 0)) + 1
    return 1


class _Scanner:
    """Reads the event stream, refuses what the format never needs and builds a tree of plain nodes."""

    def __init__(self, problems: _Problems) -> None:
        self.problems = problems
        self.stack: list[_Frame] = []
        self.root: _Node | None = None
        self.documents = 0
        self.nodes = 0

    def scan(self, text: str) -> _Node | None:
        try:
            for event in yaml.parse(text, Loader=yaml.SafeLoader):
                self.nodes += 1
                if self.nodes > MAX_NODES:
                    self.problems.add("too_many_nodes", _event_line(event), "file")
                    return None
                if not self._handle(event) or self.problems.full:
                    break
        except yaml.YAMLError as error:
            self.problems.add("syntax", _line_of(error, text), "file")
        return self.root

    def _handle(self, event: yaml.Event) -> bool:
        line = _event_line(event)
        if isinstance(event, yaml.DocumentStartEvent):
            self.documents += 1
            if self.documents > 1:
                self.problems.add("multiple_documents", line, "file")
                return False
        elif isinstance(event, yaml.AliasEvent):
            self.problems.add("alias", line, self._child_path())
            self._attach(_Scalar("", plain=False, line=line))
        elif isinstance(event, yaml.ScalarEvent):
            self._check_node(event, line)
            self._attach(_Scalar(event.value, plain=event.style is None and event.tag is None, line=line))
        elif isinstance(event, yaml.CollectionStartEvent):
            self._check_node(event, line)
            return self._push(event, line)
        elif isinstance(event, yaml.CollectionEndEvent):
            self._attach(self.stack.pop().node)
        return True

    def _check_node(self, event: yaml.NodeEvent, line: int) -> None:
        where = self._child_path()
        if event.anchor is not None:
            self.problems.add("anchor", line, where)
        if isinstance(event, (yaml.ScalarEvent, yaml.CollectionStartEvent)) and event.tag is not None:
            self.problems.add("tag", line, where)

    def _push(self, event: yaml.CollectionStartEvent, line: int) -> bool:
        where = self._child_path()
        if len(self.stack) + 1 > MAX_DEPTH:
            self.problems.add("too_deep", line, where or "root")
            return False
        node = _Map(line) if isinstance(event, yaml.MappingStartEvent) else _Seq(line)
        self.stack.append(_Frame(node, where))
        return True

    def _child_path(self) -> str:
        """The field path of the node that the next event starts."""
        if not self.stack:
            return ""
        frame = self.stack[-1]
        if isinstance(frame.node, _Seq):
            return f"{frame.path}[{len(frame.node.items)}]"
        if frame.pending_key is None:
            return frame.path
        segment = _segment(frame.pending_key.value)
        return f"{frame.path}.{segment}" if frame.path else segment

    def _attach(self, node: _Node) -> None:
        if not self.stack:
            self.root = node
            return
        frame = self.stack[-1]
        if isinstance(frame.node, _Seq):
            frame.node.items.append(node)
        elif frame.pending_key is None:
            frame.pending_key = self._key(frame, node)
        else:
            frame.node.pairs.append((frame.pending_key, node))
            frame.pending_key = None

    def _key(self, frame: _Frame, node: _Node) -> _Scalar:
        where = frame.path or "root"
        if not isinstance(node, _Scalar):
            self.problems.add("key_not_text", node.line, where)
            return _Scalar(_UNKNOWN_SEGMENT, plain=False, line=node.line)
        if node.plain and node.value == _MERGE_KEY:
            self.problems.add("merge_key", node.line, where)
        elif node.value in frame.seen:
            self.problems.add("duplicate_key", node.line, where)
        frame.seen.add(node.value)
        return node


@dataclass(slots=True)
class _Draft:
    """A category while it is read: its values, their lines and what is already reported as broken."""

    line: int
    name: str = ""
    description: str = ""
    kind: Kind = Kind.TOPIC
    notify: bool = False
    senders: list[SenderEntry] = field(default_factory=list[SenderEntry])
    name_line: int = 0
    description_line: int = 0
    senders_line: int = 0
    sender_lines: list[int] = field(default_factory=list[int])
    bad_name: bool = False
    bad_description: bool = False
    bad_senders: set[int] = field(default_factory=set[int])


class _Reader:
    """Reads the tree with the fixed field names of schema 1 and applies the policy."""

    def __init__(self, problems: _Problems) -> None:
        self.problems = problems
        self.categories_line = 0

    def read(self, root: _Node) -> ParsedList | None:
        if not isinstance(root, _Map):
            self.problems.add("not_mapping", root.line, "root")
            return None
        fields = self._fields(root, _ROOT_KEYS, "")
        self._schema(fields.get("schema"), root.line)
        instructions = self._optional_text(fields.get("generalInstructions"), "generalInstructions", "")
        archive = self._optional_text(fields.get("archiveLabel"), "archiveLabel", ARCHIVE_LABEL_DEFAULT)
        drafts = self._categories(fields.get("categories"), root.line)
        self._policy(drafts, instructions, archive)
        if self.problems.items:
            return None
        return ParsedList(instructions[0], archive[0], tuple(self._category(draft) for draft in drafts))

    def _fields(self, node: _Map, allowed: frozenset[str], path: str) -> dict[str, _Node]:
        found: dict[str, _Node] = {}
        for key, value in node.pairs:
            if key.value in allowed:
                found[key.value] = value
            else:
                self.problems.add("unknown_field", key.line, path or "root")
        return found

    def _schema(self, node: _Node | None, line: int) -> None:
        if node is None:
            self.problems.add("missing_field", line, "schema")
        elif not (isinstance(node, _Scalar) and node.plain and node.value == SCHEMA_VERSION):
            self.problems.add("schema_unsupported", node.line, "schema")

    def _text(self, node: _Node, where: str) -> str | None:
        if isinstance(node, _Scalar):
            return node.value
        self.problems.add("not_text", node.line, where)
        return None

    def _optional_text(self, node: _Node | None, where: str, default: str) -> tuple[str, int]:
        if node is None:
            return default, 0
        text = self._text(node, where)
        return (default if text is None else text), node.line

    def _flag(self, node: _Node | None, where: str) -> bool:
        if node is None:
            return False
        if isinstance(node, _Scalar) and node.plain and node.value in _BOOLEANS:
            return _BOOLEANS[node.value]
        self.problems.add("not_boolean", node.line, where)
        return False

    def _categories(self, node: _Node | None, line: int) -> list[_Draft]:
        if node is None:
            self.problems.add("missing_field", line, "categories")
            return []
        if not isinstance(node, _Seq):
            self.problems.add("not_list", node.line, "categories")
            return []
        self.categories_line = node.line
        return [self._draft(item, index) for index, item in enumerate(node.items)]

    def _draft(self, node: _Node, index: int) -> _Draft:
        path = f"categories[{index}]"
        if not isinstance(node, _Map):
            self.problems.add("not_map", node.line, path)
            return _Draft(node.line, bad_name=True, bad_description=True)
        fields = self._fields(node, _CATEGORY_KEYS, path)
        draft = _Draft(node.line, name_line=node.line, description_line=node.line, senders_line=node.line)
        self._name(draft, fields.get("name"), path)
        self._description(draft, fields.get("description"), path)
        draft.kind = self._kind(fields.get("kind"), f"{path}.kind")
        draft.notify = self._flag(fields.get("notify"), f"{path}.notify")
        self._senders(draft, fields.get("senders"), f"{path}.senders")
        return draft

    def _name(self, draft: _Draft, node: _Node | None, path: str) -> None:
        text = None if node is None else self._text(node, f"{path}.name")
        if node is None:
            self.problems.add("missing_field", draft.line, f"{path}.name")
        if text is None:
            draft.bad_name = True
        else:
            draft.name = text
            draft.name_line = node.line if node else draft.line

    def _description(self, draft: _Draft, node: _Node | None, path: str) -> None:
        text = None if node is None else self._text(node, f"{path}.description")
        if node is None:
            self.problems.add("missing_field", draft.line, f"{path}.description")
        if text is None:
            draft.bad_description = True
        else:
            draft.description = text
            draft.description_line = node.line if node else draft.line

    def _kind(self, node: _Node | None, where: str) -> Kind:
        if node is None:
            return Kind.TOPIC
        if isinstance(node, _Scalar) and node.value in {kind.value for kind in Kind}:
            return Kind(node.value)
        self.problems.add("kind_invalid", node.line, where)
        return Kind.TOPIC

    def _senders(self, draft: _Draft, node: _Node | None, path: str) -> None:
        if node is None:
            return
        draft.senders_line = node.line
        if not isinstance(node, _Seq):
            self.problems.add("not_list", node.line, path)
            return
        for position, item in enumerate(node.items):
            entry = self._entry(item, f"{path}[{position}]")
            if entry is None:
                draft.bad_senders.add(position)
                entry = SenderEntry("", False)
            draft.senders.append(entry)
            draft.sender_lines.append(item.line)

    def _entry(self, node: _Node, path: str) -> SenderEntry | None:
        if isinstance(node, _Scalar):
            return SenderEntry(node.value, False)
        if not isinstance(node, _Map):
            self.problems.add("not_text", node.line, path)
            return None
        fields = self._fields(node, _ENTRY_KEYS, path)
        subdomains = self._flag(fields.get("subdomains"), f"{path}.subdomains")
        target = fields.get("entry")
        if target is None:
            self.problems.add("missing_field", node.line, path)
            return None
        text = self._text(target, f"{path}.entry")
        return None if text is None else SenderEntry(text, subdomains)

    def _policy(
        self,
        drafts: list[_Draft],
        instructions: tuple[str, int],
        archive: tuple[str, int],
    ) -> None:
        categories = [Category(d.name, d.description, d.kind) for d in drafts]
        self._list_problems(drafts, categories)
        self._sender_problems(drafts)
        for _ in validate_instructions(instructions[0]):
            self.problems.add("instructions_too_long", instructions[1], "generalInstructions")
        for problem in validate_archive_label(archive[0], categories):
            self.problems.add(problem.rule, archive[1], _POLICY_FIELDS[problem.field])

    def _list_problems(self, drafts: list[_Draft], categories: list[Category]) -> None:
        for problem in validate_list(categories, (), ()):
            if problem.index is None:
                self.problems.add(problem.rule, self.categories_line, _POLICY_FIELDS[problem.field])
                continue
            draft = drafts[problem.index]
            where = f"categories[{problem.index}].{problem.field}"
            if problem.field == "name" and not draft.bad_name:
                self.problems.add(problem.rule, draft.name_line, where)
            elif problem.field == "description" and not draft.bad_description:
                self.problems.add(problem.rule, draft.description_line, where)

    def _sender_problems(self, drafts: list[_Draft]) -> None:
        senders = [SenderCategory(d.name, d.kind, tuple(d.senders)) for d in drafts]
        for problem in validate_entries(senders):
            draft = drafts[problem.index]
            base = f"categories[{problem.index}].senders"
            if problem.position is None:
                self.problems.add(problem.rule, draft.senders_line, base)
            elif problem.position not in draft.bad_senders:
                self.problems.add(problem.rule, draft.sender_lines[problem.position], f"{base}[{problem.position}]")

    @staticmethod
    def _category(draft: _Draft) -> FileCategory:
        return FileCategory(draft.name, draft.description, draft.kind, tuple(draft.senders), draft.notify)


def _hygiene(text: str, problems: _Problems) -> None:
    """Refuse a BOM, a NUL character and a tab, each with its line."""
    if text.startswith(_BOM):
        problems.add("bom", 1, "file")
    for number, line in enumerate(text.split("\n"), start=1):
        if "\x00" in line:
            problems.add("nul_byte", number, "file")
        if "\t" in line:
            problems.add("tab", number, "file")


def parse_category_file(data: bytes) -> ParsedList | FileProblems:
    """Parse a category file; build the list only when the whole file is valid.

    Args:
        data: The raw file content.

    Returns:
        The parsed list, or every problem found with its line and field. Nothing is raised for any input.
    """
    if len(data) > MAX_FILE_BYTES:
        return FileProblems((FileProblem("file_too_large", 1, "file"),))
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return FileProblems((FileProblem("not_utf8", 1, "file"),))
    problems = _Problems()
    _hygiene(text, problems)
    if problems.items:
        return problems.result()
    root = _Scanner(problems).scan(text)
    if problems.items:
        return problems.result()
    if root is None:
        return FileProblems((FileProblem("empty_file", 1, "file"),))
    parsed = _Reader(problems).read(root)
    return parsed if parsed is not None else problems.result()


def _entry_data(entry: SenderEntry) -> str | dict[str, str | bool]:
    return {"entry": entry.text, "subdomains": True} if entry.subdomains else entry.text


def dump_category_file(parsed: ParsedList) -> bytes:
    """Write a list as a schema 1 file; parsing the result gives the same list.

    Args:
        parsed: The list to export.

    Returns:
        The UTF-8 content of ``mail-categories.yaml``.
    """
    document = {
        "schema": int(SCHEMA_VERSION),
        "generalInstructions": parsed.general_instructions,
        "archiveLabel": parsed.archive_label,
        "categories": [
            {
                "name": category.name,
                "kind": category.kind.value,
                "description": category.description,
                "senders": [_entry_data(entry) for entry in category.senders],
                "notify": category.notify,
            }
            for category in parsed.categories
        ],
    }
    body = yaml.safe_dump(document, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100)
    return f"{_EXPORT_HEADER}{body}".encode()


__all__ = [
    "FILE_RULE_TEXT",
    "MAX_DEPTH",
    "MAX_FILE_BYTES",
    "MAX_NODES",
    "FileCategory",
    "FileProblem",
    "FileProblems",
    "ParsedList",
    "dump_category_file",
    "parse_category_file",
]
