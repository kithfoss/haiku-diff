# haiku-diff — Build Notes

## 2026-04-19 — First build (Sunday seed)

**Context:** Chosen this morning as the next weekly tool. Sunday is seeding day, but I had the afternoon so I built a working first version rather than just scoping it.

**What I built:**
- Full working `haiku-diff.py` — Python 3.7+, stdlib only, no credentials
- Symbol extraction for Python, JS/TS, Go, Ruby, Rust, Java/Kotlin/C#
- Import/dependency detection for Python and JS/TS
- File type classification (test, config, docs, lockfile)
- All four core modes working: --staged, --last N, --commit SHA, --since DATE
- Error handling: not-a-git-repo, no commits in range, empty diff
- install.sh (symlinker, same pattern as plainlog)
- README.md with usage, examples, limitations, honest "free to use" section

**Testing:**
- Tested against this workspace's actual commit history
- `--last 1`, `--last 3`: clean, accurate, symbols detected
- `--commit SHA`: working for single-file and multi-file commits
- `--since "3 days ago"`: working, found 18 files across the range
- `--staged` with no staged changes: "No changes." — correct
- Not-a-git-repo: exits with clear message — correct

**What works well:**
- The +16 more pattern for long symbol lists is clean
- Sorting by change size (biggest first) makes skimming fast
- Lockfile detection collapses noisy lock diffs into one line
- New file detection shows line count + symbols rather than +X/-0

**What's rough:**
- Symbol detection is heuristic — misses some patterns (decorators, complex class definitions)
- No color output yet — works fine in terminal, but color would help scannability
- No `--color/--no-color` flag
- The `--since` reflog syntax may behave oddly on very old refs or shallow clones
- For JS arrow functions (`const foo = () => ...`) the regex only catches simple assignment forms

**Decisions made:**
- Stdlib only — keeps it zero-dependency, installable anywhere with a Python 3.7+
- No AI summarization in this version — structural analysis only. Keeps it offline, instant, trustworthy
- Sort by change size descending — reviewers care most about big changes
- Kept the output format tight: two lines per file (path + description), not a table

**Next steps (Mon-Thu polish):**
- Add `--color` for terminal output (colorama optional, degrade gracefully)
- Better JS arrow function / React component detection
- Consider `--short` mode for just the headline + file list
- Consider `--json` output for piping into other tools
- GitHub Actions integration note in README?
- Push to kithfoss GitHub (same audience as plainlog)

**One sentence:** `haiku-diff` tells you what changed in plain language so you don't have to read the whole diff.
