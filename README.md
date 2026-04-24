# haiku-diff

Human-readable git diff summaries. What changed. In plain language. No wall of red and green.

## What it does

Reads a git diff and tells you, per file: what kind of change it was, which functions were added or removed, new dependencies, whether it's a test or config file. Groups by change size so the big stuff comes first.

## Usage

```
haiku-diff                    # working tree vs HEAD
haiku-diff --staged           # staged changes only
haiku-diff --last             # last commit
haiku-diff --last 5           # last 5 commits
haiku-diff --commit abc1234   # specific commit
haiku-diff --since yesterday  # since yesterday
haiku-diff --since "1 week ago"
haiku-diff -- src/api.py      # specific file(s)
```

### Output modes

```
haiku-diff --short                  # one line per file, no blank padding
haiku-diff --color always           # force ANSI color
haiku-diff --color never            # disable color (also: set NO_COLOR=1)
haiku-diff --json                   # structured JSON output
```

Color defaults to `auto` — on when stdout is a TTY, off when piped. Use `--color always` when you want color through `tee` or `less -R`.

### JSON output

`--json` emits a machine-readable summary — useful for CI scripts, dashboards, or piping into other tools.

```json
{
  "changed": 3,
  "additions": 45,
  "deletions": 12,
  "files": [
    {
      "path": "src/api.py",
      "additions": 30,
      "deletions": 8,
      "is_new": false,
      "is_deleted": false,
      "symbols_added": ["handle_request", "validate_input"],
      "symbols_removed": [],
      "imports_added": ["httpx"],
      "tags": [],
      "description": "+30/-8 (net +22) — added: `handle_request`, `validate_input` — deps: httpx"
    }
  ]
}
```

Tags are `"test"`, `"config"`, `"docs"`, or `"lockfile"`. Empty list means none applied.

Example: find all test files changed in the last commit:
```bash
haiku-diff --json --last 1 | jq '[.files[] | select(.tags[] == "test") | .path]'
```

## CI / GitHub Actions

Once installed, `haiku-diff` is CI-friendly: it reads `git` history and writes to stdout, no config needed.

**Summarize what a PR touched:**

```yaml
steps:
  - uses: actions/checkout@v4
    with:
      fetch-depth: 0   # needed for history; default shallow clone only has depth 1

  - name: Diff summary
    run: haiku-diff --last 1 --short --color never
```

**Gate on file type changes:**

```yaml
  - name: Audit if lockfile changed
    run: |
      LOCKFILES=$(haiku-diff --json --last 1 | python3 -c "
      import sys, json
      d = json.load(sys.stdin)
      print(sum(1 for f in d['files'] if 'lockfile' in f['tags']))
      ")
      [ "$LOCKFILES" -gt 0 ] && npm audit || true
```

**Post a diff summary as a PR comment:**

```yaml
  - name: Comment diff summary
    env:
      GH_TOKEN: ${{ github.token }}
    run: |
      haiku-diff --last 1 --color never | gh pr comment ${{ github.event.pull_request.number }} --body-file -
```

**Note:** Pass `fetch-depth: 0` in `actions/checkout` when using `--since` or `--last N` with N > 1. Without it, the checkout is shallow and older commits won't be available.

## Example output

```
10 files changed  (+4625 -27)

  lib/ker_learning.py
    new file — 1300 lines — added: `_load_inflection_evidence`, `_load_reflection_evidence` +16 more — deps: argparse, json, os
  tools/checkin/generate_checkin.py
    +83/-17 (net +66) — changed: `_user_prompt`, `_generate_via_ollama` — deps: os
  tools/plainlog/test_plainlog.py
    +80/-1 (net +79) — changed: `run_cli`, `test_dir_uses_custom_log_directory` — [test]
  NOTES.md
    +29/-1 (net +28) — [docs]
```

## Install

```bash
bash install.sh
```

Symlinks `haiku-diff.py` into `/usr/local/bin/haiku-diff`.

## Requirements

- Python 3.7+
- git in PATH
- Must be run inside a git repository

## Limitations

- Symbol detection works for Python (with decorator context), JS/TS, Go, Ruby, Rust, Java/Kotlin/C# — other languages get line counts only
- No semantic understanding — it reads structure, not meaning
- `--since` uses `git log --since` which follows reflog; very old date refs may not resolve on shallow clones
- Does not summarize binary file changes (reports "binary file" from git)

## Free to use

MIT license. No API keys. No network required.
