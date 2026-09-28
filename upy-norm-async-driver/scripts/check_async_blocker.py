#!/usr/bin/env python3
"""Validate a withdrawn no_async_variant driver directory and its blocker report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REQUIRED_MARKERS = {
    "## Source": "report must identify the synchronous source package",
    "## Blocking Evidence": "report must describe the concrete unconvertible call chain",
    "## Re-evaluation Conditions": "report must state what hardware/API evidence could enable a future async variant",
    "no_async_variant": "report must declare no_async_variant status",
}


def main(argv):
    parser = argparse.ArgumentParser(description="Validate a withdrawn MicroPython async-driver variant.")
    parser.add_argument("withdrawn_dir", help="Directory left after async runtime delivery is withdrawn")
    parser.add_argument("--report", required=True, help="Markdown blocker report kept outside the withdrawn package directory")
    args = parser.parse_args(argv)
    withdrawn_dir = Path(args.withdrawn_dir)
    report = Path(args.report)
    findings = []
    if not withdrawn_dir.is_dir():
        print(f"ERROR WITHDRAWN_DIR_MISSING: {withdrawn_dir} is not a directory")
        return 2
    if not report.is_file():
        print(f"ERROR BLOCKER_REPORT_MISSING: {report} is not a file")
        return 2
    text = report.read_text(encoding="utf-8", errors="replace")
    for marker, message in REQUIRED_MARKERS.items():
        if marker not in text:
            findings.append(("BLOCKER_REPORT_CONTRACT", message))
    for forbidden in ("package.json", "README.md", "main.py"):
        if (withdrawn_dir / forbidden).exists():
            findings.append(("WITHDRAWN_RUNTIME_ARTIFACT", f"withdrawn directory must not contain {forbidden}"))
    runtime_files = [path for path in withdrawn_dir.rglob("*.py") if "__pycache__" not in path.parts]
    if runtime_files:
        findings.append(("WITHDRAWN_RUNTIME_ARTIFACT", "withdrawn directory must not contain runtime Python files: " + ", ".join(path.relative_to(withdrawn_dir).as_posix() for path in runtime_files)))
    for code, message in findings:
        print(f"ERROR {code}: {message}")
    print(f"Checked withdrawn variant; findings={len(findings)}, errors={len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
