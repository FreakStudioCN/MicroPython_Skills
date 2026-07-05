#!/usr/bin/env python3
"""Extract plain text from a PDF datasheet.

This script intentionally does not interpret protocols or registers. It only
produces page text for the LLM workflow.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def extract_text(pdf_path: str) -> dict[str, Any]:
    result: dict[str, Any] = {"source": pdf_path, "pages": [], "error": None}
    try:
        import fitz  # type: ignore
    except ImportError:
        result["error"] = "pymupdf not installed. Run: pip install pymupdf"
        return result
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:  # pragma: no cover - depends on external PDF
        result["error"] = f"Failed to open PDF: {exc}"
        return result
    try:
        for page_num, page in enumerate(doc, start=1):
            try:
                result["pages"].append({"num": page_num, "text": page.get_text("text")})
            except Exception as exc:
                result["pages"].append({"num": page_num, "text": "", "extract_error": str(exc)})
    finally:
        doc.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract text from PDF datasheet")
    parser.add_argument("--input", required=True, help="Input PDF file path")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument("--json-summary", action="store_true", help="Print machine-readable summary to stdout")
    args = parser.parse_args()

    result = extract_text(args.input)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok = result.get("error") is None
    if args.json_summary:
        print(json.dumps({
            "status": "ok" if ok else "error",
            "pages": len(result.get("pages", [])),
            "source": args.input,
            "output": args.output,
            "message": result.get("error"),
        }, ensure_ascii=False))
    else:
        print(f"Extracted {len(result.get('pages', []))} pages -> {args.output}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
