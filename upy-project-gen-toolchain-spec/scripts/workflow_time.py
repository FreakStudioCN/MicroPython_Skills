#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Emit or validate workflow UTC timestamps."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(value: str) -> datetime:
    if not value:
        raise ValueError("timestamp is empty")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Workflow UTC timestamp helper")
    parser.add_argument("--json", action="store_true", help="emit JSON object")
    parser.add_argument("--validate", default=None, help="validate an ISO-8601 UTC timestamp")
    args = parser.parse_args()

    if args.validate is not None:
        try:
            parsed = parse_utc(args.validate)
        except ValueError as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps({"valid": True, "utc": parsed.strftime("%Y-%m-%dT%H:%M:%SZ")}, ensure_ascii=False))
        else:
            print("[OK] timestamp is valid")
        return 0

    now = utc_now()
    if args.json:
        print(json.dumps({"utc": now}, ensure_ascii=False))
    else:
        print(now)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
