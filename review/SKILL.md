---
name: mpy-review
description: Use this skill when the user wants to review MicroPython code changes using historical review patterns. Invoke when user mentions reviewing code, finding review examples, or wants feedback on MicroPython PRs/commits/diffs. Provides semantic search across ~19.5K categorized review comments.
---

# MicroPython Review Assistant Skill

## Purpose

This skill provides AI-assisted code review for MicroPython using historical review patterns from the lead maintainer. It searches a database of ~19.5K categorized review comments to find relevant examples and generate review context.

**Note:** When the `mpy-reviewer` MCP server is available (registered in `.claude/settings.json`), prefer using MCP tools directly (`review_diff`, `search_reviews`, etc.) instead of the CLI. The MCP server keeps the embedding model warm across calls, eliminating 2-3s cold start per query. This skill remains as a fallback for sessions outside the project scope.

**IMPORTANT: The `review_diff` MCP tool accepts diffs of any size.** Do NOT fall back to CLI because a diff seems "too large". Pass the full diff text directly as the `diff_text` parameter regardless of length. The tool internally splits multi-file diffs into per-file chunks for embedding, so large diffs are handled efficiently.

**MCP file-based output:** The MCP `review_diff` and `review_pr` tools return a compact orchestration prompt (~5-8K) instead of raw data. Review examples are written to individual temp files under `/tmp/mpy-review-*/`. The prompt includes a summary table with file paths, sizes, severities, and domains. To use the examples:
- Read small files (<2KB) directly with the Read tool
- For large files (>2KB), consider spawning subagents to process them in parallel
- The diff is NOT echoed back — you already have it in context from when you generated it

## When to Use This Skill

Invoke this skill when the user:
- Wants to review code changes (branches, commits, diffs, PRs)
- Asks for maintainer-style feedback on their code
- Wants to find examples of specific review patterns
- Needs review context for MicroPython code
- Mentions reviewing, feedback, or code quality for MicroPython

**Important:** Users cannot invoke skills directly. They must ask you to use the skill:
- User: "Can you review my current branch?"
- User: "Can you /mpy-review the current branch?"

When the user asks for review help, invoke this skill proactively.

## Requirements

This skill requires **codanna** for semantic code search and codebase analysis.

**Automatic setup:** A SessionStart hook automatically installs codanna via cargo on first use.

**Manual installation:**
```bash
cargo install codanna --all-features
```

If codanna is not installed, the tool will fail with a prominent error message directing the user to install it.

## Tool Location

The underlying CLI tool is located at:
```
uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer
```

Always use this full path when invoking the tool. Do not rely on PATH.

## Understanding User Intent

Parse natural language requests and map to appropriate tool commands:

### Review Current Changes
**User says:** "review my current changes", "review this branch", "review what I've done"

**What to do:**
1. Generate diff: `git diff main` (or appropriate base branch)
2. Pipe to tool: `git diff main | uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer review --stdin --codebase --output prompt`
3. Present the review prompt to help the user

**Example:**
```bash
git diff main | uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer review --stdin --codebase --output prompt
```

### Review Specific Commit
**User says:** "review commit abc123", "check commit abc123"

**What to do:**
1. Get commit diff: `git show abc123`
2. Pipe to tool: `git show abc123 | uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer review --stdin --output prompt`

**Example:**
```bash
git show ca65d543 | uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer review --stdin --codebase --output prompt
```

### Review Uncommitted Changes
**User says:** "review my uncommitted changes", "review staged changes"

**What to do:**
```bash
# All uncommitted changes (staged + unstaged)
git diff HEAD | uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer review --stdin --output prompt

# Only staged changes
git diff --cached | uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer review --stdin --output prompt
```

### Review GitHub PR
**User says:** "review PR 12345", "check pull request 12345"

**What to do:**
```bash
uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer review --pr 12345 --codebase --output prompt
```

### Review Specific Files
**User says:** "review my changes to py/gc.c", "review changes in extmod/"

**What to do:**
```bash
git diff main -- py/gc.c | uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer review --stdin --output prompt

git diff main -- extmod/ | uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer review --stdin --codebase --output prompt
```

### Find Review Examples
**User says:** "find examples of memory allocation reviews", "show me feedback on error handling"

**What to do:**
```bash
uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer search "memory allocation" --domain memory -k 10

uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer search "error handling" --domain correctness -k 10
```

### Get Quick Context (No Full Prompt)
**User says:** "show me similar reviews", "what has been said about this before"

**What to do:**
Use `--output context` instead of `--output prompt` to get just the examples without full prompt structure:
```bash
git diff main | uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer review --stdin --output context
```

## Tool Commands Reference

### Review Command
```bash
uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer review [OPTIONS]
```

**Input Options (choose one):**
- `--diff FILE` - Review a diff file
- `--pr NUMBER` - Review a GitHub PR (uses gh CLI)
- `--stdin` - Read diff from stdin (recommended for git integration)

**Quality Options:**
- `--codebase` - Include MicroPython codebase context (definitions, patterns) [RECOMMENDED]
- `--rerank` - Use cross-encoder re-ranking for better relevance (slower, 5-10s on CPU)
- `-k N` - Number of review examples (default: 8)

**Output Options:**
- `--output context` - Just the review examples (default, quick to read)
- `--output prompt` - Full prompt ready for AI review (recommended for comprehensive review)
- `--output json` - Structured JSON output

### Search Command
```bash
uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer search "query" [OPTIONS]
```

**Options:**
- `-k N` - Number of results (default: 10)
- `--domain DOMAIN` - Filter by domain (see categories below)
- `--severity SEVERITY` - Filter by severity (blocking, suggestion, nitpick)
- `--component COMPONENT` - Filter by component (py_core, extmod, port_specific, etc.)
- `--style-only` - Only show comments that exemplify the maintainer's style
- `--json` - JSON output

### Stats Command
```bash
uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer stats
```

Shows index status and record count. Use this to verify the system is working.

## Categories for Filtering

### Domains (use with --domain)
- `correctness` - Logic bugs, edge cases, error handling
- `code_style` - Formatting, naming conventions
- `api_design` - Public interfaces, function design
- `memory` - Memory management, leaks, allocation
- `performance` - Speed, efficiency optimizations
- `portability` - Cross-platform compatibility
- `documentation` - Comments, docs, clarity
- `testing` - Test coverage, quality
- `security` - Security vulnerabilities
- `architecture` - Design patterns, structure
- `build_system` - Makefiles, build configuration
- `error_handling` - Error paths, recovery

### Severities (use with --severity)
- `blocking` - Must fix before merge
- `suggestion` - Recommended improvement
- `nitpick` - Minor style/preference

### Components (use with --component)
- `py_core` - Core Python runtime (py/)
- `extmod` - Extended modules (extmod/)
- `port_specific` - Port implementations (ports/)
- `drivers` - Hardware drivers
- `tools` - Build/dev tools
- `tests` - Test suite
- `docs` - Documentation
- `build_system` - Build configuration

## Output Interpretation

### Context Output (--output context)
Returns formatted markdown with:
- Review examples with diff context
- Review comments
- Domain and severity tags

Present this directly to the user to show relevant past reviews.

### Prompt Output (--output prompt)
Returns a complete prompt containing:
- Review style guide
- 5-10 relevant review examples with code context
- The code to review
- Task instructions for AI review

**How to use:** After generating this prompt, you should:
1. Present it to the user, OR
2. Use it internally to generate a maintainer-style review yourself

**Note:** When using the MCP server instead of CLI, the `review_diff`/`review_pr` tools return an orchestration prompt with temp file paths rather than inlining all examples. Read the referenced files to access the full review examples.

### JSON Output (--output json)
Returns structured data. Parse and present relevant fields to user.

## Two-Step Verification Workflow

After generating findings, use the `verify_findings` MCP tool to cross-check each
finding against the actual codebase before presenting results. This reduces false
positives caused by pattern-matching without context.

### Structured Finding Format

Findings must be formatted as a JSON array:
```json
[
  {
    "file": "extmod/asyncio/stream.py",
    "line": 42,
    "severity": "blocking",
    "description": "POLLHUP not handled in ioctl bitmask",
    "diff_hunk": "the relevant diff hunk text"
  }
]
```

### verify_findings Tool

```
verify_findings(findings, diff_text, pr_number=None, repo="micropython/micropython")
```

- `findings`: JSON array of structured findings (format above)
- `diff_text`: the full unified diff being reviewed
- `pr_number`: optional PR number
- `repo`: repository slug

Returns a markdown orchestration prompt with a summary table and paths to
per-finding verdict files under `/tmp/mpy-verify-*/`.

### Verdict Types

- **confirmed**: finding is valid; keep as-is (or with adjusted severity)
- **partially_valid**: finding has merit but needs adjustment; update severity/description
- **false_positive**: finding is wrong; drop it from the review
- **inconclusive**: verification could not determine validity; use your judgment

### Verification Workflow

1. Generate diff (git diff, git show, etc.)
2. Call `review_diff` to get examples and style context
3. Read examples and analyze the diff
4. Assemble findings as a JSON array
5. Call `verify_findings(findings, diff_text)` to cross-check
6. Read verdict files for evidence
7. Drop false positives, adjust partially valid findings
8. Present verified findings as the final review

## Workflow Examples

### Example 1: User Wants General Review

**User:** "Can you review my current changes?"

**Your response:**
1. Run: `git diff main | uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer review --stdin --codebase --output prompt`
2. Read the generated prompt
3. Use the prompt to provide maintainer-style review feedback to the user

### Example 2: User Wants Quick Examples

**User:** "What has been said about similar code before?"

**Your response:**
1. Run: `git diff main | uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer review --stdin --output context`
2. Present the review examples to the user directly
3. Summarize common themes

### Example 3: User Asks About Specific Pattern

**User:** "Find me examples of feedback on GPIO configuration"

**Your response:**
1. Run: `uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer search "GPIO configuration" --component port_specific -k 15`
2. Present the search results
3. Summarize key patterns

### Example 4: User Mentions Specific Commit

**User:** "Review commit ca65d543"

**Your response:**
1. Run: `git show ca65d543 | uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer review --stdin --codebase --output prompt`
2. Use the prompt to provide review feedback
3. Highlight key issues found from similar past reviews

### Example 5: User Asks to Review Specific File

**User:** "Can you review my changes to py/gc.c?"

**Your response:**
1. Run: `git diff main -- py/gc.c | uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer review --stdin --codebase --output prompt`
2. Provide targeted review focusing on that file
3. Reference relevant review patterns for GC code

## Decision Guide: When to Use Which Options

### Use `--codebase`
**When:** User wants comprehensive review, mentions API usage, function calls, or needs context
**Why:** Includes MicroPython codebase definitions and patterns
**Cost:** +2-3 seconds

### Use `--rerank`
**When:** User emphasizes quality/accuracy, or initial results seem off-topic
**Why:** Better relevance via cross-encoder scoring
**Cost:** +5-10 seconds on CPU

### Use `--output prompt`
**When:** User wants detailed review, mentions "thorough", or you'll provide review feedback
**Why:** Gives you complete context to generate maintainer-style review
**Cost:** Longer output to process

### Use `--output context`
**When:** User asks for examples, "what has been said", or wants quick reference
**Why:** Just the examples, faster to read
**Cost:** Minimal

### Use `search` instead of `review`
**When:** User asks about patterns/topics without providing specific code to review
**Example:** "What do reviewers think about error handling?"
**Why:** Semantic search, not diff-based retrieval

## Handling Errors

### "Index not found"
The vector index hasn't been built. Inform user:
```
The review database index needs to be built first. Run:
cd ${CLAUDE_PLUGIN_ROOT}
uv run python scripts/build_index_resume.py
```

### "Command not found"
Verify uv and the project are accessible:
```bash
uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer stats
```

### Git errors (no repository, invalid ref, etc.)
Handle appropriately - ask user to clarify or check their git state.

## Performance Expectations

- **First query:** 2-3 seconds (model loading)
- **Subsequent queries:** 0.5-1 second (dense search only)
- **With --rerank:** +5-10 seconds on CPU
- **With --codebase:** +2-3 seconds

Inform user if a long operation is running.

## Data Scope

The database contains:
- **~19.5K categorized review comments**
- **Source:** micropython/micropython and micropython/micropython-lib repositories
- **Timeframe:** 2013-2026
- **Coverage:** All PR review comments, issue comments, and review verdicts

## Natural Language Understanding

Be flexible with user requests. Map to appropriate commands:

| User Intent | Tool Command |
|-------------|--------------|
| "review this" | `git diff \| ... review --stdin` |
| "review commit X" | `git show X \| ... review --stdin` |
| "review PR 123" | `... review --pr 123` |
| "find GPIO reviews" | `... search "GPIO" --component port_specific` |
| "show me memory issues" | `... search "memory" --domain memory --severity blocking` |
| "examples of his style" | `... search "..." --style-only` |

Always interpret user intent conversationally, then invoke the appropriate tool command.

## Important Notes

1. **Always use full path:** `uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer`
2. **Prefer stdin for git integration:** Use `git diff \| ... --stdin` over temp files
3. **Default to quality:** Use `--codebase --output prompt` unless user wants quick results
4. **Be conversational:** Don't just relay CLI output, interpret and present meaningfully
5. **Handle context:** If reviewing specific commits/branches, mention what's being reviewed
6. **Cite examples:** When referencing review patterns, show the actual comments from search results

## Verification

To test the skill is working:
```bash
uv run --project ${CLAUDE_PLUGIN_ROOT} mpy-reviewer stats
```

Should show:
- Index exists: True
- Number of records: ~19.5K
