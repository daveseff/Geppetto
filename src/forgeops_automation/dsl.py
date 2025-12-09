from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .types import ActionSpec, HostConfig, Plan, TaskSpec


class DSLParseError(ValueError):
    """Raised when the ForgeOps DSL cannot be parsed."""

    def __init__(self, message: str, line: int | None = None, column: int | None = None):
        super().__init__(message)
        self.line = line
        self.column = column


@dataclass
class Token:
    type: str
    value: str
    position: int
    line: int
    column: int


class Tokenizer:
    SIMPLE_TOKENS = {
        "{": "LBRACE",
        "}": "RBRACE",
        "[": "LBRACKET",
        "]": "RBRACKET",
        ",": "COMMA",
        ":": "COLON",
    }

    def __init__(self, text: str):
        self.text = text
        self.length = len(text)
        self.pos = 0
        self.line = 1
        self.column = 1

    def __iter__(self) -> Iterator[Token]:
        while self.pos < self.length:
            ch = self._peek_char()
            if ch.isspace():
                self._advance()
                continue
            if ch == "#":
                self._skip_comment()
                continue
            if ch in ("'", '"'):
                yield self._string()
                continue
            if ch.isdigit() or (ch == "-" and self._peek(1).isdigit()):
                yield self._number()
                continue
            if ch == "=" and self._peek(1) == ">":
                start = self.pos
                start_line, start_col = self.line, self.column
                self._advance(2)
                yield Token("ARROW", "=>", start, start_line, start_col)
                continue
            token_type = self.SIMPLE_TOKENS.get(ch)
            if token_type:
                start = self.pos
                start_line, start_col = self.line, self.column
                self._advance()
                yield Token(token_type, ch, start, start_line, start_col)
                continue
            if self._is_ident_start(ch):
                yield self._identifier()
                continue
            raise DSLParseError(
                f"Unexpected character '{ch}'",
                line=self.line,
                column=self.column,
            )
        yield Token("EOF", "", self.pos, self.line, self.column)

    def _string(self) -> Token:
        quote = self._peek_char()
        start = self.pos
        start_line, start_col = self.line, self.column
        self._advance()
        result: list[str] = []
        while self.pos < self.length:
            ch = self._peek_char()
            if ch == "\\":
                self._advance()
                if self.pos >= self.length:
                    raise DSLParseError("Unterminated string literal", line=self.line, column=self.column)
                esc = self._peek_char()
                escapes = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'"}
                result.append(escapes.get(esc, esc))
                self._advance()
                continue
            if ch == quote:
                self._advance()
                return Token("STRING", "".join(result), start, start_line, start_col)
            result.append(ch)
            self._advance()
        raise DSLParseError("Unterminated string literal", line=self.line, column=self.column)

    def _identifier(self) -> Token:
        start = self.pos
        start_line, start_col = self.line, self.column
        while self.pos < self.length and self._is_ident_part(self.text[self.pos]):
            self._advance()
        return Token("IDENT", self.text[start:self.pos], start, start_line, start_col)

    def _number(self) -> Token:
        start = self.pos
        start_line, start_col = self.line, self.column
        if self._peek_char() == "-":
            self._advance()
        while self.pos < self.length and self.text[self.pos].isdigit():
            self._advance()
        return Token("NUMBER", self.text[start:self.pos], start, start_line, start_col)

    def _skip_comment(self) -> None:
        while self.pos < self.length and self.text[self.pos] != "\n":
            self._advance()
        if self.pos < self.length:
            self._advance()  # consume newline

    @staticmethod
    def _is_ident_start(ch: str) -> bool:
        return ch.isalpha() or ch in "_./"

    @staticmethod
    def _is_ident_part(ch: str) -> bool:
        return ch.isalnum() or ch in "_-./"

    def _peek(self, offset: int) -> str:
        idx = self.pos + offset
        if idx >= self.length:
            return ""
        return self.text[idx]

    def _peek_char(self) -> str:
        return self.text[self.pos]

    def _advance(self, count: int = 1) -> None:
        for _ in range(count):
            if self.pos >= self.length:
                return
            ch = self.text[self.pos]
            self.pos += 1
            if ch == "\n":
                self.line += 1
                self.column = 1
            else:
                self.column += 1


class DSLParser:
    def parse_text(self, text: str) -> Plan:
        tokenizer = Tokenizer(text)
        self.source_text = text
        self.tokens: list[Token] = list(tokenizer)
        self.index = 0
        hosts: dict[str, HostConfig] = {}
        tasks: list[TaskSpec] = []
        while not self._match("EOF"):
            if self._check("IDENT", "node"):
                node = self._parse_node()
                hosts[node.name] = node
            elif self._check("IDENT", "task"):
                tasks.append(self._parse_task())
            else:
                token = self._peek()
                raise DSLParseError(
                    f"Unexpected token '{token.value}'",
                    line=token.line,
                    column=token.column,
                )
        if not hosts:
            hosts["local"] = HostConfig(name="local")
        return Plan(hosts=hosts, tasks=tasks)

    def parse_file(self, path: Path) -> Plan:
        return self.parse_text(path.read_text())

    def _parse_node(self) -> HostConfig:
        self._consume("IDENT", "node")
        name = self._parse_string_like()
        self._consume("LBRACE")
        attrs = self._parse_attributes()
        self._consume("RBRACE")
        connection = str(attrs.pop("connection", "local"))
        address_value = attrs.pop("address", None)
        address = str(address_value) if address_value is not None else None
        variables_value = attrs.pop("variables", {})
        if variables_value and not isinstance(variables_value, dict):
            raise DSLParseError("variables attribute must be a map")
        variables = dict(variables_value)
        for key, value in attrs.items():
            variables[key] = value
        return HostConfig(name=name, connection=connection, address=address, variables=variables)

    def _parse_task(self) -> TaskSpec:
        self._consume("IDENT", "task")
        name = self._parse_string_like()
        self._consume("IDENT", "on")
        hosts = self._parse_host_list()
        self._consume("LBRACE")
        actions: list[ActionSpec] = []
        while not self._check("RBRACE"):
            actions.append(self._parse_resource())
        self._consume("RBRACE")
        return TaskSpec(name=name, hosts=hosts, actions=actions)

    def _parse_resource(self) -> ActionSpec:
        type_token = self._consume("IDENT")
        resource_type = type_token.value
        self._consume("LBRACE")
        title = self._parse_value()
        self._consume("COLON")
        attrs = self._parse_attributes()
        self._consume("RBRACE")
        data: dict[str, object] = {}
        if isinstance(title, list):
            if resource_type != "package":
                raise DSLParseError("Only package resources accept list titles")
            data["packages"] = [str(item) for item in title]
        else:
            data["name"] = str(title)
            if resource_type == "file":
                data.setdefault("path", data["name"])
        depends_on: list[str] = []
        for key, value in attrs.items():
            if key == "ensure":
                data.setdefault("state", value)
            elif key == "depends_on":
                if isinstance(value, list):
                    depends_on.extend(str(v) for v in value)
                else:
                    depends_on.append(str(value))
            else:
                data[key] = value
        return ActionSpec(type=resource_type, data=data, depends_on=depends_on)

    def _parse_host_list(self) -> list[str]:
        if self._match("LBRACKET"):
            hosts: list[str] = []
            while not self._check("RBRACKET"):
                hosts.append(self._parse_string_like())
                self._match("COMMA")
            self._consume("RBRACKET")
            return hosts
        return [self._parse_string_like()]

    def _parse_attributes(self) -> dict[str, object]:
        attrs: dict[str, object] = {}
        while not self._check("RBRACE"):
            key_token = self._consume("IDENT")
            self._consume("ARROW")
            attrs[key_token.value] = self._parse_value()
        return attrs

    def _parse_value(self) -> object:
        token = self._peek()
        if token.type == "STRING":
            self._advance()
            return token.value
        if token.type == "NUMBER":
            self._advance()
            try:
                return int(token.value)
            except ValueError:
                raise DSLParseError(
                    f"Invalid number '{token.value}'",
                    line=token.line,
                    column=token.column,
                )
        if token.type == "IDENT":
            self._advance()
            lowered = token.value.lower()
            if lowered == "true":
                return True
            if lowered == "false":
                return False
            return token.value
        if token.type == "LBRACKET":
            return self._parse_list()
        if token.type == "LBRACE":
            return self._parse_map()
        raise DSLParseError(
            f"Unexpected value token '{token.value}'",
            line=token.line,
            column=token.column,
        )

    def _parse_list(self) -> list[object]:
        values: list[object] = []
        self._consume("LBRACKET")
        while not self._check("RBRACKET"):
            values.append(self._parse_value())
            self._match("COMMA")
        self._consume("RBRACKET")
        return values

    def _parse_map(self) -> dict[str, object]:
        mapping: dict[str, object] = {}
        self._consume("LBRACE")
        while not self._check("RBRACE"):
            key_token = self._consume("IDENT") if self._check("IDENT") else self._consume("STRING")
            self._consume("ARROW")
            mapping[key_token.value] = self._parse_value()
            self._match("COMMA")
        self._consume("RBRACE")
        return mapping

    def _parse_string_like(self) -> str:
        token = self._peek()
        if token.type not in {"STRING", "IDENT"}:
            raise DSLParseError(
                f"Expected identifier or string but found '{token.value}'",
                line=token.line,
                column=token.column,
            )
        self._advance()
        return token.value

    def _match(self, token_type: str, value: str | None = None) -> bool:
        if self._check(token_type, value):
            self._advance()
            return True
        return False

    def _check(self, token_type: str, value: str | None = None) -> bool:
        token = self._peek()
        if token.type != token_type:
            return False
        if value is not None and token.value != value:
            return False
        return True

    def _consume(self, token_type: str, value: str | None = None) -> Token:
        if not self._check(token_type, value):
            got = self._peek()
            detail = f" {value}" if value else ""
            raise DSLParseError(
                f"Expected {token_type}{detail} but found '{got.value}'",
                line=got.line,
                column=got.column,
            )
        return self._advance()

    def _advance(self) -> Token:
        token = self.tokens[self.index]
        if token.type != "EOF":
            self.index += 1
        return token

    def _peek(self) -> Token:
        return self.tokens[self.index]


def load_plan_from_dsl(path: Path) -> Plan:
    parser = DSLParser()
    return parser.parse_file(path)
