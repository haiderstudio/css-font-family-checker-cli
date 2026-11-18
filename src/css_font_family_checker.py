#!/usr/bin/env python3
"""Check font-family lists in CSS files end with a generic fallback.

Run: python3 src/css_font_family_checker.py style.css
     python3 src/css_font_family_checker.py styles/
     python3 src/css_font_family_checker.py --stdin < style.css

A font stack with no generic fallback falls back to
the browser's default when every named font is
missing — the page renders in an unintended face
and the author never sees it, because their own
machine has the named font installed. This tool
reads each CSS file, finds every font-family list,
and reports each one whose last item is not a
generic fallback — serif, sans-serif, monospace,
cursive, fantasy, or system-ui — with the file and
the line number. It exits 1 when any list fails,
so it can fail a CI run. A file whose lists all end
with a generic fallback exits 0.

A list is split on commas, ignoring commas inside
quotes, so "Times New Roman" stays one item. The
last item is what counts: a stack that ends in a
generic passes, whatever comes before it. Quoted
names count the same as bare ones, and the match
ignores case — SANS-SERIF passes like sans-serif.
A trailing !important is ignored.

Three things are not flagged, and the README says
why. A font-family inside an @font-face block
names the font being defined, it is not a stack,
so those are skipped. A list that ends in var(...)
hands the stack to a variable, so the fallback
lives wherever the variable is defined — checking
that is the job of css-var-checker-cli, not this
one. A list that is only a CSS-wide keyword —
inherit, initial, unset, revert, revert-layer —
is not a font list at all. The font: shorthand is
not checked either: it can carry a family, but
reading it apart from its size and weight is a
different job.

A file given directly on the command line is always
checked, whatever its name. A folder is walked for
files ending in .css only, recursively by default
(--no-recursive stops at the top level). .git
folders are never walked, and directory links are
never followed.

Declarations inside CSS comments are not
declarations — comments are stripped before the
scan, keeping line numbers intact.

It never rewrites a file, never touches the network,
and reads only the files and folders you point it at.
"""

import argparse
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

__version__ = "1.0.0"

CSS_SUFFIXES = (".css",)

GENERIC_FALLBACKS = ("serif", "sans-serif", "monospace",
                     "cursive", "fantasy", "system-ui")

CSS_WIDE_KEYWORDS = ("inherit", "initial", "unset",
                     "revert", "revert-layer")

DECLARATION_RE = re.compile(
    r"font-family\s*:\s*([^;{}]+?)(?:;|})",
    re.IGNORECASE | re.DOTALL)

COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

FONT_FACE_RE = re.compile(r"@font-face\s*\{", re.IGNORECASE)


def _blank_out(text, start, end):
    """Replace a span with spaces, keeping newlines."""
    return "".join("\n" if ch == "\n" else " "
                   for ch in text[start:end])


def _strip_comments(text):
    """Remove CSS comments, keeping line numbers intact."""
    return COMMENT_RE.sub(
        lambda match: _blank_out(text, match.start(), match.end()),
        text)


def _strip_font_face_blocks(text):
    """Blank out @font-face blocks, keeping line numbers.

    A font-family inside @font-face names the font
    being defined, it is not a stack, so it must not
    be checked. Blocks are matched by brace depth,
    so a nested rule inside one is handled too.
    """
    out = list(text)
    for match in FONT_FACE_RE.finditer(text):
        depth = 0
        index = match.end() - 1
        while index < len(text):
            char = text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        end = min(index + 1, len(text))
        blanked = _blank_out(text, match.start(), end)
        out[match.start():end] = list(blanked)
    return "".join(out)


def _split_list(value):
    """Split a font-family value on commas, ignoring quoted ones."""
    items = []
    current = []
    quote = None
    for char in value:
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
            current.append(char)
        elif char == ",":
            items.append("".join(current))
            current = []
        else:
            current.append(char)
    items.append("".join(current))
    return items


def _last_item(value):
    """The final item of a font-family list, cleaned up."""
    items = _split_list(value)
    last = items[-1].strip() if items else ""
    last = re.sub(r"\s*!important\s*$", "", last,
                  flags=re.IGNORECASE)
    last = last.strip().strip("'\"").strip()
    return last.lower()


def check_text(text):
    """Check one document's text.

    Returns a list of findings, each {"line": int,
    "reason": str}, in document order.
    """
    cleaned = _strip_font_face_blocks(_strip_comments(text))
    findings = []
    for match in DECLARATION_RE.finditer(cleaned):
        last = _last_item(match.group(1))
        if last in GENERIC_FALLBACKS:
            continue
        if last in CSS_WIDE_KEYWORDS:
            continue
        if last.startswith("var("):
            continue
        line = cleaned.count("\n", 0, match.start()) + 1
        findings.append({
            "line": line,
            "reason": "font-family list has no generic fallback "
                      "(last item is %s)" % (last or "empty"),
        })
    return findings


def check_file(path):
    """Check one file. Returns (findings, error)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], "not valid UTF-8"
    except OSError as exc:
        return [], str(exc)
    try:
        return check_text(text), None
    except Exception as exc:  # malformed text the scan rejects
        return [], "could not be scanned: %s" % exc


def _is_css_file(path):
    return Path(path).name.lower().endswith(CSS_SUFFIXES)


def collect_files(paths, recursive=True, exclude=None):
    """Expand CLI paths into a sorted list of CSS files.

    A file given directly is always checked, whatever its
    name. A folder is walked for files ending in .css
    only. .git folders are never walked, and directory
    links are never followed.
    """
    exclude = exclude or []
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            found.append(str(path))
        elif path.is_dir():
            for dirpath, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = [
                    d for d in dirs
                    if d != ".git"
                    and not any(fnmatch.fnmatch(d, pat) for pat in exclude)
                ]
                for name in files:
                    candidate = Path(dirpath) / name
                    if not _is_css_file(candidate):
                        continue
                    if any(
                        fnmatch.fnmatch(str(candidate), pat)
                        or fnmatch.fnmatch(name, pat)
                        for pat in exclude
                    ):
                        continue
                    found.append(str(candidate))
                if not recursive:
                    break
        else:
            raise FileNotFoundError("no such file or folder: %s" % raw)
    seen = set()
    unique = []
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return sorted(unique)


def format_finding(path, finding):
    """One human-readable line for one failing list."""
    return ("FAIL %s: font-family line %d %s"
            % (path, finding["line"], finding["reason"]))


def run(paths, recursive=True, exclude=None, as_json=False):
    """Check paths, print the report, return the exit code."""
    try:
        files = collect_files(paths, recursive=recursive, exclude=exclude)
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if not files:
        print("error: no CSS files found", file=sys.stderr)
        return 2
    results = []
    findings = 0
    files_with_findings = 0
    for path in files:
        bad, error = check_file(path)
        count = len(bad) + (1 if error else 0)
        if count:
            findings += count
            files_with_findings += 1
        results.append({"path": path, "findings": bad, "error": error})
    if as_json:
        print(json.dumps(
            {"files": results, "checked": len(files),
             "findings": findings},
            indent=2))
    else:
        for result in results:
            if result["error"]:
                print("FAIL %s: %s" % (result["path"], result["error"]))
            for finding in result["findings"]:
                print(format_finding(result["path"], finding))
        if findings:
            print("Checked %d file(s), %d font-family list(s) "
                  "without a generic fallback in %d file(s)."
                  % (len(files), findings, files_with_findings))
        else:
            print("OK — %d file(s) checked, every font-family "
                  "list ends with a generic fallback." % len(files))
    return 1 if findings else 0


def run_stdin(as_json=False):
    """Check one CSS document read from standard input."""
    text = sys.stdin.read()
    bad = check_text(text)
    findings = len(bad)
    if as_json:
        print(json.dumps(
            {"files": [{"path": "<stdin>", "findings": bad,
                        "error": None}],
             "checked": 1, "findings": findings},
            indent=2))
    else:
        for finding in bad:
            print(format_finding("<stdin>", finding))
        if findings:
            print("Checked 1 file(s), %d font-family list(s) "
                  "without a generic fallback in 1 file(s)."
                  % findings)
        else:
            print("OK — 1 file(s) checked, every font-family "
                  "list ends with a generic fallback.")
    return 1 if findings else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="css_font_family_checker",
        description="Check font-family lists in CSS files end "
                    "with a generic fallback, fail CI when one "
                    "does not.")
    parser.add_argument("paths", nargs="*",
                        help="CSS files or folders to walk")
    parser.add_argument("--no-recursive", action="store_true",
                        help="do not walk into subfolders")
    parser.add_argument("--exclude", action="append", default=[],
                        help="skip files or folders matching this pattern "
                             "(repeatable)")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    parser.add_argument("--stdin", action="store_true",
                        help="check one CSS document from standard input")
    parser.add_argument("--version", action="version",
                        version="%(prog)s " + __version__)
    args = parser.parse_args(argv)
    if args.stdin:
        if args.paths:
            parser.error("--stdin takes no file or folder arguments")
        return run_stdin(as_json=args.json)
    if not args.paths:
        parser.error("give at least one CSS file or folder")
    return run(args.paths, recursive=not args.no_recursive,
               exclude=args.exclude, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
