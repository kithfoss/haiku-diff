#!/usr/bin/env python3
"""
haiku-diff — human-readable git diff summaries

What changed. In plain language. No wall of red and green.

Usage:
  haiku-diff                    summarize working tree vs HEAD
  haiku-diff --staged           summarize staged changes
  haiku-diff --commit SHA       summarize a specific commit
  haiku-diff --last [N]         summarize last N commits (default: 1)
  haiku-diff --since DATE       summarize changes since a date
  haiku-diff [files...]         limit to specific files
"""

import subprocess
import sys
import re
import os
import argparse
from collections import defaultdict

# Optional color support: use native ANSI on POSIX (terminals handle it),
# bring in colorama only on Windows so cmd.exe cooperates. Stripping is NEVER
# done by colorama — the --color flag alone decides whether escape codes are
# emitted. This keeps `--color always | tee` working as expected.
if sys.platform == "win32":
    try:
        import colorama  # type: ignore

        colorama.just_fix_windows_console()
    except ImportError:
        pass


class _Style:
    """Tiny ANSI helper. Disabled instances no-op their .wrap() method."""

    ANSI = {
        "reset": "\033[0m",
        "bold": "\033[1m",
        "dim": "\033[2m",
        "green": "\033[32m",
        "red": "\033[31m",
        "yellow": "\033[33m",
        "cyan": "\033[36m",
        "blue": "\033[34m",
        "magenta": "\033[35m",
    }

    def __init__(self, enabled: bool):
        self.enabled = enabled

    def wrap(self, text: str, *styles: str) -> str:
        if not self.enabled or not styles:
            return text
        prefix = "".join(self.ANSI.get(s, "") for s in styles)
        return f"{prefix}{text}{self.ANSI['reset']}"


def _decide_color(flag: str) -> bool:
    """flag is 'auto', 'always', or 'never'."""
    if flag == "always":
        return True
    if flag == "never":
        return False
    # auto
    if not sys.stdout.isatty():
        return False
    if os.environ.get("NO_COLOR") is not None:
        return False
    return True


def run_git(*args, check=True):
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=True, text=True
    )
    if check and result.returncode != 0:
        print(f"git: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout, result.returncode


def get_diff(args):
    base_cmd = []

    if args.staged:
        base_cmd = ["diff", "--cached"]
    elif args.commit:
        base_cmd = ["diff", f"{args.commit}^!", ]
        # for merge commits, use the first parent
        base_cmd = ["diff", f"{args.commit}^", args.commit]
    elif args.last is not None:
        n = args.last if args.last > 0 else 1
        base_cmd = ["diff", f"HEAD~{n}", "HEAD"]
    elif args.since:
        # Find the oldest commit since that date, diff from its parent
        log_out, rc = run_git("log", f"--since={args.since}", "--format=%H", check=False)
        commits = [c for c in log_out.strip().splitlines() if c]
        if not commits:
            print(f"No commits since '{args.since}'.", file=sys.stderr)
            sys.exit(0)
        oldest = commits[-1]
        # Check if oldest has a parent
        parent_out, rc = run_git("rev-parse", "--verify", f"{oldest}^", check=False)
        if rc == 0:
            base_cmd = ["diff", f"{oldest}^", "HEAD"]
        else:
            base_cmd = ["diff", oldest, "HEAD"]
    else:
        base_cmd = ["diff", "HEAD"]

    file_args = (["--"] + args.files) if args.files else []

    stat_out, _ = run_git(*(base_cmd + ["--stat"] + file_args))
    diff_out, _ = run_git(*(base_cmd + file_args))

    return diff_out, stat_out


def parse_diff(diff_text):
    """Parse unified diff into per-file line records."""
    files = {}
    current_file = None
    current_lines = []
    is_new = False
    is_deleted = False

    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            if current_file:
                files[current_file] = {"lines": current_lines, "new": is_new, "deleted": is_deleted}
            current_lines = []
            current_file = None
            is_new = False
            is_deleted = False
        elif line.startswith("new file mode"):
            is_new = True
        elif line.startswith("deleted file mode"):
            is_deleted = True
        elif line.startswith("+++ b/"):
            current_file = line[6:]
        elif line.startswith("+++ /dev/null"):
            # deletion — keep the --- name
            pass
        elif line.startswith("--- a/") and current_file is None:
            current_file = line[6:]  # fallback for deletions
        elif current_file and len(line) > 0 and line[0] in ("+", "-"):
            if not (line.startswith("+++") or line.startswith("---")):
                current_lines.append(line)

    if current_file:
        files[current_file] = {"lines": current_lines, "new": is_new, "deleted": is_deleted}

    return files


def extract_symbols(lines, ext):
    """Extract added/removed named symbols (functions, classes, etc.)."""
    added = []
    removed = []

    # Patterns by language family
    if ext in (".py",):
        pattern = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+(\w+)")
    elif ext in (".js", ".ts", ".jsx", ".tsx", ".mjs"):
        pattern = re.compile(
            r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\s+(\w+)|"
            r"class\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s*)?\(|"
            r"(?:let|var)\s+(\w+)\s*=\s*function)"
        )
    elif ext in (".go",):
        pattern = re.compile(r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(")
    elif ext in (".rb",):
        pattern = re.compile(r"^\s*(?:def|class|module)\s+(\w+)")
    elif ext in (".rs",):
        pattern = re.compile(r"^\s*(?:pub\s+)?(?:fn|struct|enum|trait|impl)\s+(\w+)")
    elif ext in (".java", ".kt", ".cs"):
        pattern = re.compile(
            r"^\s*(?:public|private|protected|static|abstract|override|\s)*"
            r"(?:class|interface|enum|void|\w+)\s+(\w+)\s*(?:\(|<|\{)"
        )
    else:
        return added, removed

    for line in lines:
        if not line or line[0] not in ("+", "-"):
            continue
        stripped = line[1:]
        m = pattern.match(stripped)
        if m:
            name = next((g for g in m.groups() if g), None)
            if name and not name.startswith("_test") and len(name) > 1:
                (added if line[0] == "+" else removed).append(name)

    return added, removed


def extract_imports(lines, ext):
    """Return newly added import/require targets."""
    new_imports = []
    for line in lines:
        if not line.startswith("+"):
            continue
        s = line[1:].strip()
        # Python
        m = re.match(r"^(?:import|from)\s+([\w\.]+)", s)
        if m:
            new_imports.append(m.group(1).split(".")[0])
            continue
        # JS/TS require
        m = re.match(r'require\([\'"]([^\'"]+)[\'"]\)', s)
        if m:
            new_imports.append(m.group(1).split("/")[0].lstrip("@"))
            continue
        # JS/TS import
        m = re.match(r"^import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]", s)
        if m:
            pkg = m.group(1).split("/")[0].lstrip("@")
            if not pkg.startswith("."):
                new_imports.append(pkg)
    return new_imports


def classify_file(path, file_data):
    """Build a plain-language description of what changed in one file."""
    lines = file_data["lines"]
    is_new = file_data["new"]
    is_deleted = file_data["deleted"]

    ext = os.path.splitext(path)[1].lower()
    filename = os.path.basename(path)

    additions = sum(1 for l in lines if l.startswith("+"))
    removals = sum(1 for l in lines if l.startswith("-"))

    parts = []

    # File-level status
    if is_new:
        parts.append("new file")
    elif is_deleted:
        parts.append("deleted")

    # Line count summary
    if not is_new and not is_deleted:
        net = additions - removals
        if additions == 0 and removals > 0:
            parts.append(f"removed {removals} line{'s' if removals != 1 else ''}")
        elif removals == 0 and additions > 0:
            parts.append(f"added {additions} line{'s' if additions != 1 else ''}")
        else:
            direction = f"net +{net}" if net > 0 else (f"net {net}" if net < 0 else "same size")
            parts.append(f"+{additions}/-{removals} ({direction})")
    elif is_new:
        parts.append(f"{additions} line{'s' if additions != 1 else ''}")

    # Symbol changes
    added_syms, removed_syms = extract_symbols(lines, ext)
    if added_syms and not removed_syms:
        names = ", ".join(f"`{s}`" for s in added_syms[:3])
        more = f" +{len(added_syms)-3} more" if len(added_syms) > 3 else ""
        parts.append(f"added: {names}{more}")
    elif removed_syms and not added_syms:
        names = ", ".join(f"`{s}`" for s in removed_syms[:3])
        parts.append(f"removed: {names}")
    elif added_syms and removed_syms:
        parts.append(f"changed: {', '.join(f'`{s}`' for s in (added_syms + removed_syms)[:3])}")

    # New imports/dependencies
    new_imports = extract_imports(lines, ext)
    if new_imports:
        unique = list(dict.fromkeys(new_imports))[:3]
        parts.append(f"deps: {', '.join(unique)}")

    # File type hints
    is_test = bool(re.search(r"test|spec", filename, re.I))
    is_config = ext in (".json", ".yaml", ".yml", ".toml", ".ini", ".env", ".cfg", ".conf")
    is_doc = ext in (".md", ".rst", ".txt")
    is_lock = filename in ("package-lock.json", "yarn.lock", "Pipfile.lock", "poetry.lock", "go.sum")

    if is_lock:
        parts = [f"lockfile update ({additions} additions, {removals} removals)"]
    elif is_test:
        parts.append("[test]")
    elif is_config:
        parts.append("[config]")
    elif is_doc:
        parts.append("[docs]")

    return " — ".join(parts) if parts else f"+{additions}/-{removals}"


def summarize_diff(diff_text, stat_text, style=None, short=False):
    """Render a summary of diff_text.

    style  — a _Style instance (enabled or disabled). Omit for plain text.
    short  — one-line-per-file layout, no blank lines.
    """
    if style is None:
        style = _Style(False)

    if not diff_text.strip():
        return "No changes."

    files_data = parse_diff(diff_text)

    file_counts = {}
    for path, data in files_data.items():
        additions = sum(1 for l in data["lines"] if l.startswith("+"))
        removals = sum(1 for l in data["lines"] if l.startswith("-"))
        file_counts[path] = (additions, removals)

    total_files = len(file_counts)
    total_add = sum(v[0] for v in file_counts.values())
    total_del = sum(v[1] for v in file_counts.values())

    lines = []

    # Headline — bold, with colored +/- counts.
    add_str = style.wrap(f"+{total_add}", "green")
    del_str = style.wrap(f"-{total_del}", "red")
    files_str = style.wrap(
        f"{total_files} file{'s' if total_files != 1 else ''} changed", "bold"
    )
    headline = files_str
    if total_add or total_del:
        headline += f"  ({add_str} {del_str})"
    lines.append(headline)

    # Per-file breakdown — sort by change size descending.
    sorted_files = sorted(
        file_counts.items(), key=lambda x: x[1][0] + x[1][1], reverse=True
    )

    if short:
        # One line per file: "  path — description"
        for path, _ in sorted_files:
            description = classify_file(path, files_data[path])
            # Color the [tag] portions in description if present.
            description = _colorize_tags(description, style)
            lines.append(f"  {style.wrap(path, 'cyan')} — {description}")
    else:
        lines.append("")
        for path, _ in sorted_files:
            description = classify_file(path, files_data[path])
            description = _colorize_tags(description, style)
            lines.append(f"  {style.wrap(path, 'cyan')}")
            lines.append(f"    {description}")

    return "\n".join(lines)


_TAG_COLORS = {
    "[test]": "magenta",
    "[docs]": "blue",
    "[config]": "yellow",
}


def _colorize_tags(description: str, style: "_Style") -> str:
    """Paint any [tag] tokens in the description."""
    if not style.enabled:
        return description
    for tag, color in _TAG_COLORS.items():
        if tag in description:
            description = description.replace(tag, style.wrap(tag, color))
    # Plus/minus counts inside description
    description = re.sub(
        r"\+(\d+)", lambda m: style.wrap(f"+{m.group(1)}", "green"), description
    )
    description = re.sub(
        r"(?<![\w])-(\d+)",
        lambda m: style.wrap(f"-{m.group(1)}", "red"),
        description,
    )
    return description


def main():
    parser = argparse.ArgumentParser(
        prog="haiku-diff",
        description="human-readable git diff summaries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--staged", action="store_true", help="summarize staged changes")
    parser.add_argument("--commit", metavar="SHA", help="summarize a specific commit")
    parser.add_argument(
        "--last",
        metavar="N",
        type=int,
        nargs="?",
        const=1,
        help="summarize last N commits (default: 1)",
    )
    parser.add_argument("--since", metavar="DATE", help="changes since DATE (e.g. 'yesterday', '1 week ago')")
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="colorize output (default: auto — on when stdout is a TTY)",
    )
    parser.add_argument(
        "--short",
        action="store_true",
        help="one line per file, no blank-line padding",
    )
    parser.add_argument("files", nargs="*", help="limit to specific files")

    args = parser.parse_args()

    # Confirm we're in a git repo
    _, rc = run_git("rev-parse", "--git-dir", check=False)
    if rc != 0:
        print("Not a git repository.", file=sys.stderr)
        sys.exit(1)

    style = _Style(_decide_color(args.color))
    diff, stat = get_diff(args)
    print(summarize_diff(diff, stat, style=style, short=args.short))


if __name__ == "__main__":
    main()
