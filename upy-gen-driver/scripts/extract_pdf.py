#!/usr/bin/env python3
"""PDF 数据手册文本提取脚本。纯文本提取，不做结构化理解。

用法:
  python extract_pdf.py --input datasheet.pdf --output chip_text.json

输出 JSON:
{
  "source": "datasheet.pdf",
  "pages": [
    {"num": 1, "text": "..."},
    {"num": 2, "text": "..."}
  ],
  "error": null
}
"""

import argparse
import json
import sys
from typing import Any, Dict, List


def extract_text(pdf_path: str) -> Dict[str, Any]:
    """从 PDF 提取每页文本。"""
    result: Dict[str, Any] = {
        "source": pdf_path,
        "pages": [],
        "error": None,
    }

    try:
        import fitz  # pymupdf
    except ImportError:
        result["error"] = "pymupdf not installed. Run: pip install pymupdf"
        return result

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        result["error"] = "Failed to open PDF: %s" % e
        return result

    try:
        for page_num, page in enumerate(doc, start=1):
            try:
                text = page.get_text("text")
                result["pages"].append({
                    "num": page_num,
                    "text": text,
                })
            except Exception as e:
                result["pages"].append({
                    "num": page_num,
                    "text": "",
                    "extract_error": str(e),
                })
    finally:
        doc.close()

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract text from PDF datasheet"
    )
    parser.add_argument("--input", required=True, help="Input PDF file path")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    args = parser.parse_args()

    result = extract_text(args.input)

    try:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print("Extracted %d pages → %s" % (len(result["pages"]), args.output))
    except Exception as e:
        json.dump(
            {"source": args.input, "pages": [], "error": "Write output failed: %s" % e},
            sys.stdout, ensure_ascii=False, indent=2,
        )
        sys.exit(1)

    if result["error"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
