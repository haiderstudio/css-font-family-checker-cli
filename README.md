# css-font-family-checker-cli

Check font-family lists in CSS files end with a generic fallback — fail CI when one does not.

[![CI](https://github.com/haiderstudio/css-font-family-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/css-font-family-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`css_font_family_checker` reads each CSS file,
finds every `font-family` list, and reports each
one whose last item is not a generic fallback —
`serif`, `sans-serif`, `monospace`, `cursive`,
`fantasy`, or `system-ui` — with the file and the
line number. It exits 1 when any list fails, so it
can fail a CI run. A file whose lists all end with
a generic fallback exits 0.

- A font stack with no generic fallback falls back
  to the browser's default when every named font is
  missing — the page renders in an unintended face
  and the author never sees it, because their own
  machine has the named font installed. This names
  the exact line, and the fix is one word per list.
- A list is split on commas, ignoring commas inside
  quotes, so `"Times New Roman"` stays one item.
  The last item is what counts: a stack that ends
  in a generic passes, whatever comes before it.
  Quoted names count the same as bare ones, and
  the match ignores case — `SANS-SERIF` passes
  like `sans-serif`. A trailing `!important` is
  ignored.
- A `font-family` inside an `@font-face` block names
  the font being defined, it is not a stack, so
  those are skipped. A list that ends in `var(...)`
  hands the stack to a variable, so the fallback
  lives wherever the variable is defined — that is
  repo #121, css-var-checker-cli, not this one. A
  list that is only a CSS-wide keyword — `inherit`,
  `initial`, `unset`, `revert`, `revert-layer` —
  is not a font list at all. The `font:` shorthand
  is not checked either: it can carry a family, but
  reading it apart from its size and weight is a
  different job.
- A file given directly on the command line is always
  checked, whatever its name. A folder is walked for
  files ending in `.css` only, recursively by
  default (`--no-recursive` stops at the top level).
  `.git` folders are never walked, and directory
  links are never followed.
- `--json` prints the result as JSON, and `--stdin`
  checks one CSS document read from standard input.
- Declarations inside CSS comments are not
  declarations — comments are stripped before the
  scan, keeping line numbers intact.

## Who it is for

Every stylesheet author. One stack with no generic
fallback and the page renders in the browser's
default face on any machine missing the named font
— found by a visitor, not the author, because the
author's machine has the font installed. The fix is
one word once the list is found. This is the gate
that stops it at the pull request.

## What it does NOT do

- It does not check whether a `var(--name)` reference
  resolves to a defined variable. That is repo #121,
  css-var-checker-cli — variable resolution is a
  different check on the same files.
- It does not check whether a hex colour is valid.
  That is repo #122, css-color-hex-checker-cli — a
  different check on the same files.
- It does not check empty rules. That is repo #99,
  css-empty-rule-checker-cli — a different check on
  the same files.
- It does not check whether a named font is installed
  anywhere, or whether it exists in Google Fonts.
  That is a different job, done by tools such as
  google-fonts-checker.
- It never rewrites a file, and it never touches the
  network.

## How this differs

- A fresh search of GitHub on Nov 16, 2026 found 0
  results for `"css-font-family-checker-cli"` and 2
  results for `css font family checker`, both noise:
  google-fonts-checker checks whether a font family
  exists in Google Fonts and generates a link tag,
  and Onylogy-Font-Checker is a browser extension
  that shows a hovered element's font. Neither
  checks fallbacks in local CSS files.
- No rival checks font-family fallbacks in local CSS
  files with a CI exit code.

## Install

```sh
git clone https://github.com/haiderstudio/css-font-family-checker-cli.git
cd css-font-family-checker-cli
```

There is nothing else to install: Python 3.10 or newer,
standard library only, no dependencies.

## Usage

Check one CSS file:

```sh
python3 src/css_font_family_checker.py style.css
```

A file whose lists all end with a generic fallback passes:

```sh
$ python3 src/css_font_family_checker.py examples/clean.css
OK — 1 file(s) checked, every font-family list ends with a generic fallback.
```

A file with lists missing a fallback fails, with the
file and line for each one:

```sh
$ python3 src/css_font_family_checker.py examples/flagged.css
FAIL examples/flagged.css: font-family line 3 font-family list has no generic fallback (last item is helvetica)
FAIL examples/flagged.css: font-family line 6 font-family list has no generic fallback (last item is georgia)
FAIL examples/flagged.css: font-family line 9 font-family list has no generic fallback (last item is menlo)
Checked 1 file(s), 3 font-family list(s) without a generic fallback in 1 file(s).
```

Check a whole folder (`.css` files only):

```sh
$ python3 src/css_font_family_checker.py examples/
FAIL examples/flagged.css: font-family line 3 font-family list has no generic fallback (last item is helvetica)
FAIL examples/flagged.css: font-family line 6 font-family list has no generic fallback (last item is georgia)
FAIL examples/flagged.css: font-family line 9 font-family list has no generic fallback (last item is menlo)
Checked 3 file(s), 3 font-family list(s) without a generic fallback in 1 file(s).
```

Check one document from standard input:

```sh
$ printf 'body { font-family: Georgia; }\n' | python3 src/css_font_family_checker.py --stdin
FAIL <stdin>: font-family line 1 font-family list has no generic fallback (last item is georgia)
Checked 1 file(s), 1 font-family list(s) without a generic fallback in 1 file(s).
```

Machine-readable output:

```sh
$ python3 src/css_font_family_checker.py --json examples/flagged.css
{
  "files": [
    {
      "path": "examples/flagged.css",
      "findings": [
        {
          "line": 3,
          "reason": "font-family list has no generic fallback (last item is helvetica)"
        },
        {
          "line": 6,
          "reason": "font-family list has no generic fallback (last item is georgia)"
        },
        {
          "line": 9,
          "reason": "font-family list has no generic fallback (last item is menlo)"
        }
      ],
      "error": null
    }
  ],
  "checked": 1,
  "findings": 3
}
```

Exit codes: 0 when every font-family list ends with
a generic fallback, 1 when any list does not or a
file cannot be read, 2 for a usage error (a missing
path, a bad flag, or no CSS files found).

## Examples

A `font-family` inside `@font-face`, a list ending
in `var(...)`, a CSS-wide keyword, an uppercase
generic, a quoted name with a comma, and a
multi-line list all pass — `examples/edge.css`
has all of them:

```sh
$ python3 src/css_font_family_checker.py examples/edge.css
OK — 1 file(s) checked, every font-family list ends with a generic fallback.
```

A generic in the middle of the list does not count —
the LAST item must be generic:

```sh
$ printf 'body { font-family: sans-serif, Arial; }\n' | python3 src/css_font_family_checker.py --stdin
FAIL <stdin>: font-family line 1 font-family list has no generic fallback (last item is arial)
Checked 1 file(s), 1 font-family list(s) without a generic fallback in 1 file(s).
```

Run every bundled example at once with `sh
examples/run-example.sh` — the output is saved in
[examples/sample-output.md](examples/sample-output.md).

## How it is tested

```sh
python3 tests/test_css_font_family_checker.py
```

The tests cover fallback detection (a stack ending
in each of the six generics passes, a stack ending
in a named font fails with the last item named, a
single named font fails, a generic in the middle
does not count, an uppercase generic passes, a
quoted generic passes, a quoted name with a comma
stays one item, a trailing `!important` is ignored,
a multi-line declaration reports its start line, a
declaration without a semicolon before the brace,
several lists in document order, a file with no
`font-family` passes, an empty document passes, a
list ending in `var(...)` passes, every CSS-wide
keyword passes, the `font:` shorthand is not
checked, an empty value fails), skipping (an
`@font-face` block skipped, a declaration after one
still checked, a declaration in a comment skipped,
line numbers kept after a multi-line comment, a
declaration inside a media query checked, a custom
property not checked), the CLI (exit 0/1/2, folder
walking for several CSS files, nested folders,
`--no-recursive`, `--exclude`, `.git` skipped, a
direct file checked whatever its name, duplicate
paths checked once, `--json` output, `--stdin`,
bad flags, missing paths, empty folders,
`--version`, a non-UTF-8 file reported, input files
left unchanged, the tool run from another folder
and under a changed HOME), the bundled examples
(sample output compared byte-for-byte against a
fresh run, and the README-quoted outputs checked
against it), and hygiene checks (no placeholder
text, no absolute paths, no real secrets outside
the tests and examples, stdlib imports only, no
network use in the source, `.env` first in
`.gitignore`, CI file runs the test file, README
names the neighbouring repos).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The
idea of checking font fallbacks is not new, and the
scan is plain text matching — but no existing tool
does this one job, checking that every font-family
list in local CSS files ends with a generic fallback,
as a tested command-line gate with a CI exit code,
as the search above shows — and every line of code
here is original, built on nothing but Python's
standard library.
