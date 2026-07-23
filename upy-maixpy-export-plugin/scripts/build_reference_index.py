#!/usr/bin/env python3
"""Maintenance helper for reviewing crawled MaixPy raw pages.

The actual curated references are edited under references/. This helper reports
what was crawled so a maintainer can update summaries without relying on live
network access during generation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-index", required=True, help="Path to crawler output index.json")
    args = parser.parse_args(argv)

    raw_index = Path(args.raw_index).resolve()
    data = json.loads(raw_index.read_text(encoding="utf-8-sig"))
    ok = [item for item in data if item.get("status") == "ok"]
    failed = [item for item in data if item.get("status") != "ok"]
    summary = {
        "raw_index": str(raw_index),
        "ok_count": len(ok),
        "failed_count": len(failed),
        "failed_urls": [item.get("url") for item in failed],
        "next_action": "Update references/*.md and examples/*.py manually from crawled official sources, then run validate_reference_index.py.",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
