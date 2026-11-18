#!/usr/bin/env python3
"""Tests for css_font_family_checker — stdlib unittest only.

Every CSS document in this file is made up for testing.
No real secret appears anywhere in this file.
"""

import ast
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import css_font_family_checker as checker

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src/css_font_family_checker.py"


def run_cli(argv):
    """Run main(argv), capture stdout/stderr, return (code, out, err)."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = checker.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def write(tmp, name, text, encoding="utf-8"):
    path = Path(tmp) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding=encoding)
    return str(path)


def findings_of(text):
    return checker.check_text(text)


class TestFallbackDetection(unittest.TestCase):
    def test_stack_ending_in_sans_serif_passes(self):
        self.assertEqual(
            findings_of("body { font-family: Arial, Helvetica, "
                        "sans-serif; }"),
            [])

    def test_stack_ending_in_serif_passes(self):
        self.assertEqual(
            findings_of('h1 { font-family: "Times New Roman", '
                        "Times, serif; }"),
            [])

    def test_stack_ending_in_monospace_passes(self):
        self.assertEqual(
            findings_of("code { font-family: Menlo, monospace; }"),
            [])

    def test_stack_ending_in_cursive_passes(self):
        self.assertEqual(
            findings_of("body { font-family: 'Comic Sans MS', "
                        "cursive; }"),
            [])

    def test_stack_ending_in_fantasy_passes(self):
        self.assertEqual(
            findings_of("body { font-family: Papyrus, fantasy; }"),
            [])

    def test_system_ui_alone_passes(self):
        self.assertEqual(
            findings_of("body { font-family: system-ui; }"),
            [])

    def test_stack_ending_in_named_font_fails(self):
        bad = findings_of("body { font-family: Arial, Helvetica; }")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 1)
        self.assertIn("helvetica", bad[0]["reason"])

    def test_single_named_font_fails(self):
        bad = findings_of("h1 { font-family: Georgia; }")
        self.assertEqual(len(bad), 1)
        self.assertIn("georgia", bad[0]["reason"])

    def test_generic_in_the_middle_does_not_count(self):
        bad = findings_of(
            "body { font-family: sans-serif, Arial; }")
        self.assertEqual(len(bad), 1)
        self.assertIn("arial", bad[0]["reason"])

    def test_uppercase_generic_passes(self):
        self.assertEqual(
            findings_of("body { font-family: ARIAL, SANS-SERIF; }"),
            [])

    def test_quoted_generic_passes(self):
        self.assertEqual(
            findings_of('body { font-family: Arial, "sans-serif"; }'),
            [])

    def test_quoted_name_with_comma_stays_one_item(self):
        self.assertEqual(
            findings_of('body { font-family: "Times, New Roman", '
                        "serif; }"),
            [])

    def test_quoted_name_with_comma_and_no_fallback_fails(self):
        bad = findings_of(
            'body { font-family: "Times, New Roman", Georgia; }')
        self.assertEqual(len(bad), 1)
        self.assertIn("georgia", bad[0]["reason"])

    def test_trailing_important_ignored(self):
        self.assertEqual(
            findings_of("body { font-family: Arial, sans-serif "
                        "!important; }"),
            [])
        bad = findings_of("body { font-family: Arial !important; }")
        self.assertEqual(len(bad), 1)
        self.assertIn("arial", bad[0]["reason"])

    def test_multiline_declaration_reports_its_start_line(self):
        text = ("body {\n"
                "  font-family:\n"
                "    Arial,\n"
                "    Helvetica;\n"
                "}\n")
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 2)

    def test_declaration_without_semicolon_before_brace(self):
        bad = findings_of("body { font-family: Arial }")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 1)
        self.assertEqual(
            findings_of("body { font-family: Arial, serif }"), [])

    def test_multiple_declarations_in_document_order(self):
        text = ("body { font-family: Arial, sans-serif; }\n"
                "h1 { font-family: Georgia; }\n"
                "p { font-family: Verdana, sans-serif; }\n"
                "code { font-family: Menlo; }\n")
        bad = findings_of(text)
        self.assertEqual([f["line"] for f in bad], [2, 4])

    def test_file_with_no_font_family_passes(self):
        self.assertEqual(
            findings_of("body { color: red; margin: 0; }"), [])

    def test_empty_document_passes(self):
        self.assertEqual(findings_of(""), [])

    def test_var_last_item_passes(self):
        self.assertEqual(
            findings_of("body { font-family: var(--font-body); }"),
            [])
        self.assertEqual(
            findings_of("body { font-family: Arial, "
                        "var(--font-fallback); }"),
            [])

    def test_css_wide_keywords_pass(self):
        for keyword in ("inherit", "initial", "unset", "revert",
                        "revert-layer"):
            self.assertEqual(
                findings_of("body { font-family: %s; }" % keyword),
                [],
                keyword)

    def test_font_shorthand_not_checked(self):
        self.assertEqual(
            findings_of("body { font: italic bold 16px/1.5 Georgia; }"),
            [])

    def test_empty_value_fails(self):
        bad = findings_of("body { font-family: ; }")
        self.assertEqual(len(bad), 1)
        self.assertIn("empty", bad[0]["reason"])


class TestSkipping(unittest.TestCase):
    def test_font_face_block_skipped(self):
        text = ('@font-face {\n'
                '  font-family: "MyFont";\n'
                '  src: url("myfont.woff2") format("woff2");\n'
                '}\n')
        self.assertEqual(findings_of(text), [])

    def test_declaration_after_font_face_still_checked(self):
        text = ('@font-face {\n'
                '  font-family: "MyFont";\n'
                '  src: url("myfont.woff2") format("woff2");\n'
                '}\n'
                'body { font-family: MyFont; }\n')
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 5)

    def test_declaration_in_comment_skipped(self):
        text = ("/* font-family: Arial; */\n"
                "body { font-family: Arial, sans-serif; }\n")
        self.assertEqual(findings_of(text), [])

    def test_multiline_comment_skipped_line_numbers_kept(self):
        text = ("/*\n"
                "font-family: Arial;\n"
                "*/\n"
                "body { font-family: Georgia; }\n")
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 4)

    def test_declaration_inside_media_query_checked(self):
        text = ("@media (max-width: 600px) {\n"
                "  body { font-family: Arial; }\n"
                "}\n")
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 2)

    def test_custom_property_not_checked(self):
        self.assertEqual(
            findings_of(":root { --font-body: Arial; }"), [])


class TestCLI(unittest.TestCase):
    def test_clean_file_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "style.css",
                         "body { font-family: Arial, sans-serif; }\n")
            code, out, err = run_cli([path])
            self.assertEqual(code, 0)
            self.assertIn("generic fallback", out)
            self.assertEqual(err, "")

    def test_flagged_file_exit_1_with_file_and_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "style.css",
                         "body { font-family: Arial; }\n")
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("line 1", out)
            self.assertIn("no generic fallback", out)
            self.assertIn(path, out)

    def test_folder_walk_finds_css_files_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.css",
                  "body { font-family: Arial, sans-serif; }\n")
            write(tmp, "b.css", "body { font-family: Georgia; }\n")
            write(tmp, "notes.txt", "body { font-family: Georgia; }\n")
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s)", out)
            self.assertIn("b.css", out)
            self.assertNotIn("notes.txt", out)

    def test_folder_walk_skips_nested_with_no_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.css",
                  "body { font-family: Arial, sans-serif; }\n")
            write(tmp, "sub/b.css", "body { font-family: Georgia; }\n")
            code, out, err = run_cli([tmp, "--no-recursive"])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s)", out)

    def test_exclude_skips_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.css",
                  "body { font-family: Arial, sans-serif; }\n")
            write(tmp, "b.css", "body { font-family: Georgia; }\n")
            code, out, err = run_cli([tmp, "--exclude", "b.css"])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_git_folder_skipped_in_walk(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.css",
                  "body { font-family: Arial, sans-serif; }\n")
            write(tmp, ".git/b.css", "body { font-family: Georgia; }\n")
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_direct_file_checked_whatever_its_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "theme.txt",
                         "body { font-family: Georgia; }\n")
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("theme.txt", out)

    def test_duplicate_paths_checked_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.css",
                         "body { font-family: Arial, sans-serif; }\n")
            code, out, err = run_cli([path, path])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.css",
                         "body { font-family: Georgia; }\n")
            code, out, err = run_cli(["--json", path])
            self.assertEqual(code, 1)
            data = json.loads(out)
            self.assertEqual(data["checked"], 1)
            self.assertEqual(data["findings"], 1)
            self.assertEqual(data["files"][0]["path"], path)
            self.assertEqual(
                data["files"][0]["findings"][0]["line"], 1)
            self.assertIn("no generic fallback",
                          data["files"][0]["findings"][0]["reason"])
            self.assertIsNone(data["files"][0]["error"])

    def test_stdin_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(SRC), "--stdin"],
                input="body { font-family: Arial, sans-serif; }\n",
                cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("generic fallback", result.stdout)

    def test_stdin_dirty(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(SRC), "--stdin"],
                input="body { font-family: Georgia; }\n",
                cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL <stdin>: font-family line 1",
                          result.stdout)

    def test_stdin_with_paths_is_usage_error(self):
        code, out, err = run_cli(["--stdin", "style.css"])
        self.assertEqual(code, 2)

    def test_no_paths_is_usage_error(self):
        code, out, err = run_cli([])
        self.assertEqual(code, 2)

    def test_missing_path_exit_2(self):
        code, out, err = run_cli(["/nonexistent/path/xyz"])
        self.assertEqual(code, 2)
        self.assertIn("no such file or folder", err)

    def test_empty_folder_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 2)
            self.assertIn("no CSS files found", err)

    def test_bad_flag_exit_2(self):
        code, out, err = run_cli(["--nope"])
        self.assertEqual(code, 2)

    def test_version(self):
        code, out, err = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("css_font_family_checker 1.0.0", out)

    def test_non_utf8_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.css", b"\xff\xfe body {}\n")
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("not valid UTF-8", out)

    def test_input_files_left_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.css",
                         "body { font-family: Georgia; }\n")
            before = Path(path).read_text()
            run_cli([path])
            self.assertEqual(Path(path).read_text(), before)

    def test_cli_runs_from_another_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.css",
                  "body { font-family: Arial, sans-serif; }\n")
            result = subprocess.run(
                [sys.executable, str(SRC), "a.css"],
                cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("generic fallback", result.stdout)

    def test_cli_runs_under_fake_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.css",
                         "body { font-family: Arial, sans-serif; }\n")
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                code, out, err = run_cli([path])
            finally:
                if old_home is None:
                    del os.environ["HOME"]
                else:
                    os.environ["HOME"] = old_home
            self.assertEqual(code, 0)


class TestExamples(unittest.TestCase):
    def test_run_example_output_matches_sample(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        expected = (REPO / "examples/sample-output.md").read_text()
        self.assertEqual(result.stdout, expected)

    def test_readme_quotes_match_real_runs(self):
        readme = (REPO / "README.md").read_text()
        clean = subprocess.run(
            [sys.executable, "src/css_font_family_checker.py",
             "examples/clean.css"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(clean.returncode, 0)
        self.assertIn(clean.stdout.strip(), readme)
        flagged = subprocess.run(
            [sys.executable, "src/css_font_family_checker.py",
             "examples/flagged.css"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(flagged.returncode, 1)
        self.assertIn(flagged.stdout.strip(), readme)
        folder = subprocess.run(
            [sys.executable, "src/css_font_family_checker.py",
             "examples/"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(folder.returncode, 1)
        self.assertIn("Checked 3 file(s), 3 font-family list(s) "
                      "without a generic fallback in 1 file(s).",
                      folder.stdout)
        self.assertIn("Checked 3 file(s), 3 font-family list(s) "
                      "without a generic fallback in 1 file(s).",
                      readme)
        edge = subprocess.run(
            [sys.executable, "src/css_font_family_checker.py",
             "examples/edge.css"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(edge.returncode, 0)
        self.assertIn(edge.stdout.strip(), readme)
        js = subprocess.run(
            [sys.executable, "src/css_font_family_checker.py",
             "--json", "examples/flagged.css"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(js.returncode, 1)
        self.assertIn(js.stdout.strip(), readme)


class TestHygiene(unittest.TestCase):
    def _repo_files(self, skip_tests=True, skip_examples=True):
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "__pycache__")
                       and not (skip_tests and d == "tests")
                       and not (skip_examples and d == "examples")]
            for name in files:
                if name.endswith(".pyc"):
                    continue
                yield Path(root) / name

    def test_no_placeholder_text(self):
        banned = ["TODO", "coming soon", "lorem", "FIXME", "XXX"]
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for word in banned:
                if word in text:
                    hits.append("%s: %s" % (path.name, word))
        self.assertEqual(hits, [])

    def test_no_absolute_paths(self):
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for marker in ("/home/", "/Users/", "C:\\"):
                if marker in text:
                    hits.append("%s: %s" % (path.name, marker))
        self.assertEqual(hits, [])

    def test_no_real_secrets_outside_tests_and_examples(self):
        # The source holds no key values at all; the tests
        # and examples hold fake values only, so they are
        # excluded from this scan.
        patterns = [
            re.compile(r"AKIA[0-9A-Z]{16}"),
            re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
            re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
            re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
            re.compile(r"AIza[0-9A-Za-z_-]{35}"),
            re.compile(r"[rs]k_(?:live|test)_[A-Za-z0-9]{16,}"),
            re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
            re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ"),
        ]
        hits = []
        for path in self._repo_files():
            text = path.read_text(errors="ignore")
            for pattern in patterns:
                if pattern.search(text):
                    hits.append("%s: %s" % (path.name, pattern.pattern))
        self.assertEqual(hits, [])

    def test_stdlib_imports_only(self):
        stdlib = set(sys.stdlib_module_names)
        for target in (REPO / "src/css_font_family_checker.py",
                       REPO / "tests/test_css_font_family_checker.py"):
            tree = ast.parse(target.read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0]
                                    for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(
                imported - stdlib - {"css_font_family_checker"},
                (target.name, imported))
            self.assertNotIn("yaml", imported)

    def test_no_network_use_in_src(self):
        src = (REPO / "src/css_font_family_checker.py").read_text()
        for marker in ("urllib.request", "requests", "socket",
                       "http.client", "urlopen", "urlretrieve"):
            self.assertNotIn(marker, src, marker)

    def test_gitignore_lists_env_first(self):
        lines = (REPO / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_ci_runs_this_test_file(self):
        ci = (REPO / ".github/workflows/ci.yml").read_text()
        self.assertIn("tests/test_css_font_family_checker.py", ci)
        self.assertIn("ubuntu-latest", ci)
        self.assertIn("3.12", ci)
        self.assertIn("actions/checkout", ci)
        self.assertIn("setup-python", ci)
        self.assertIn("push", ci)
        self.assertIn("pull_request", ci)

    def test_readme_names_the_neighbouring_repos(self):
        readme = (REPO / "README.md").read_text()
        self.assertIn("css-empty-rule-checker-cli", readme)
        self.assertIn("css-var-checker-cli", readme)


if __name__ == "__main__":
    unittest.main()
