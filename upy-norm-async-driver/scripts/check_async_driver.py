#!/usr/bin/env python3
"""Static checks for MicroPython async driver conversions.

This is a heuristic gate, not a proof of correctness. It catches common
mistakes from uasyncio driver ports: fake async wrappers, blocking calls inside
async methods, unsafe IRQ callbacks, and RP2 DMA/PIO hazards.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "build",
    "dist",
}

BLOCKING_ASYNC_PATTERNS = (
    ("ERROR", "time.sleep", "blocking sleep inside async function"),
    ("ERROR", "time.sleep_ms", "blocking sleep_ms inside async function"),
    ("ERROR", "sleep_ms", "imported sleep_ms inside async function"),
    ("ERROR", "sleep_us", "sleep_us inside async function; keep timing-critical primitive sync"),
    ("ERROR", "urequests", "blocking urequests inside async function"),
    ("ERROR", "requests", "blocking requests inside async function"),
    ("WARN", "socket.getaddrinfo", "DNS lookup may block on MicroPython ports"),
    ("WARN", "ssl.wrap_socket", "TLS handshake may block on MicroPython ports"),
    ("WARN", "open", "file I/O inside async function needs chunking/residual-blocking docs"),
    ("WARN", "json.load", "JSON file/body parsing inside async path may block or allocate heavily"),
    ("WARN", "json.loads", "JSON parsing inside async path may block or allocate heavily"),
)

IRQ_IO_PATTERNS = (
    "readfrom",
    "readfrom_into",
    "writeto",
    "write_readinto",
    "readinto",
    "write",
    "read",
    "connect",
    "wrap_socket",
    "open",
)


@dataclass
class Finding:
    severity: str
    path: Path
    line: int
    code: str
    message: str


def matches_blocking_call(name: str, pattern: str) -> bool:
    if pattern in {"time.sleep", "time.sleep_ms", "sleep_ms", "sleep_us", "open"}:
        return name == pattern
    if pattern in {"urequests", "requests"}:
        return name == pattern or name.startswith(pattern + ".")
    if pattern == "socket.getaddrinfo":
        return name in {"socket.getaddrinfo", "getaddrinfo"}
    if pattern == "ssl.wrap_socket":
        return name in {"ssl.wrap_socket", "wrap_socket"}
    if pattern == "json.load":
        return name in {"json.load", "load"}
    if pattern == "json.loads":
        return name in {"json.loads", "loads"}
    return name == pattern


def iter_py_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(".py"):
                yield Path(dirpath) / name


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return call_name(node.func)
    return ""


def has_await(node: ast.AST) -> bool:
    return any(isinstance(child, (ast.Await, ast.AsyncFor, ast.AsyncWith)) for child in ast.walk(node))


def decorator_name(node: ast.AST) -> str:
    return call_name(node.func if isinstance(node, ast.Call) else node)


def source_segment(source: str, node: ast.AST) -> str:
    try:
        return ast.get_source_segment(source, node) or ""
    except Exception:
        return ""


class Checker(ast.NodeVisitor):
    def __init__(self, path: Path, source: str):
        self.path = path
        self.source = source
        self.findings: list[Finding] = []
        self.stack: list[ast.AST] = []

    def add(self, severity: str, node: ast.AST, code: str, message: str) -> None:
        self.findings.append(
            Finding(severity, self.path, getattr(node, "lineno", 1), code, message)
        )

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        decos = {decorator_name(d) for d in node.decorator_list}
        if "micropython.native" in decos or "micropython.viper" in decos:
            self.add("ERROR", node, "ASYNC_OPT_DECORATOR", "async def decorated with micropython native/viper")

        calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
        call_names = [call_name(c.func) for c in calls]
        for severity, pattern, message in BLOCKING_ASYNC_PATTERNS:
            for c, name in zip(calls, call_names):
                if matches_blocking_call(name, pattern):
                    self.add(severity, c, "ASYNC_BLOCKING_CALL", message)

        for child in ast.walk(node):
            if isinstance(child, ast.While) and isinstance(child.test, ast.Constant) and child.test.value is True:
                if not has_await(child):
                    self.add("ERROR", child, "ASYNC_WHILE_TRUE_NO_AWAIT", "while True in async function has no await")

        for child in ast.walk(node):
            if isinstance(child, ast.Expr) and isinstance(child.value, ast.Call):
                name = call_name(child.value.func)
                if name.endswith("asyncio.create_task") or name == "create_task":
                    self.add("WARN", child, "UNSTORED_TASK", "create_task result is not stored for lifecycle cleanup")

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        lname = node.name.lower()
        looks_like_irq = any(k in lname for k in ("irq", "interrupt", "timer", "callback", "handler"))
        if looks_like_irq:
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    name = call_name(child.func)
                    if name == "print":
                        self.add("WARN", child, "IRQ_PRINT", "callback/IRQ-like function prints")
                    if any(part in name for part in IRQ_IO_PATTERNS):
                        self.add("WARN", child, "IRQ_IO", "callback/IRQ-like function performs I/O or allocation-heavy work")

        decos = {decorator_name(d) for d in node.decorator_list}
        if "micropython.native" in decos or "micropython.viper" in decos:
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    name = call_name(child.func)
                    if "sleep_ms" in name or "sleep_us" in name:
                        self.add("WARN", child, "OPT_TIMING_PRIMITIVE", "optimized timing primitive should stay sync")

        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self._check_pio_loop(node)
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self._check_pio_loop(node)
        self.generic_visit(node)

    def _check_pio_loop(self, node: ast.AST) -> None:
        names = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                names.append(call_name(child.func))
        if any(re.search(r"(^|\.)(put|get)$", name) for name in names):
            text = source_segment(self.source, node)
            if "StateMachine" in self.source or re.search(r"\bsm\b", text):
                if not re.search(r"timeout|ticks_ms|ticks_diff|await|sleep_ms", text):
                    self.add("WARN", node, "PIO_FIFO_LOOP", "StateMachine put/get loop lacks visible timeout/yield")


def regex_fallback(path: Path, source: str) -> list[Finding]:
    findings: list[Finding] = []
    lines = source.splitlines()
    for idx, line in enumerate(lines, 1):
        nearby = lines[max(0, idx - 3) : idx]
        if re.search(r"^\s*async\s+def\b", line) and any("@micropython." in prev for prev in nearby):
            findings.append(Finding("ERROR", path, idx, "ASYNC_OPT_DECORATOR", "async def near micropython optimizer decorator"))
        if re.search(r"\.irq\s*\(.*hard\s*=\s*True", line):
            findings.append(Finding("WARN", path, idx, "HARD_IRQ", "hard IRQ callback must only signal; inspect manually"))
    return findings


def check_file(path: Path) -> list[Finding]:
    source = path.read_text(encoding="utf-8", errors="replace")
    findings = regex_fallback(path, source)
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        findings.append(Finding("WARN", path, exc.lineno or 1, "SYNTAX_SKIP", f"could not parse with CPython AST: {exc.msg}"))
        return findings

    checker = Checker(path, source)
    checker.visit(tree)
    findings.extend(checker.findings)
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Check MicroPython async driver conversion hazards.")
    parser.add_argument("path", help="Converted driver package directory or a single .py file")
    parser.add_argument("--warn-as-error", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args(argv)

    root = Path(args.path)
    if not root.exists():
        print(f"Path not found: {root}", file=sys.stderr)
        return 2

    files = [root] if root.is_file() else list(iter_py_files(root))
    all_findings: list[Finding] = []
    for path in files:
        all_findings.extend(check_file(path))

    all_findings.sort(key=lambda f: (str(f.path), f.line, f.severity, f.code))
    for finding in all_findings:
        rel = finding.path.relative_to(root) if root.is_dir() and finding.path.is_relative_to(root) else finding.path
        print(f"{finding.severity} {rel}:{finding.line} {finding.code}: {finding.message}")

    errors = [f for f in all_findings if f.severity == "ERROR" or (args.warn_as_error and f.severity == "WARN")]
    print(f"Checked {len(files)} Python file(s); findings={len(all_findings)}, errors={len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
