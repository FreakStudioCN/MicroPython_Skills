#!/usr/bin/env python3
"""Resolve MicroPython dependency candidates from upypi index and English queries."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from common import configure_stdio, json_dump, safe_name


UPYPI_PACKAGES_URL = "https://upypi.net/packages.json"
UPYPI_SEARCH_URL = "https://upypi.net/api/search?q={query}"

CN_KEYWORD_MAP = {
    "温湿度": ["temperature", "humidity", "sensor"],
    "温度": ["temperature", "sensor"],
    "湿度": ["humidity", "sensor"],
    "气压": ["pressure", "barometer", "sensor"],
    "人体感应": ["pir", "motion", "sensor"],
    "红外": ["infrared", "ir", "sensor"],
    "蜂鸣器": ["buzzer", "alarm"],
    "报警": ["alarm", "alert"],
    "继电器": ["relay"],
    "电机": ["motor"],
    "舵机": ["servo"],
    "显示": ["display"],
    "屏幕": ["display"],
    "OLED": ["ssd1306", "oled", "display"],
    "网络": ["network"],
    "上报": ["publish"],
    "重试": ["retry", "backoff"],
    "异步": ["uasyncio", "async", "task"],
    "定时": ["timer", "scheduler"],
    "多线程": ["thread", "_thread"],
}

MIDDLEWARE_HINTS = {
    "mqtt": ["mqtt", "umqtt", "publish", "subscribe"],
    "http": ["http", "urequests", "requests"],
    "ntp": ["ntp", "time", "sync"],
    "retry": ["retry", "backoff"],
    "queue": ["queue", "async", "uasyncio"],
    "json": ["json", "ujson"],
}


def fetch_json(url: str, timeout: int = 15) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "upy-generate-plugin/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec - user-requested public API
        return json.loads(response.read().decode("utf-8-sig"))


def load_or_fetch_index(index_file: str | None, offline: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    if index_file:
        with Path(index_file).open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    elif offline:
        data = {"packages": []}
        warnings.append({"code": "UPYPI_OFFLINE", "message": "offline mode; packages index is empty"})
    else:
        try:
            data = fetch_json(UPYPI_PACKAGES_URL)
        except Exception as exc:  # pragma: no cover - depends on network
            data = {"packages": []}
            warnings.append({"code": "UPYPI_INDEX_FETCH_FAILED", "message": str(exc)})
    packages = data.get("packages", data if isinstance(data, list) else [])
    if not isinstance(packages, list):
        packages = []
    normalized = []
    for item in packages:
        if isinstance(item, str):
            normalized.append({"name": item, "version": None})
        elif isinstance(item, dict) and item.get("name"):
            normalized.append({"name": str(item["name"]), "version": item.get("version")})
    return normalized, warnings


def english_keywords(text: str) -> list[str]:
    tokens: list[str] = []
    lowered = text.lower()
    ascii_words = [
        word.strip(" _-/.,:;()[]{}")
        for word in lowered.replace("_", " ").replace("-", " ").split()
    ]
    tokens.extend(word for word in ascii_words if word and word.isascii())
    for key, words in CN_KEYWORD_MAP.items():
        if key in text:
            tokens.extend(words)
    for key, words in MIDDLEWARE_HINTS.items():
        if key in lowered:
            tokens.extend(words)
    seen = set()
    result = []
    for token in tokens:
        token = token.lower()
        if token and token not in seen:
            seen.add(token)
            result.append(token)
    return result


def candidate_score(package_name: str, query_tokens: list[str]) -> float:
    name = package_name.lower()
    if not query_tokens:
        return 0.0
    exact_hits = sum(1 for token in query_tokens if token in name)
    fuzzy = max(SequenceMatcher(None, token, name).ratio() for token in query_tokens)
    return round(min(1.0, (exact_hits / max(len(query_tokens), 1)) * 0.8 + fuzzy * 0.2), 4)


def search_api(query: str, offline: bool) -> list[dict[str, Any]]:
    if offline or not query.strip():
        return []
    try:
        url = UPYPI_SEARCH_URL.format(query=urllib.parse.quote(query))
        data = fetch_json(url)
    except Exception:  # pragma: no cover - depends on network
        return []
    results = data.get("results", data.get("packages", data if isinstance(data, list) else []))
    normalized = []
    if isinstance(results, list):
        for item in results:
            if isinstance(item, str):
                normalized.append({"name": item, "source": "upypi-search"})
            elif isinstance(item, dict) and item.get("name"):
                normalized.append({"name": str(item["name"]), "source": "upypi-search", "version": item.get("version")})
    return normalized


def queries_from_manifest(manifest: dict[str, Any]) -> list[str]:
    queries: list[str] = []
    requirements = manifest.get("requirements", {})
    if isinstance(requirements, dict):
        for key in ("description", "network", "output", "special_requirements"):
            value = requirements.get(key)
            if isinstance(value, str) and value.strip():
                queries.append(value)
            elif isinstance(value, list):
                queries.extend(str(item) for item in value if str(item).strip())
    for device in manifest.get("devices", []):
        if not isinstance(device, dict):
            continue
        for key in ("name", "type", "model"):
            if device.get(key):
                queries.append(str(device[key]))
        driver = device.get("driver", {})
        if isinstance(driver, dict):
            for key in ("package_name", "driver_url", "query"):
                if driver.get(key):
                    queries.append(str(driver[key]))
    return queries


def parse_queries(args: argparse.Namespace) -> list[str]:
    queries: list[str] = []
    if args.queries:
        try:
            parsed = json.loads(args.queries)
        except json.JSONDecodeError:
            parsed = [item.strip() for item in args.queries.split(",")]
        if isinstance(parsed, list):
            queries.extend(str(item) for item in parsed if str(item).strip())
        else:
            queries.append(str(parsed))
    if args.manifest:
        from common import load_manifest_arg

        queries.extend(queries_from_manifest(load_manifest_arg(args.manifest)))
    return queries


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Resolve upypi package candidates")
    parser.add_argument("--queries", default="", help="JSON array or comma-separated query text")
    parser.add_argument("--manifest", default="", help="Optional manifest or phase_complete path; '-' reads stdin")
    parser.add_argument("--index-file", default="", help="Optional cached packages.json")
    parser.add_argument("--offline", action="store_true", help="Do not access network")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()

    packages, warnings = load_or_fetch_index(args.index_file or None, args.offline)
    queries = parse_queries(args)
    resolved = []
    for raw_query in queries:
        tokens = english_keywords(raw_query)
        if not tokens:
            tokens = [safe_name(raw_query)]
            warnings.append(
                {
                    "code": "QUERY_NORMALIZED_WITH_FALLBACK",
                    "query": raw_query,
                    "message": "query did not contain usable English tokens; safe_name fallback used",
                }
            )
        scored = []
        for package in packages:
            score = candidate_score(package["name"], tokens)
            if score > 0.08:
                scored.append(
                    {
                        "name": package["name"],
                        "version": package.get("version"),
                        "source": "upypi-index",
                        "score": score,
                    }
                )
        scored.sort(key=lambda item: (-item["score"], item["name"].lower()))
        api_results = search_api(" ".join(tokens[:4]), args.offline)
        known = {item["name"].lower() for item in scored}
        for item in api_results:
            if item["name"].lower() not in known:
                item["score"] = 0.5
                scored.append(item)
        resolved.append(
            {
                "query": raw_query,
                "english_keywords": tokens,
                "candidates": scored[: max(args.limit, 1)],
            }
        )

    json_dump(
        {
            "upypi_package_index": {
                "fetched": bool(packages),
                "count": len(packages),
                "source": args.index_file or ("offline" if args.offline else UPYPI_PACKAGES_URL),
            },
            "queries": resolved,
            "warnings": warnings,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
