#!/usr/bin/env python3
"""Compile and exercise RainbowGrades only in disposable synthetic working directories."""

import argparse
import csv
import itertools
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from html.parser import HTMLParser

REPO = Path(__file__).resolve().parents[1]
FIELDS = ("linkedin_username", "github_username", "personal_webpage")
LABELS = ("LinkedIn Username", "GitHub Username", "Personal Webpage")
CONTACTS = ("alpha-linkedin", "alpha-github", "https://example.com/alpha")
PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument("--json-include", required=True, type=Path, help="Existing nlohmann/json v3.12.0 include directory")
PARSER.add_argument("--artifacts", type=Path, help="New directory in which to retain build logs and all synthetic outputs")
PARSER.add_argument("--baseline-executable", type=Path, help="Optional unmodified baseline binary for CSV comparisons")
PARSER.add_argument("--cxx", default=os.environ.get("CXX", "clang++"))


class ReportHTML(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag == "td":
            self.cell = {"text": "", "links": []}
        elif tag == "a" and self.cell is not None:
            self.cell["links"].append(dict(attrs))

    def handle_data(self, text):
        if self.cell is not None:
            self.cell["text"] += text

    def handle_endtag(self, tag):
        if tag == "td" and self.row is not None:
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def write_fixture(directory, contacts, flags, aliases=False):
    (directory / "raw_data/all_grades").mkdir(parents=True)
    for folder in ("individual_summary_html", "all_students_summary_html", "all_students_summary_csv"):
        (directory / folder).mkdir()
    customization = {
        "gradeables": [{"type": "homework", "count": 1, "percent": 1.0, "ids": [{"id": "demo_hw", "max": 10.0}]}],
        "benchmark_percent": {"lowest_a-": 0.9, "lowest_b-": 0.8, "lowest_c-": 0.7, "lowest_d": 0.6},
        "section": {"1": "Synthetic section"},
        "display": ["grade_summary", "grade_details", *flags],
        "display_benchmark": [], "benchmark_color": {}, "messages": [], "use": {},
    }
    (directory / "customization_no_comments.json").write_text(json.dumps(customization), encoding="utf-8")
    # The normal generator expects this file even in a standalone synthetic run.
    (directory / "RG_version.json").write_text(json.dumps({
        "installed_commit_rg": "synthetic-test", "short_installed_commit_rg": "synthetic", "most_recent_git_tag_rg": "test",
    }), encoding="utf-8")
    (directory / "raw_data/base_url.json").write_text(json.dumps({
        "base_url": "https://submitty.example.test/", "term": "f26", "course": "synthetic",
    }), encoding="utf-8")
    for user_id, score in (("alpha", 8.0), ("bravo", 6.0)):
        student = {
            "user_id": user_id, "user_numeric_id": "100" if user_id == "alpha" else "101",
            "legal_given_name": user_id.capitalize(), "legal_family_name": "Student",
            "registration_section": "1", "registration_type": "graded", "last_update": "synthetic fixture",
            "homework": [{"id": "demo_hw", "name": "Synthetic homework", "score": score,
                          "status": "Good", "gradeable_type": "Numeric"}],
        }
        if aliases:
            student["legal_first_name"] = student.pop("legal_given_name")
            student["legal_last_name"] = student.pop("legal_family_name")
        if contacts is not None:
            student.update(contacts if user_id == "alpha" else dict(zip(FIELDS, (
                "bravo-linkedin", "bravo-github", "https://example.com/bravo"))))
        (directory / "raw_data/all_grades" / f"{user_id}_summary.json").write_text(json.dumps(student), encoding="utf-8")


def compile_program(command, log):
    print("COMPILE:", shlex.join(map(str, command)), flush=True)
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log.write_text(result.stdout, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"Compilation failed; see {log}\n{result.stdout}")


class ContactInfoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.counter = 0
        cls.binary = ARTIFACTS / "process_grades.out"
        compile_program([ARGS.cxx, "-std=c++11", "-Wall", "-Wextra", f"-I{ARGS.json_include}",
                         *sorted(REPO.glob("*.cpp")), "-o", cls.binary], ARTIFACTS / "compile.log")
        cls.probe = ARTIFACTS / "table_cell_test.out"
        compile_program([ARGS.cxx, "-std=c++11", "-Wall", "-Wextra", f"-I{REPO}",
                         REPO / "tests/table_cell_test.cpp", REPO / "table.cpp", "-o", cls.probe], ARTIFACTS / "table-compile.log")
        reference = cls.run_fixture("reference-old-json", None, ())
        if reference[1].returncode:
            raise RuntimeError(reference[1].stdout)
        cls.reference = reference[0]

    @classmethod
    def run_fixture(cls, name, contacts, flags, mode="by_overall", binary=None, aliases=False):
        cls.counter += 1
        directory = ARTIFACTS / f"{cls.counter:03d}-{name}"
        directory.mkdir()
        write_fixture(directory, contacts, flags, aliases)
        result = subprocess.run([str(binary or cls.binary), mode], cwd=directory,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=20)
        (directory / "run.log").write_text(result.stdout, encoding="utf-8")
        return directory, result

    def successful_report(self, contacts, flags=FIELDS, mode="by_overall", aliases=False):
        directory, result = self.run_fixture(self.id().split(".")[-1], contacts, flags, mode, aliases=aliases)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("UNKNOWN TOKEN", result.stdout)
        self.assertNotIn("OOPS", result.stdout)
        for filename in ("output.html", "output.csv"):
            self.assertTrue((directory / filename).is_file(), result.stdout)
            self.assertGreater((directory / filename).stat().st_size, 0)
        instructor = (directory / "output.html").read_text(encoding="utf-8")
        self.assertIn("</table>", instructor)
        self.assertNotIn(b"\0", (directory / "output.csv").read_bytes())
        with (directory / "output.csv").open(newline="", encoding="utf-8") as file:
            rows = list(csv.reader(file))
        self.assertEqual(rows[0][-3:], list(LABELS))
        self.assertTrue(all(len(row) == len(rows[0]) for row in rows))
        students = {row[0]: row for row in rows if row[0] in ("alpha", "bravo")}
        self.assertEqual(set(students), {"alpha", "bravo"})
        score_index = rows[0].index("Synthetic homework")
        self.assertEqual(students["alpha"][score_index], "8.0")
        self.assertEqual(students["bravo"][score_index], "6.0")
        for row in rows[1:]:
            if row[0] not in students:
                self.assertEqual(row[-3:], ["", "", ""])
        # Byte equality against old JSON catches disclosure through any individual
        # projection, including the second (CSV-mode) generation pass and benchmarks.
        for user_id in ("alpha", "bravo"):
            name = f"individual_summary_html/{user_id}_summary.html"
            self.assertEqual((directory / name).read_bytes(), (self.reference / name).read_bytes())
        report = ReportHTML(instructor)
        headers = [cell["text"] for cell in report.rows[0]]
        self.assertEqual(headers[-len(flags):] if flags else [], [LABELS[FIELDS.index(field)] for field in FIELDS if field in flags])
        benchmarks = ("AVERAGE", "STDDEV", "PERFECT", "LOWEST A-", "LOWEST B-", "LOWEST C-", "LOWEST D")
        benchmark_rows = [row for row in report.rows if row and row[0]["text"] in benchmarks]
        self.assertCountEqual([row[0]["text"] for row in benchmark_rows], benchmarks)
        for label, field in zip(LABELS, FIELDS):
            self.assertEqual(label in headers, field in flags)
            if field in flags:
                index = headers.index(label)
                for row in benchmark_rows:
                    with self.subTest(benchmark=row[0]["text"], field=field):
                        self.assertEqual(row[index]["text"], "")
                        self.assertEqual(row[index]["links"], [])
        return directory, rows, students, report

    def test_old_json_and_existing_aliases(self):
        for aliases in (False, True):
            _, _, students, _ = self.successful_report(None, aliases=aliases)
            self.assertEqual(students["alpha"][-3:], ["", "", ""])

    def test_baseline_grade_columns_unchanged(self):
        if not ARGS.baseline_executable:
            self.skipTest("--baseline-executable was not provided")
        directory, result = self.run_fixture("baseline-control", None, (), binary=ARGS.baseline_executable)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((directory / "output.html").is_file())
        with (directory / "output.csv").open(newline="", encoding="utf-8") as file:
            baseline_rows = list(csv.reader(file))
        _, rows, _, _ = self.successful_report(dict(zip(FIELDS, CONTACTS)), flags=())
        self.assertEqual([row[:-3] for row in rows], baseline_rows)

    def test_negative_numeric_cells_and_visibility(self):
        result = subprocess.run([str(self.probe)], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout, "4 table-cell checks passed\n")

    def test_baseline_reproduces_contact_rejection(self):
        if not ARGS.baseline_executable:
            self.skipTest("--baseline-executable was not provided")
        directory, result = self.run_fixture("baseline-new-json", dict(zip(FIELDS, CONTACTS)), (), binary=ARGS.baseline_executable)
        self.assertEqual(result.returncode, 0)
        self.assertIn("UNKNOWN TOKEN Y 'github_username'", result.stdout)
        self.assertFalse((directory / "output.html").exists())
        self.assertFalse((directory / "output.csv").exists())

    def test_mixed_missing_null_empty(self):
        _, _, students, _ = self.successful_report({FIELDS[1]: None, FIELDS[2]: ""})
        self.assertEqual(students["alpha"][-3:], ["", "", ""])

    def test_representative_sort_modes(self):
        for mode in ("by_section", "by_name", "by_hw"):
            self.successful_report(dict(zip(FIELDS, CONTACTS)), mode=mode)


def add_test(name, function):
    setattr(ContactInfoTests, f"test_{name}", function)


def flag_test(enabled):
    def test(self):
        flags = tuple(field for field, show in zip(FIELDS, enabled) if show)
        _, _, students, report = self.successful_report(dict(zip(FIELDS, CONTACTS)), flags)
        self.assertEqual(students["alpha"][-3:], list(CONTACTS))
        row = next(row for row in report.rows if row[0]["text"] == "alpha")
        cells = row[-len(flags):] if flags else []
        for cell, field in zip(cells, flags):
            index = FIELDS.index(field)
            self.assertEqual(cell["text"], CONTACTS[index])
            self.assertEqual(len(cell["links"]), 1)
            link = cell["links"][0]
            self.assertEqual(link["target"], "_blank")
            self.assertEqual(set(link["rel"].split()), {"noopener", "noreferrer"})
    return test


for enabled in itertools.product((False, True), repeat=3):
    add_test("display_" + "".join(str(int(value)) for value in enabled), flag_test(enabled))


def wrong_type_test(field, value):
    def test(self):
        directory, result = self.run_fixture(self.id().split(".")[-1], {field: value}, ())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(field, result.stdout)
        self.assertIn("alpha_summary.json", result.stdout)
        self.assertIn("must be a string or null", result.stdout)
        self.assertNotIn("UNKNOWN TOKEN", result.stdout)
        self.assertFalse((directory / "output.html").exists())
        self.assertFalse((directory / "output.csv").exists())
    return test


for field in FIELDS:
    for kind, value in (("bool", True), ("int", 7), ("float", 2.5), ("array", []), ("object", {})):
        add_test(f"wrong_type_{field}_{kind}", wrong_type_test(field, value))


def value_test(field, value, expected_link=None, csv_value=None):
    def test(self):
        contacts = dict(zip(FIELDS, CONTACTS))
        contacts[field] = value
        _, _, students, report = self.successful_report(contacts)
        index = FIELDS.index(field)
        self.assertEqual(students["alpha"][-3 + index], value if csv_value is None else csv_value)
        row = next(row for row in report.rows if row[0]["text"] == "alpha")
        cell = row[-3 + index]
        self.assertEqual(cell["text"], "" if value is None else value.replace("\r\n", "\n").replace("\r", "\n"))
        self.assertEqual([link["href"] for link in cell["links"]], [] if expected_link is None else [expected_link])
    return test


for field in FIELDS:
    for kind, value in (("empty", ""), ("null", None)):
        add_test(f"optional_{field}_{kind}", value_test(field, value, csv_value=""))

LINK_CASES = [
    ("github_min", FIELDS[1], "a", "https://github.com/a"),
    ("github_max", FIELDS[1], "a" * 39, "https://github.com/" + "a" * 39),
    ("github_hyphen", FIELDS[1], "student-code", "https://github.com/student-code"),
    ("github_double_hyphen", FIELDS[1], "bad--name", None),
    ("github_leading_hyphen", FIELDS[1], "-bad", None),
    ("github_long", FIELDS[1], "a" * 40, None),
    ("linkedin_min", FIELDS[0], "abc", "https://www.linkedin.com/in/abc"),
    ("linkedin_max", FIELDS[0], "a" * 100, "https://www.linkedin.com/in/" + "a" * 100),
    ("linkedin_internal_hyphens", FIELDS[0], "student--name", "https://www.linkedin.com/in/student--name"),
    ("linkedin_short", FIELDS[0], "ab", None),
    ("linkedin_long", FIELDS[0], "a" * 101, None),
    ("linkedin_trailing_hyphen", FIELDS[0], "bad-", None),
    ("github_hostile", FIELDS[1], '\"><script data-contact-attack>alert(1)</script>&\'', None),
    ("linkedin_hostile", FIELDS[0], 'a/\" onclick=\"alert(1)', None),
]
for name, value in (
    ("https", "https://example.com/portfolio"), ("http", "http://example.com/portfolio"),
    ("mixed_scheme", "HTTPS://example.com/?a=1&b=2"), ("port", "https://example.com:443/"),
    ("ipv6", "https://[::1]:8080/path"), ("ipv4", "https://127.0.0.1/path"),
    ("escaped_path", "https://example.com/%22portfolio%22?q=a,b&x=2"),
):
    LINK_CASES.append(("web_" + name, FIELDS[2], value, value))
for name, value in (
    ("javascript", "javascript:alert(1)"), ("data", "data:text/html,<script>alert(1)</script>"),
    ("relative", "//example.com/path"), ("empty_host", "https:///path"),
    ("credentials", "https://user:pass@example.com/"), ("bad_port", "https://example.com:abc/"),
    ("big_port", "https://example.com:65536/"), ("bad_percent", "https://example.com/%zz"),
    ("space", "https://example.com/a b"), ("backslash", "https://example.com\\@evil.example/"),
    ("quote", 'https://example.com/\" onmouseover=\"alert(1)'),
    ("bad_host", "https://bad_host.example/"), ("double_dot", "https://example.com../"),
    ("bad_ipv6", "https://[::not-an-ip]/"), ("long", "https://example.com/" + "x" * 2048),
):
    LINK_CASES.append(("web_" + name, FIELDS[2], value, None))
for name, field, value, link in LINK_CASES:
    add_test(name, value_test(field, value, link, "'" + value if value.startswith("-") else value))

for index, value in enumerate((
    "https://example.com/?a=1,b=2", 'text,"quoted"\r\nnext', "a&b<c>d\"e'f", "'=already-literal",
)):
    add_test(f"csv_literal_{index}", value_test(FIELDS[2], value, value if index == 0 else None))
for index, value in enumerate((
    "=1+1", "+1", "-1", "@SUM(1,2)", " =1", "\t=1", "\r=1", "\n=1", "\x00=1", "\x1f=1", "\x7f=1",
    "\ufeff=1", "\u00a0=1", "\u2003=1", "\u202f=1", "\u3000=1",
)):
    add_test(f"csv_formula_{index}", value_test(FIELDS[2], value, csv_value="'" + value.replace("\0", "\\0")))

for field in FIELDS:
    for kind, value, expected in (
        ("only", "\0", "'\\0"),
        ("embedded", 'before\0\0,\0"after"\r\nend\0', 'before\\0\\0,\\0"after"\r\nend\\0'),
        ("formula", "=\0+1", "'=\\0+1"),
        ("literal", r"\0=1", r"\0=1"),
    ):
        add_test(f"csv_nul_{field}_{kind}", value_test(field, value, csv_value=expected))


if __name__ == "__main__":
    ARGS, remaining = PARSER.parse_known_args()
    ARGS.json_include = ARGS.json_include.resolve()
    if not (ARGS.json_include / "nlohmann/json.hpp").is_file():
        PARSER.error("--json-include must contain an existing nlohmann/json.hpp; this runner never downloads dependencies")
    if ARGS.baseline_executable:
        ARGS.baseline_executable = ARGS.baseline_executable.resolve()
    if ARGS.artifacts:
        ARTIFACTS = ARGS.artifacts.resolve()
        ARTIFACTS.mkdir(parents=True, exist_ok=False)
        print("ARTIFACTS:", ARTIFACTS, flush=True)
        unittest.main(argv=[__file__, *remaining])
    else:
        with tempfile.TemporaryDirectory(prefix="rainbowgrades-contact-") as temp:
            ARTIFACTS = Path(temp)
            program = unittest.main(argv=[__file__, *remaining], exit=False)
            raise SystemExit(0 if program.result.wasSuccessful() else 1)
