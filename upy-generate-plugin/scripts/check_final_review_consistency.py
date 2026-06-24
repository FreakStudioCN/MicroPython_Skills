#!/usr/bin/env python3
"""Ensure final review findings cannot be ignored by phase_complete success."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump


BLOCKING_PATTERNS = [
    re.compile(r"\bcritical\b", re.IGNORECASE),
    re.compile(r"\bblocking\b", re.IGNORECASE),
    re.compile(r"\bsevere\b", re.IGNORECASE),
    re.compile(r"严重"),
    re.compile(r"关键\s*Bug", re.IGNORECASE),
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def phase_review_findings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    review = payload.get("review_findings")
    if not isinstance(review, dict):
        return []
    blocking = review.get("blocking")
    if not isinstance(blocking, list):
        return []
    return [item for item in blocking if isinstance(item, dict) or item]


def markdown_blocking_findings(path: Path) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    findings = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("| # ") or stripped.startswith("|---"):
            continue
        if any(pattern.search(line) for pattern in BLOCKING_PATTERNS):
            findings.append(
                {
                    "code": "FINAL_REVIEW_BLOCKING_TEXT",
                    "path": str(path),
                    "line": lineno,
                    "message": stripped,
                }
            )
    return findings


def json_blocking_findings(path: Path) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    try:
        data = load_json(path)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    review = data.get("review_findings", data)
    if not isinstance(review, dict):
        return []
    blocking = review.get("blocking", [])
    if not isinstance(blocking, list):
        return []
    return [
        item if isinstance(item, dict) else {"code": "FINAL_REVIEW_BLOCKING_ITEM", "message": str(item)}
        for item in blocking
    ]


def validate(phase_complete: dict[str, Any], log_path: Path | None, review_json: Path | None) -> dict[str, Any]:
    payload = phase_complete.get("payload") if isinstance(phase_complete.get("payload"), dict) else {}
    result = payload.get("result")
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    blocking = phase_review_findings(payload)
    if review_json:
        blocking.extend(json_blocking_findings(review_json))
    if log_path:
        blocking.extend(markdown_blocking_findings(log_path))
    if result == "success" and blocking:
        errors.append(
            {
                "code": "SUCCESS_WITH_BLOCKING_REVIEW_FINDINGS",
                "message": "phase_complete.result=success is invalid when final review has blocking findings",
                "findings": blocking,
            }
        )
    if result == "success" and "review_findings" not in payload:
        warnings.append(
            {
                "code": "REVIEW_FINDINGS_MISSING",
                "message": "success phase_complete should include review_findings with blocking=[]",
            }
        )
    return {
        "check": "final_review_consistency",
        "result": result,
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Check final review consistency")
    parser.add_argument("--phase-complete", required=True)
    parser.add_argument("--log", default="", help="Optional generate_phase_log.md path")
    parser.add_argument("--review-json", default="", help="Optional structured final review JSON")
    args = parser.parse_args()
    result = validate(
        load_json(Path(args.phase_complete)),
        Path(args.log) if args.log else None,
        Path(args.review_json) if args.review_json else None,
    )
    json_dump(result)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
