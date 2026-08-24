#!/usr/bin/env python3
import argparse
import json
import sys
import urllib.parse
import urllib.request


DEFAULT_BASE_URL = "https://upypi.net"
DEFAULT_PACKAGES = ("xfyun_asr", "xfyun_tts")
VERIFY_IMPORTS = {
    "xfyun_asr": {"module": "xfyun_asr", "symbols": []},
    "xfyun_tts": {"module": "xfyun_tts", "symbols": []},
    "async_websocket_client": {"module": "async_websocketclient", "symbols": ["AsyncWebsocketClient"]},
}


class ResolverError(Exception):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def fetch_json(url, timeout):
    request = urllib.request.Request(url, headers={"User-Agent": "mpos-robot-app/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def normalize_package_url(url):
    value = str(url).strip().rstrip("/")
    if value.endswith("/package.json"):
        value = value[: -len("/package.json")]
    return value


class Resolver:
    def __init__(self, base_url, timeout):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.packages = {}
        self.order = []

    def search(self, name):
        url = self.base_url + "/api/search?q=" + urllib.parse.quote(name)
        data = fetch_json(url, self.timeout)
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            raise ResolverError("UPYPI_RESPONSE_INVALID", "uPyPI search response has no results array", {"url": url})
        exact = [item for item in results if isinstance(item, dict) and item.get("name") == name and item.get("url")]
        if not exact:
            raise ResolverError("DEPENDENCY_UNAVAILABLE", "uPyPI package was not found", {"package": name, "url": url})
        return normalize_package_url(exact[0]["url"])

    def resolve_name(self, name):
        return self.resolve_url(self.search(name), expected_name=name)

    def resolve_url(self, package_url, expected_name=None):
        package_url = normalize_package_url(package_url)
        if package_url in self.packages:
            return self.packages[package_url]
        metadata_url = package_url + "/package.json"
        metadata = fetch_json(metadata_url, self.timeout)
        if not isinstance(metadata, dict):
            raise ResolverError("UPYPI_PACKAGE_INVALID", "package.json must contain an object", {"url": metadata_url})
        name = metadata.get("name")
        version = metadata.get("version")
        if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
            raise ResolverError("UPYPI_PACKAGE_INVALID", "package.json requires name and version", {"url": metadata_url})
        if expected_name and name != expected_name:
            raise ResolverError(
                "UPYPI_PACKAGE_MISMATCH",
                "Search result package name does not match package.json",
                {"expected": expected_name, "actual": name, "url": metadata_url},
            )
        urls = metadata.get("urls")
        if not isinstance(urls, list) or not urls:
            raise ResolverError("UPYPI_PACKAGE_INVALID", "package.json requires a non-empty urls array", {"url": metadata_url})
        install_files = []
        for item in urls:
            if not isinstance(item, list) or len(item) < 2:
                raise ResolverError("UPYPI_PACKAGE_INVALID", "Invalid urls entry", {"package": name, "entry": item})
            install_files.append({"destination": str(item[0]), "source": str(item[1])})
        record = {
            "name": name,
            "version": version,
            "package_url": package_url,
            "package_json_url": metadata_url,
            "chips": metadata.get("chips"),
            "fw": metadata.get("fw"),
            "deps": [],
            "install_files": install_files,
            "verify": VERIFY_IMPORTS.get(name, {"module": name.replace("-", "_"), "symbols": []}),
        }
        self.packages[package_url] = record
        deps = metadata.get("deps") or []
        if not isinstance(deps, list):
            raise ResolverError("UPYPI_PACKAGE_INVALID", "deps must be an array", {"package": name})
        for item in deps:
            if not isinstance(item, list) or not item:
                raise ResolverError("UPYPI_PACKAGE_INVALID", "Invalid dependency entry", {"package": name, "entry": item})
            spec = str(item[0]).strip()
            declared_version = str(item[1]).strip() if len(item) > 1 else "latest"
            if spec.startswith("http://") or spec.startswith("https://"):
                dependency = self.resolve_url(spec)
            else:
                dependency = self.resolve_name(spec)
            record["deps"].append(
                {
                    "name": dependency["name"],
                    "version": dependency["version"],
                    "declared_version": declared_version,
                    "package_url": dependency["package_url"],
                }
            )
        self.order.append(package_url)
        return record

    def result(self, requested, target):
        packages = [self.packages[url] for url in self.order]
        requested_names = set(requested)
        install_plan = []
        for package in packages:
            if package["name"] not in requested_names:
                continue
            install_plan.append(
                {
                    "package": package["name"],
                    "version": package["version"],
                    "package_url": package["package_url"],
                    "target": target,
                    "command": ["mpremote", "mip", "install", "--target=" + target, package["package_url"]],
                    "verify": package["verify"],
                }
            )
        verification_plan = [
            {"module": "fastb64", "symbols": ["b64encode_str", "b64decode"]}
        ]
        verification_plan.extend(package["verify"] for package in packages)
        return {
            "ok": True,
            "source": "upypi-live-metadata",
            "requested": requested,
            "packages": packages,
            "install_plan": install_plan,
            "verification_plan": verification_plan,
            "driver_source_downloaded": False,
            "driver_source_snapshotted": False,
        }


def main():
    parser = argparse.ArgumentParser(description="Resolve uPyPI metadata without downloading driver source")
    parser.add_argument("--package", action="append", dest="packages", help="Package to resolve; repeat as needed")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--target", default="/apps/<app-fullname>/lib")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()
    requested = args.packages or list(DEFAULT_PACKAGES)
    resolver = Resolver(args.base_url, args.timeout)
    try:
        for package in requested:
            resolver.resolve_name(package)
        result = resolver.result(requested, args.target)
        exit_code = 0
    except ResolverError as exc:
        result = {
            "ok": False,
            "source": "upypi-live-metadata",
            "requested": requested,
            "packages": [resolver.packages[url] for url in resolver.order],
            "driver_source_downloaded": False,
            "driver_source_snapshotted": False,
            "error": {"code": exc.code, "message": str(exc), "retryable": exc.code == "DEPENDENCY_UNAVAILABLE", "details": exc.details},
        }
        exit_code = 1
    except Exception as exc:
        result = {
            "ok": False,
            "source": "upypi-live-metadata",
            "requested": requested,
            "packages": [resolver.packages[url] for url in resolver.order],
            "driver_source_downloaded": False,
            "driver_source_snapshotted": False,
            "error": {"code": "UPYPI_REQUEST_FAILED", "message": str(exc), "retryable": True, "details": {}},
        }
        exit_code = 1
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
