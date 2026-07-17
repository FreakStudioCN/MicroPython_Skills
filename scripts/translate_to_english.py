#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recursive LLM translation script — translates Chinese → English for markdown
and JSON files, then mirrors the source tree into an output directory.

Supports two backends:
  - Anthropic Claude API (via anthropic SDK)
  - OpenAI-compatible APIs: DeepSeek, Qwen, GLM, Moonshot, etc. (via HTTP)

Usage
-----
    # DeepSeek (recommended for China users)
    python translate_to_english.py --src G:/MicroPython_Skills --dst G:/MicroPython_Skills_EN --backend deepseek --api-key sk-xxx

    # Anthropic Claude
    set ANTHROPIC_API_KEY=sk-ant-...
    python translate_to_english.py --src G:/MicroPython_Skills --dst G:/MicroPython_Skills_EN --backend anthropic

    # Custom OpenAI-compatible endpoint
    python translate_to_english.py --src G:/MicroPython_Skills --dst G:/MicroPython_Skills_EN --backend custom --base-url https://api.example.com/v1 --model my-model --api-key sk-xxx

    # dry-run: list what would be translated
    python translate_to_english.py --src G:/MicroPython_Skills --dst G:/MicroPython_Skills_EN --dry-run

    # resume after interruption
    python translate_to_english.py --src G:/MicroPython_Skills --dst G:/MicroPython_Skills_EN --resume

    # single file (test)
    python translate_to_english.py --src G:/MicroPython_Skills --dst G:/MicroPython_Skills_EN --file upy-analyze/SKILL.md
"""

import os
import sys
import json
import time
import hashlib
import argparse
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKIP_DIRS  = {".git", "__pycache__", ".idea", ".codex-plugin", "node_modules"}
SKIP_FILES = {".gitignore", ".DS_Store", ".api_key"}
SKIP_EXTENSIONS = {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".bin", ".hex", ".uf2"}

TRANSLATE_EXTENSIONS = {".md", ".json"}

# JSON files that are machine-generated indexes (skip translating)
JSON_SKIPLIST = {
    "_awesome_cache.json",
    "micropython_official_library_index.json",
}

# Minimum fraction of lines containing Chinese to trigger translation
MIN_CHINESE_RATIO = 0.03

# API / rate-limiting
BACKEND_DEFAULT     = "deepseek"
MODEL_DEFAULT       = "deepseek-chat"
REQUESTS_PER_MINUTE = 40
MAX_RETRIES         = 3
INITIAL_BACKOFF_S   = 10

# Pre-configured OpenAI-compatible backends
BACKEND_CONFIG = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model":    "deepseek-chat",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model":    "qwen-plus",
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model":    "glm-4-flash",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "model":    "moonshot-v1-8k",
    },
}

VALID_BACKENDS = ("anthropic", "deepseek", "qwen", "glm", "moonshot", "custom")


def claude_settings_env() -> dict:
    path = Path(os.environ.get("CLAUDE_SETTINGS_PATH", "~/.claude/settings.json")).expanduser()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    env = data.get("env") if isinstance(data, dict) else None
    if not isinstance(env, dict):
        return {}
    return {str(key): str(value) for key, value in env.items() if value is not None}


def env_value(*names: str) -> Optional[str]:
    settings_env = claude_settings_env()
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
        value = settings_env.get(name, "").strip()
        if value:
            return value
    return None


def default_backend() -> str:
    configured = env_value("SKILLS_TRANSLATE_BACKEND")
    if configured:
        return configured
    if env_value("SKILLS_TRANSLATE_BASE_URL"):
        return "custom"
    if env_value("DEEPSEEK_API_KEY"):
        return "deepseek"
    if env_value("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        return "anthropic"
    return BACKEND_DEFAULT


def resolve_api_key(backend: str) -> Optional[str]:
    generic = env_value("SKILLS_TRANSLATE_API_KEY")
    if generic:
        return generic
    if backend == "anthropic":
        return env_value("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
    if backend == "deepseek":
        return env_value("DEEPSEEK_API_KEY")
    return env_value("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")

# Token budget
MAX_TOKENS_SMALL = 8192
MAX_TOKENS_LARGE = 16384
LARGE_FILE_LINES = 500

PROGRESS_FILENAME = ".translation_progress.json"

# ---------------------------------------------------------------------------
# Chinese detection
# ---------------------------------------------------------------------------

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")


def has_chinese(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def chinese_line_ratio(content: str) -> float:
    lines = [l for l in content.split("\n") if l.strip()]  # ignore blank lines
    if not lines:
        return 0.0
    return sum(1 for l in lines if has_chinese(l)) / len(lines)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# System prompts (cached ephemerally by the Anthropic API)
# ---------------------------------------------------------------------------

PROMPT_MARKDOWN = """\
You are a technical translator specialising in MicroPython embedded-systems
documentation.  Translate the following Markdown file from Chinese to English.

RULES (follow exactly — no exceptions):

1. YAML FRONTMATTER: translate ONLY the "description" field value.  Keep every
   key, every other value, and the --- delimiters unchanged.

2. CODE BLOCKS (``` … ```): do NOT translate anything inside fenced code
   blocks.  Preserve every character — including comments — exactly as-is.

3. INLINE CODE (`…`): keep inline code spans unchanged.

4. LINKS [text](url): translate the link TEXT; keep the URL exactly as-is.

5. TABLES: translate cell contents.  Keep the header row, alignment colons,
   and pipe characters.

6. JSON / PROTOCOL examples inside the markdown: never translate JSON keys.
   Only translate Chinese string *values*.  Keep the JSON structure intact.

7. UNTRANSLATED technical terms (keep as-is):
   - Buses: I2C, SPI, UART, GPIO, PWM, ADC, DAC, I2S, CAN
   - μPy: deinit, __slots__, micropython.const, urequests, asyncio, _thread
   - HW:  Timer, Pin, RTC, WDT
   - Python: __init__, __version__, __author__, __license__, @property
   - File paths, CLI commands, function / variable names

8. Translate prose (instructions, explanations, comments outside code blocks)
   into natural English.  Preserve tone — if the original is imperative keep
   it imperative.

9. Preserve: blank lines, heading levels (# ## ###), list markers (- * 1.),
   blockquotes (>), horizontal rules (---), emphasis (**bold** *italic*).

10. OUTPUT ONLY THE TRANSLATED FILE.  No preamble, no "here is the
    translation", no wrapping ``` fences."""

PROMPT_JSON = """\
You are a technical translator.  Translate the following JSON file from
Chinese to English.

RULES:
1. NEVER translate JSON keys — keep every key exactly as-is.
2. Only translate string VALUES that contain Chinese characters.
3. Keep numbers, booleans, null unchanged.
4. Preserve all nesting, arrays, and JSON structure exactly.
5. OUTPUT ONLY THE TRANSLATED JSON — no surrounding text, no ``` fences."""

PROMPT_PLUGIN_JSON = """\
You are a technical translator.  Translate the following Codex plugin.json
file from Chinese to English.

RULES:
1. NEVER translate JSON keys.
2. Translate ONLY these fields when they contain Chinese:
   "description", "shortDescription", "longDescription", "displayName"
3. Keep every other value unchanged.
4. Preserve JSON structure exactly.
5. OUTPUT ONLY THE TRANSLATED JSON — no surrounding text, no ``` fences."""


def pick_prompt(file_type: str) -> str:
    if file_type == "plugin.json":
        return PROMPT_PLUGIN_JSON
    if file_type == "json":
        return PROMPT_JSON
    return PROMPT_MARKDOWN


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    def __init__(self, rpm: int):
        self._interval = 60.0 / rpm
        self._last = 0.0

    def wait(self):
        now = time.time()
        gap = now - self._last
        if gap < self._interval:
            time.sleep(self._interval - gap)
        self._last = time.time()


# ---------------------------------------------------------------------------
# Translator (Anthropic API)
# ---------------------------------------------------------------------------

class Translator:
    """Multi-backend translator.

    backends:
      - "anthropic": uses the anthropic SDK
      - "deepseek" / "qwen" / "glm" / "moonshot": OpenAI-compatible HTTP
      - "custom": requires --base-url (OpenAI-compatible)
    """

    def __init__(
        self,
        api_key: str,
        backend: str = BACKEND_DEFAULT,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        rpm: int = REQUESTS_PER_MINUTE,
    ):
        self._api_key  = api_key
        self._backend  = backend
        self._base_url = base_url or ""
        self._limiter  = RateLimiter(rpm)

        # Resolve model
        if model:
            self._model = model
        elif backend == "anthropic":
            self._model = "claude-sonnet-4-6"
        elif backend in BACKEND_CONFIG:
            self._model = BACKEND_CONFIG[backend]["model"]
        else:
            self._model = "deepseek-chat"

        # Resolve base URL for known OpenAI-compatible backends
        if backend != "anthropic" and not self._base_url:
            self._base_url = BACKEND_CONFIG.get(backend, {}).get("base_url", "")

        # Init Anthropic client if needed
        if backend == "anthropic":
            from anthropic import Anthropic
            client_args = {"api_key": api_key}
            if self._base_url:
                client_args["base_url"] = self._base_url
            self._anthropic = Anthropic(**client_args)
        else:
            self._anthropic = None

    # ------------------------------------------------------------------
    def translate(
        self, content: str, file_type: str
    ) -> Optional[Tuple[str, int, int]]:
        if self._backend == "anthropic":
            return self._translate_anthropic(content, file_type)
        return self._translate_openai_compatible(content, file_type)

    # ------------------------------------------------------------------
    def _translate_anthropic(self, content: str, file_type: str):
        system_prompt = pick_prompt(file_type)
        line_count = content.count("\n")
        max_tok = MAX_TOKENS_LARGE if line_count > LARGE_FILE_LINES else MAX_TOKENS_SMALL

        for attempt in range(MAX_RETRIES):
            try:
                self._limiter.wait()
                resp = self._anthropic.messages.create(
                    model=self._model,
                    max_tokens=max_tok,
                    system=[{
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }],
                    messages=[{"role": "user", "content": content}],
                )
                text = _clean_output(resp.content[0].text, file_type)
                return text, resp.usage.input_tokens, resp.usage.output_tokens
            except Exception as exc:
                wait_s = INITIAL_BACKOFF_S * (2 ** attempt)
                print(f"  [{attempt+1}/{MAX_RETRIES}] {exc}", file=sys.stderr)
                if attempt < MAX_RETRIES - 1:
                    print(f"  Retrying in {wait_s}s …", file=sys.stderr)
                    time.sleep(wait_s)
        return None

    # ------------------------------------------------------------------
    def _translate_openai_compatible(self, content: str, file_type: str):
        system_prompt = pick_prompt(file_type)
        line_count = content.count("\n")
        max_tok = MAX_TOKENS_LARGE if line_count > LARGE_FILE_LINES else MAX_TOKENS_SMALL

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            "max_tokens": max_tok,
            "temperature": 0.1,
        }

        for attempt in range(MAX_RETRIES):
            try:
                self._limiter.wait()
                resp = requests.post(url, headers=headers, json=payload, timeout=180)
                if resp.status_code != 200:
                    err = resp.text[:300]
                    print(f"  HTTP {resp.status_code}: {err}", file=sys.stderr)
                    wait_s = INITIAL_BACKOFF_S * (2 ** attempt)
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(wait_s)
                    continue

                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                in_tok  = usage.get("prompt_tokens", 0)
                out_tok = usage.get("completion_tokens", 0)

                text = _clean_output(text, file_type)
                return text, in_tok, out_tok

            except Exception as exc:
                wait_s = INITIAL_BACKOFF_S * (2 ** attempt)
                print(f"  [{attempt+1}/{MAX_RETRIES}] {exc}", file=sys.stderr)
                if attempt < MAX_RETRIES - 1:
                    print(f"  Retrying in {wait_s}s …", file=sys.stderr)
                    time.sleep(wait_s)
        return None


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------

def _clean_output(text: str, file_type: str) -> str:
    """Strip ``` fences the LLM sometimes adds, plus minor fixups."""
    t = text.strip()
    if t.startswith("```"):
        idx = t.find("\n")
        if idx != -1:
            t = t[idx + 1:]
    if t.endswith("```"):
        t = t[: t.rfind("\n")].rstrip()
    return t + "\n"


# ---------------------------------------------------------------------------
# Progress tracker (JSON file in dst root)
# ---------------------------------------------------------------------------

class ProgressTracker:
    def __init__(self, dst_root: str):
        self._path = os.path.join(dst_root, PROGRESS_FILENAME)
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.isfile(self._path):
            with open(self._path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        return {"started_at": None, "model": MODEL_DEFAULT, "files": {}}

    def save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, ensure_ascii=False)

    def is_done(self, rel_path: str, chash: str) -> bool:
        entry = self._data["files"].get(rel_path)
        return (
            entry is not None
            and entry.get("status") == "done"
            and entry.get("input_hash") == chash
        )

    def mark_done(self, rel_path: str, chash: str, tokens: dict):
        self._data["files"][rel_path] = {
            "status": "done",
            "input_hash": chash,
            "tokens_used": tokens,
            "translated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.save()

    def mark_failed(self, rel_path: str, error: str):
        self._data["files"][rel_path] = {
            "status": "failed",
            "error": error[:500],
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        self.save()

    def mark_skipped(self, rel_path: str, reason: str):
        self._data["files"][rel_path] = {
            "status": "skipped",
            "reason": reason,
        }
        self.save()


# ---------------------------------------------------------------------------
# File classifier
# ---------------------------------------------------------------------------

def classify(filepath: str) -> str:
    """Return 'markdown' | 'json' | 'plugin.json' | 'skip'."""
    base = os.path.basename(filepath)
    ext  = os.path.splitext(filepath)[1].lower()

    if ext not in TRANSLATE_EXTENSIONS:
        return "skip"
    if base == "plugin.json":
        return "plugin.json"
    if ext == ".json":
        if base in JSON_SKIPLIST:
            return "skip"
        return "json"
    return "markdown"


def should_skip_name(name: str) -> bool:
    if name in SKIP_DIRS or name in SKIP_FILES:
        return True
    for pat in SKIP_EXTENSIONS:
        if name.endswith(pat):
            return True
    return False


# ---------------------------------------------------------------------------
# Core — recursive processor
# ---------------------------------------------------------------------------

def process(
    src_dir: str,
    dst_dir: str,
    translator: Optional[Translator],
    progress: ProgressTracker,
    *,
    dry_run: bool = False,
    resume:  bool = True,
    single_file: Optional[str] = None,
) -> dict:
    stats = {"total": 0, "translated": 0, "skipped": 0, "failed": 0, "copied": 0, "raw_unchanged": 0}
    token_total = {"input": 0, "output": 0}

    # Walk the tree
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if not should_skip_name(d)]
        rel_root = os.path.relpath(root, src_dir)
        if rel_root == ".":
            rel_root = ""

        for fn in sorted(files):
            if should_skip_name(fn):
                continue

            filepath = os.path.join(root, fn)
            rel_path = os.path.join(rel_root, fn) if rel_root else fn

            # --single-file filter
            if single_file:
                if rel_path.replace("\\", "/") != single_file.replace("\\", "/"):
                    if not dry_run:
                        if _copy_raw(filepath, os.path.join(dst_dir, rel_path)):
                            stats["copied"] += 1
                        else:
                            stats["raw_unchanged"] += 1
                    else:
                        stats["copied"] += 1
                    continue

            ftype = classify(filepath)
            if ftype == "skip":
                if not dry_run:
                    if _copy_raw(filepath, os.path.join(dst_dir, rel_path)):
                        stats["copied"] += 1
                    else:
                        stats["raw_unchanged"] += 1
                else:
                    stats["copied"] += 1
                continue

            stats["total"] += 1

            # Read
            try:
                with open(filepath, "r", encoding="utf-8") as fh:
                    content = fh.read()
            except (UnicodeDecodeError, OSError):
                print(f"SKIP (binary/unreadable): {rel_path}")
                stats["skipped"] += 1
                continue

            # Chinese check — skip if barely any Chinese
            ratio = chinese_line_ratio(content)
            if ratio < MIN_CHINESE_RATIO:
                print(f"SKIP (CN ratio {ratio:.1%}): {rel_path}")
                stats["skipped"] += 1
                if not dry_run:
                    _copy_raw(filepath, os.path.join(dst_dir, rel_path))
                progress.mark_skipped(rel_path, f"CN ratio {ratio:.1%}")
                continue

            chash = content_hash(content)

            # Resume?
            if resume and progress.is_done(rel_path, chash):
                print(f"SKIP (already done): {rel_path}")
                stats["skipped"] += 1
                continue

            print(f"TRANSLATE [{ftype}] ({content.count(chr(10))} lines): {rel_path}")

            if dry_run:
                stats["translated"] += 1
                continue

            # Translate
            result = translator.translate(content, ftype)

            if result is None:
                stats["failed"] += 1
                progress.mark_failed(rel_path, "API returned None after retries")
                continue

            out_text, in_tok, out_tok = result
            token_total["input"] += in_tok
            token_total["output"] += out_tok

            # Write
            dst_path = os.path.join(dst_dir, rel_path)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            with open(dst_path, "w", encoding="utf-8") as fh:
                fh.write(out_text)

            progress.mark_done(rel_path, chash, {"input": in_tok, "output": out_tok})
            stats["translated"] += 1
            print(f"   OK  {in_tok}+{out_tok} tokens")

    # Print cost estimate
    if token_total["input"] or token_total["output"]:
        # Sonnet pricing (may drift — check https://www.anthropic.com/pricing)
        cost = (
            token_total["input"] / 1_000_000 * 3.0
            + token_total["output"] / 1_000_000 * 15.0
        )
        print(f"\nTokens: {token_total['input']:,} in + {token_total['output']:,} out")
        print(f"Estimated cost: ${cost:.2f} (Sonnet pricing)")

    return stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _copy_raw(src: str, dst: str) -> bool:
    """Copy src → dst. Returns True if copied, False if already identical."""
    with open(src, "rb") as f_in:
        content = f_in.read()
    if os.path.isfile(dst):
        with open(dst, "rb") as f_out:
            if f_out.read() == content:
                return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "wb") as f_out:
        f_out.write(content)
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Recursive Chinese→English translation via LLM API"
    )
    parser.add_argument("--src", required=True, help="Source root directory")
    parser.add_argument("--dst", required=True, help="Output root directory")
    parser.add_argument(
        "--backend", default=default_backend(),
        choices=VALID_BACKENDS,
        help=f"API backend (default: {BACKEND_DEFAULT})",
    )
    parser.add_argument(
        "--base-url",
        default=env_value("SKILLS_TRANSLATE_BASE_URL"),
        help="Custom OpenAI-compatible base URL, or Anthropic-compatible base URL for --backend anthropic",
    )
    parser.add_argument(
        "--api-key",
        help="API key (env: SKILLS_TRANSLATE_API_KEY, ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or DEEPSEEK_API_KEY)",
    )
    parser.add_argument(
        "--model",
        default=env_value("SKILLS_TRANSLATE_MODEL", "ANTHROPIC_MODEL"),
        help="Model name (default depends on backend)",
    )
    parser.add_argument("--dry-run", action="store_true", help="List files, no API calls")
    parser.add_argument("--no-resume", action="store_true", help="Ignore progress file")
    parser.add_argument("--rpm", type=int, default=REQUESTS_PER_MINUTE)
    parser.add_argument("--file", dest="single_file", help="Translate a single relative path")

    args = parser.parse_args()

    if not args.base_url and args.backend == "anthropic":
        args.base_url = env_value("ANTHROPIC_BASE_URL")

    if not args.dry_run and args.backend == "custom" and not args.base_url:
        print("ERROR: --backend custom requires --base-url or SKILLS_TRANSLATE_BASE_URL", file=sys.stderr)
        sys.exit(1)

    # API key — try multiple sources
    api_key = args.api_key
    if not api_key:
        api_key = resolve_api_key(args.backend)
    if not api_key and not args.dry_run:
        print(
            "ERROR: provide --api-key or set SKILLS_TRANSLATE_API_KEY / "
            "ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / DEEPSEEK_API_KEY",
            file=sys.stderr,
        )
        sys.exit(1)

    src = os.path.abspath(args.src)
    dst = os.path.abspath(args.dst)

    if not os.path.isdir(src):
        print(f"ERROR: source not found: {src}", file=sys.stderr)
        sys.exit(1)

    print(f"Source  : {src}")
    print(f"Output  : {dst}")
    print(f"Backend : {args.backend}")
    print(f"Model   : {args.model or 'auto'}")
    print(f"Mode    : {'DRY-RUN' if args.dry_run else 'TRANSLATE'}\n")

    translator = None
    if not args.dry_run:
        translator = Translator(
            api_key=api_key,
            backend=args.backend,
            model=args.model,
            base_url=args.base_url,
            rpm=args.rpm,
        )

    progress = ProgressTracker(dst)
    if progress._data["started_at"] is None:
        progress._data["started_at"] = datetime.now(timezone.utc).isoformat()
        progress._data["backend"] = args.backend
        progress._data["model"] = args.model or translator._model if translator else ""
        progress.save()

    stats = process(
        src, dst, translator, progress,
        dry_run=args.dry_run,
        resume=not args.no_resume,
        single_file=args.single_file,
    )

    print(
        f"\nDone. total={stats['total']}  translated={stats['translated']}"
        f"  skipped={stats['skipped']}  failed={stats['failed']}"
        f"  copied={stats['copied']}  raw_unchanged={stats['raw_unchanged']}"
    )


if __name__ == "__main__":
    main()
