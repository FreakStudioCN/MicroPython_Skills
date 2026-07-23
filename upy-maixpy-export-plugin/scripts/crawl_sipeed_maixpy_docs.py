#!/usr/bin/env python3
"""Maintenance crawler for Sipeed MaixPy docs.

This script is not part of runtime code generation. Run it manually when the
Skill reference library must be refreshed from official Sipeed pages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


SEEDS = [
    "https://wiki.sipeed.com/hardware/zh/maixcam/maixcam_pro.html",
    "https://wiki.sipeed.com/maixpy/",
    "https://wiki.sipeed.com/maixpy/api/index.html",
    "https://github.com/sipeed/maixpy",
]
ALLOWED_HOSTS = {"wiki.sipeed.com", "github.com"}


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in_title = False
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data.strip()


def allowed(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.netloc not in ALLOWED_HOSTS:
        return False
    if parsed.netloc == "wiki.sipeed.com":
        return "/maixpy" in parsed.path or "/hardware/zh/maixcam" in parsed.path
    return parsed.path.startswith("/sipeed/maixpy")


def safe_name(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    parsed = urllib.parse.urlparse(url)
    stem = (parsed.netloc + parsed.path).strip("/").replace("/", "_").replace(".", "_")
    return f"{stem[:120]}__{digest}.html"


def fetch(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "MicroPython-Skills-MaixPy-Crawler/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True, help="Directory for raw crawled pages and index.json")
    parser.add_argument("--max-pages", type=int, default=80)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--seed", action="append", default=[])
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    queue = list(dict.fromkeys(args.seed or SEEDS))
    seen: set[str] = set()
    records: list[dict[str, object]] = []

    while queue and len(seen) < args.max_pages:
        url = queue.pop(0)
        url = urllib.parse.urldefrag(url)[0]
        if url in seen or not allowed(url):
            continue
        seen.add(url)
        try:
            body = fetch(url, args.timeout)
            html = body.decode("utf-8", errors="replace")
            name = safe_name(url)
            (out_dir / name).write_text(html, encoding="utf-8")
            parser_obj = LinkExtractor()
            parser_obj.feed(html)
            for href in parser_obj.links:
                next_url = urllib.parse.urljoin(url, href)
                next_url = urllib.parse.urldefrag(next_url)[0]
                if allowed(next_url) and next_url not in seen and next_url not in queue:
                    queue.append(next_url)
            records.append({"url": url, "status": "ok", "file": name, "title": parser_obj.title})
        except Exception as exc:  # pragma: no cover - maintenance diagnostics
            records.append({"url": url, "status": "failed", "error": repr(exc)})

    (out_dir / "index.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out_dir": str(out_dir), "pages": len(records)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
