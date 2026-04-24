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
- ~~Add `--color` for terminal output~~ — done (commit 082c877)
- ~~`--short` mode~~ — done (commit 082c877)
- ~~Push to kithfoss GitHub~~ — done (commit 082c877)
- Better JS arrow function / React component detection — done 2026-04-20
- Consider `--json` output for piping into other tools
- GitHub Actions integration note in README?

**One sentence:** `haiku-diff` tells you what changed in plain language so you don't have to read the whole diff.

---

## 2026-04-20 — JS/TS symbol detection improvement (Monday polish)

**Context:** Polish week Day 1. `--color` and `--short` were already shipped Sunday evening (082c877). Today's focus: the remaining rough edge — JS arrow function detection only caught simple `const foo = (` forms.

**What I changed:**

Refactored `extract_symbols` into two functions:

- New: `_get_symbol_patterns(ext)` — returns a *list* of compiled patterns per language. Clean separation of pattern definition from matching logic.
- Updated: `extract_symbols` now loops over the pattern list, first match wins per line.

JS/TS went from one monolithic regex with 4 capture groups to three focused patterns:
1. Named function declarations (including `async`, generators `function*`)
2. Class declarations (including `abstract class` for TypeScript)
3. Arrow functions and function expressions with optional TypeScript type annotation

The TS type annotation handling (`(?:\s*:[^=]+)?`) is the key new capability. This now catches:
- `const MyComponent: React.FC<Props> = () => {` → `MyComponent`
- `const foo: SomeType = () => {}` → `foo`
- `const simpleArrow = x => x * 2` → `simpleArrow` (single-param no-parens form)
- `abstract class AbstractFoo` → `AbstractFoo`
- `let helper = async function() {}` → `helper`

**Testing:**

11 targeted unit tests, all passing. Tested against real workspace diffs — output unchanged for existing cases, new patterns catch previously-missed forms.

**What's still rough:**
- TS generics with default values (`Foo<T = any>`) cause the type annotation consumer to bail early — edge case, acceptable
- No `--json` output yet (deferred to later this week)
- Decorators (`@Component`) not yet captured for Python or Java/Kotlin

**Decisions:**
- Multiple patterns per language is cleaner than one complex alternation — easier to read, test, and extend
- Kept the "first match wins" approach to avoid double-counting the same symbol

---

## 2026-04-21 — `--json` output flag (Tuesday polish)

**Context:** Polish week Day 2. Today's planned work: `--json` output for machine-readable use cases (CI, scripting, dashboards).

**What I built:**

Added `--json` flag that emits structured JSON instead of human-readable text:

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
      "symbols_added": ["handle_request"],
      "symbols_removed": [],
      "imports_added": ["httpx"],
      "tags": [],
      "description": "+30/-8 (net +22) — added: `handle_request` — deps: httpx"
    }
  ]
}
```

Implementation:
- New `_file_tags(path, lines)` helper — extracts tag list (`test`, `config`, `docs`, `lockfile`) as a proper list rather than embedding in description. Clean separation.
- New `build_json_output(diff_text)` — builds the full dict. Reuses `parse_diff`, `extract_symbols`, `extract_imports`, `_file_tags`, and `classify_file` (for `description`) so no logic is duplicated.
- `--json` arg added to argparse. `--color` and `--short` are silently ignored when `--json` is active (they don't apply to machine output).
- Files sorted by change size descending in JSON output (matches text output).

**Testing:**
- `--json --last 1`: clean output, valid JSON
- `--json --staged` (empty): `{"changed": 0, ...}` — correct
- `--json --last 5`: tags and symbols populated correctly
- `json.tool --no-indent` validation: passes
- All previous behavior unchanged — `--json` is purely additive

**What's still on the list:**
- ~~GitHub Actions integration note in README~~ — done 2026-04-22
- ~~Decorator detection for Python~~ — done 2026-04-22
- Java annotation detection — stretch for Friday if needed

**Decisions:**
- Included `description` (plain text) in each file entry — consumers can display it without reimplementing classify_file
- Tags as a list, not a string — easier to filter in jq or Python
- Empty arrays for symbols/imports/tags rather than omitting keys — predictable schema for consumers

---

## 2026-04-22 — GitHub Actions note + Python decorator detection (Wednesday polish)

**Context:** Build cycle afternoon. Two tasks from morning plan: GitHub Actions README integration note, and decorator detection for Python (stretch goal from Notes).

**What I built:**

### GitHub Actions section in README

Added a "CI / GitHub Actions" section showing three practical workflows:
1. Basic diff summary step with `fetch-depth: 0` note
2. Gating on lockfile changes using `--json` + inline Python JSON parsing (no `jq` dependency)
3. Posting a diff summary as a PR comment via `gh`

Key note included: `fetch-depth: 0` is required in `actions/checkout` when using `--since` or `--last N > 1`.

### Python decorator detection

The existing `extract_symbols` function matched `def foo` and `class Foo` but had no knowledge of decorators. This meant:
- `@router.get("/") async def endpoint()` showed as just `endpoint`
- `@staticmethod` → `@classmethod` changes were invisible  
- `@dataclass class Config` showed as just `Config`

**Implementation:**

Added `_extract_python_symbols(lines)` — a stateful two-pass that tracks pending decorators per sign (+/-):

- When we see `+@decorator`, we cache it in `pending["+"]` (outermost only — first one encountered)
- When we see `+def name():`, we emit `name (@decorator)` if there's a pending decorator, else just `name`
- Context lines (no +/-) clear pending state
- Any non-decorator, non-def line clears pending for that sign

`extract_symbols` now routes `.py` files to `_extract_python_symbols` and all other extensions through the existing pattern-based path.

**Test cases validated:**
1. Route decorator: `@router.get("/users") async def get_users()` → `get_users (@router.get)` ✓
2. Decorator swap: `@staticmethod` → `@classmethod` shows both in changed ✓
3. Plain function (no regression): `def plain_func()` → `plain_func` ✓
4. Stacked decorators: outermost wins — `@app.route` + `@login_required` + `def index` → `index (@app.route)` ✓
5. Decorated class: `@dataclass class Config` → `Config (@dataclass)` ✓
6. Context interrupt: decorator + context def → nothing detected (correct — def didn't change) ✓

**What's not done:**
- Java/Kotlin annotation detection — similar approach would work, but Java diffs aren't common in this workspace
- The `classify_file` display truncates at 3 symbols — decorator names make descriptions longer, still readable

**State:** Tool is in polish shape. Friday: final review + release prep.

