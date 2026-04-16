#!/usr/bin/env python3
"""Fail Phase-4 CI on inline numeric literals in AE3 handlers.

Rule:
- numeric literal with absolute value > 1 inside
  `backend/services/automation-engine/ae3lite/application/handlers/**/*.py`
  is rejected
- exceptions:
  - module/class-level named constants (`ALL_CAPS`)
  - comparison bounds (`x <= 14.0`)
  - unit-conversion helpers (`* 60`, `/ 100.0`, `% (24 * 60)`)
  - `round(..., 4)` precision argument
  - current line, enclosing expression line, or previous non-empty line contains
    `config-literal:`
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
HANDLERS_ROOT = REPO_ROOT / "backend/services/automation-engine/ae3lite/application/handlers"
WHITELIST_MARKER = "config-literal:"
ALLOWED_UNIT_LITERALS = {4, 24, 60, 100, 100.0, 1000, 1000.0}


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    col: int
    value: float
    source: str


class HandlerLiteralVisitor(ast.NodeVisitor):
    def __init__(self, *, path: Path, lines: list[str]) -> None:
        self._path = path
        self._lines = lines
        self._parents: list[ast.AST] = []
        self.violations: list[Violation] = []

    def visit(self, node: ast.AST) -> None:
        self._parents.append(node)
        super().visit(node)
        self._parents.pop()

    def visit_Constant(self, node: ast.Constant) -> None:
        value = node.value
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return
        if abs(float(value)) <= 1.0:
            return
        if self._is_whitelisted(node):
            return
        source = self._lines[node.lineno - 1].rstrip()
        self.violations.append(
            Violation(
                path=self._path,
                line=node.lineno,
                col=node.col_offset + 1,
                value=float(value),
                source=source,
            )
        )

    def _is_whitelisted(self, node: ast.Constant) -> bool:
        if self._line_has_marker(node.lineno):
            return True
        if self._ancestor_has_marker(node):
            return True
        if self._inside_named_constant_assignment():
            return True

        parent = self._parent()
        if isinstance(parent, ast.Compare):
            return True
        if self._is_round_precision(node=node, parent=parent):
            return True
        if self._is_unit_conversion_literal(node=node, parent=parent):
            return True
        return False

    def _ancestor_has_marker(self, node: ast.Constant) -> bool:
        for ancestor in reversed(self._parents[:-1]):
            lineno = getattr(ancestor, "lineno", None)
            if isinstance(lineno, int) and lineno < node.lineno and self._line_has_marker(lineno):
                return True
        return False

    def _line_has_marker(self, lineno: int) -> bool:
        line = self._lines[lineno - 1]
        if WHITELIST_MARKER in line:
            return True
        cursor = lineno - 2
        while cursor >= 0:
            previous = self._lines[cursor].strip()
            if not previous:
                cursor -= 1
                continue
            return WHITELIST_MARKER in previous
        return False

    def _inside_named_constant_assignment(self) -> bool:
        for ancestor in reversed(self._parents[:-1]):
            if not isinstance(ancestor, (ast.Assign, ast.AnnAssign)):
                continue
            targets = ancestor.targets if isinstance(ancestor, ast.Assign) else [ancestor.target]
            if all(isinstance(target, ast.Name) and target.id.upper() == target.id for target in targets):
                return True
            return False
        return False

    def _is_round_precision(self, *, node: ast.Constant, parent: ast.AST | None) -> bool:
        return (
            isinstance(parent, ast.Call)
            and getattr(parent.func, "id", None) == "round"
            and len(parent.args) >= 2
            and parent.args[1] is node
        )

    def _is_unit_conversion_literal(self, *, node: ast.Constant, parent: ast.AST | None) -> bool:
        return (
            isinstance(parent, ast.BinOp)
            and float(node.value) in ALLOWED_UNIT_LITERALS
            and isinstance(parent.op, (ast.Mult, ast.Div, ast.Mod))
        )

    def _parent(self) -> ast.AST | None:
        if len(self._parents) < 2:
            return None
        return self._parents[-2]


def iter_handler_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def lint_file(path: Path) -> list[Violation]:
    source = path.read_text(encoding="utf-8")
    visitor = HandlerLiteralVisitor(path=path, lines=source.splitlines())
    visitor.visit(ast.parse(source, filename=str(path)))
    return visitor.violations


def main() -> int:
    files = iter_handler_files(HANDLERS_ROOT)
    violations: list[Violation] = []
    for path in files:
        violations.extend(lint_file(path))

    if not violations:
        print("AE3 config lint passed: no forbidden inline numeric literals found.")
        return 0

    print("AE3 config lint failed. Use a named constant or annotate with '# config-literal: <reason>'.")
    for item in violations:
        rel_path = item.path.relative_to(REPO_ROOT)
        print(f"{rel_path}:{item.line}:{item.col}: numeric literal {item.value:g} is not allowed")
        print(f"  {item.source}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
