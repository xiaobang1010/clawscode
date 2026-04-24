from __future__ import annotations

import logging
import os
import signal
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ParseResultType(str, Enum):
    SIMPLE = "simple"
    TOO_COMPLEX = "too-complex"
    PARSE_UNAVAILABLE = "parse-unavailable"


@dataclass
class ParsedCommand:
    argv: list[str] = field(default_factory=list)
    env_vars: list[tuple[str, str]] = field(default_factory=list)
    redirects: list[dict[str, str]] = field(default_factory=list)
    text: str = ""
    var_scope: dict[str, str] = field(default_factory=dict)


@dataclass
class ParseResult:
    result_type: ParseResultType
    commands: list[ParsedCommand] = field(default_factory=list)
    error: str = ""


class BashASTParser:
    TIMEOUT_SECONDS = 2.0
    MAX_NODES = 10000

    def __init__(self) -> None:
        self._parser: Any = None
        self._available = False
        self._init_parser()

    def _init_parser(self) -> None:
        if not os.environ.get("CLAWSCODE_TREE_SITTER_BASH"):
            self._available = False
            return

        try:
            import tree_sitter_bash as tsbash
            from tree_sitter import Language, Parser

            bash_lang = Language(tsbash.language())
            self._parser = Parser(bash_lang)
            self._available = True
            logger.info("tree-sitter bash parser initialized successfully")
        except ImportError:
            self._available = False
            logger.debug("tree-sitter bash parser not available, falling back to regex")
        except Exception as e:
            self._available = False
            logger.debug(f"tree-sitter init failed: {e}")

    @property
    def is_available(self) -> bool:
        return self._available and self._parser is not None

    def parse_for_security(self, command: str) -> ParseResult:
        if not self.is_available:
            return ParseResult(
                result_type=ParseResultType.PARSE_UNAVAILABLE,
                error="tree-sitter parser not available",
            )

        result_holder: list[ParseResult] = []
        error_holder: list[str] = []

        def _parse():
            try:
                tree = self._parser.parse(command.encode("utf-8"))
                if tree is None:
                    error_holder.append("parse returned None")
                    return

                root = tree.root_node
                if root.has_error:
                    error_holder.append("parse has errors")
                    return

                node_count = self._count_nodes(root)
                if node_count > self.MAX_NODES:
                    error_holder.append(f"node budget exceeded: {node_count}")
                    return

                commands = self._extract_commands(root, command)
                result_holder.append(ParseResult(
                    result_type=ParseResultType.SIMPLE,
                    commands=commands,
                ))
            except Exception as e:
                error_holder.append(str(e))

        timer = threading.Timer(self.TIMEOUT_SECONDS, lambda: None)
        try:
            timer.start()
            _parse()
        finally:
            timer.cancel()

        if error_holder:
            return ParseResult(
                result_type=ParseResultType.TOO_COMPLEX,
                error="; ".join(error_holder),
            )

        if result_holder:
            return result_holder[0]

        return ParseResult(
            result_type=ParseResultType.TOO_COMPLEX,
            error="parse timed out",
        )

    def _count_nodes(self, node: Any) -> int:
        count = 1
        for child in node.children:
            count += self._count_nodes(child)
            if count > self.MAX_NODES:
                return count
        return count

    def _extract_commands(self, root: Any, source: str) -> list[ParsedCommand]:
        commands: list[ParsedCommand] = []
        self._walk_node(root, source, commands)
        return commands

    def _walk_node(self, node: Any, source: str, commands: list[ParsedCommand]) -> None:
        if node.type == "simple_command":
            cmd = self._parse_simple_command(node, source)
            commands.append(cmd)
            return

        if node.type == "command":
            for child in node.children:
                if child.type == "simple_command":
                    cmd = self._parse_simple_command(child, source)
                    commands.append(cmd)

        for child in node.children:
            self._walk_node(child, source, commands)

    def _parse_simple_command(self, node: Any, source: str) -> ParsedCommand:
        argv: list[str] = []
        env_vars: list[tuple[str, str]] = []
        redirects: list[dict[str, str]] = []
        var_scope: dict[str, str] = {}

        for child in node.children:
            if child.type in ("word", "concatenation", "string", "raw_string"):
                text = source[child.start_byte:child.end_byte]
                argv.append(text)
            elif child.type == "variable_assignment":
                text = source[child.start_byte:child.end_byte]
                if "=" in text:
                    key, _, val = text.partition("=")
                    env_vars.append((key, val))
                    var_scope[key] = val
            elif child.type == "file_redirect":
                redirect = self._parse_redirect(child, source)
                if redirect:
                    redirects.append(redirect)
            elif child.type == "heredoc_redirect":
                redirect = self._parse_redirect(child, source)
                if redirect:
                    redirects.append(redirect)

        full_text = source[node.start_byte:node.end_byte]
        return ParsedCommand(
            argv=argv,
            env_vars=env_vars,
            redirects=redirects,
            text=full_text,
            var_scope=var_scope,
        )

    def _parse_redirect(self, node: Any, source: str) -> dict[str, str] | None:
        descriptor = ""
        target = ""
        op = ""

        for child in node.children:
            if child.type == "file_descriptor":
                descriptor = source[child.start_byte:child.end_byte]
            elif child.type in ("<", ">", ">>", "&>", "&>>", ">|"):
                op = child.type
            elif child.type in ("word", "string", "raw_string", "concatenation"):
                target = source[child.start_byte:child.end_byte]

        if op or target:
            return {"descriptor": descriptor, "operator": op, "target": target}
        return None


_parser_instance: BashASTParser | None = None


def _get_parser() -> BashASTParser:
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = BashASTParser()
    return _parser_instance


def parse_for_security(command: str) -> ParseResult:
    return _get_parser().parse_for_security(command)


def cross_validate_with_regex(command: str, regex_result: str) -> str:
    if not _get_parser().is_available:
        return regex_result

    ast_result = parse_for_security(command)

    if ast_result.result_type == ParseResultType.PARSE_UNAVAILABLE:
        return regex_result

    if ast_result.result_type == ParseResultType.TOO_COMPLEX:
        return "unknown"

    ast_dangerous = False
    for cmd in ast_result.commands:
        for redirect in cmd.redirects:
            if redirect.get("operator", "") in (">", ">>", "&>", "&>>"):
                target = redirect.get("target", "")
                if target.startswith("/dev/sd") or target.startswith("/etc/"):
                    ast_dangerous = True
                if target.startswith("$") or target.startswith("`"):
                    ast_dangerous = True

        for key, val in cmd.env_vars:
            if any(c in val for c in ("$(", "`", "\n")):
                ast_dangerous = True

    if ast_dangerous and regex_result == "safe":
        return "dangerous"

    if regex_result == "dangerous":
        return "dangerous"

    return regex_result
