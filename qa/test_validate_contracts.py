#!/usr/bin/env python3
"""
Tests for validate_contracts.

The important ones are in TestCatchesRealBugs: each reproduces a defect that
actually reached a pull request in this project and asserts the validator would
have caught it. A checker nobody has seen fail is indistinguishable from one
that always passes.

Run from the repo root:

    python3 -m unittest discover -s qa -t qa
"""
from __future__ import annotations

import csv
import subprocess
import tempfile
import unittest
from pathlib import Path

import validate_contracts as vc

CORPUS_COLS = [
    "book_id", "title", "author", "author_death_year", "author_death_year_disputed",
    "publication_year", "source", "source_url", "language", "notes",
]
CALENDAR_COLS = [
    "pd_date", "book_id", "title", "author", "author_death_year", "publication_year",
    "rule_applied", "confidence", "flags", "source", "notes",
]
VERIFY_COLS = ["book_id", "pd_status", "reasoning", "rule_applied", "flags", "verified_date"]
SCORES_COLS = ["book_id", "studio", "total_score", "reasoning"]
SHORTLIST_COLS = [
    "rank", "book_id", "title", "author", "total_score", "score_reasoning",
    "pd_status", "pd_reasoning",
]

BOOK_A = "frankenstein__shelley-mary__1818"
BOOK_B = "dracula__stoker-bram__1897"


def corpus_row(book_id=BOOK_A, **over):
    row = {c: "" for c in CORPUS_COLS}
    row.update(book_id=book_id, title="A Title", author="Author, An", author_death_year="1851",
               author_death_year_disputed="false", publication_year="1818", source="test",
               language="en")
    row.update(over)
    return row


def verify_row(book_id=BOOK_A, **over):
    row = {c: "" for c in VERIFY_COLS}
    row.update(book_id=book_id, pd_status="confirmed", reasoning="because",
               rule_applied="pub+95", verified_date="2026-08-13")
    row.update(over)
    return row


def shortlist_row(rank=1, book_id=BOOK_A, **over):
    row = {c: "" for c in SHORTLIST_COLS}
    row.update(rank=str(rank), book_id=book_id, title="A Title", author="Author, An",
               total_score="90.0", score_reasoning="fits", pd_status="confirmed",
               pd_reasoning="expired")
    row.update(over)
    return row


class ValidatorTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "data").mkdir()

    def write(self, name, cols, rows):
        p = self.root / "data" / name
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        return p

    def run_validator(self):
        return vc.validate(self.root)

    def assertFails(self, rep, needle):
        joined = " | ".join(rep.errors)
        self.assertTrue(rep.errors, f"expected an error mentioning {needle!r}, got none")
        self.assertIn(needle, joined)


class TestCatchesRealBugs(ValidatorTestCase):
    """Each of these reproduces a defect that reached a PR in this project."""

    def test_issue_8_gitignored_deliverable(self):
        """A contract file git refuses to track. Valid on disk, absent everywhere else."""
        repo = self.root
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        (repo / ".gitignore").write_text("data/studio_scores.csv\n")
        self.write("book_corpus.csv", CORPUS_COLS, [corpus_row()])
        self.write("studio_scores.csv", SCORES_COLS,
                   [{"book_id": BOOK_A, "studio": "A24", "total_score": "88", "reasoning": "x"}])
        self.assertFails(vc.validate(repo), "gitignored")

    def test_issue_5_book_id_that_no_longer_resolves(self):
        """Regenerating the corpus shifted book_ids; downstream files still hold the old ones."""
        self.write("book_corpus.csv", CORPUS_COLS, [corpus_row(book_id="flatland__abbott__1886")])
        self.write("pd_verification.csv", VERIFY_COLS, [verify_row(book_id="flatland__abbott__unk")])
        self.assertFails(self.run_validator(), "not present in data/book_corpus.csv")

    def test_wrong_rule_gives_a_date_that_is_not_january_first(self):
        """The whole premise of the calendar: terms end Dec 31, so PD starts Jan 1."""
        self.write("book_corpus.csv", CORPUS_COLS, [corpus_row()])
        rows = [{c: "" for c in CALENDAR_COLS}]
        rows[0].update(pd_date="2030-06-15", book_id=BOOK_A, confidence="uncertain",
                       rule_applied="pub+95")
        self.write("pd_calendar.csv", CALENDAR_COLS, rows)
        self.assertFails(self.run_validator(), "January 1st")

    def test_pd_gate_violation_in_the_shortlist(self):
        """project-plan.md section 5: no exceptions, even for a high scorer."""
        self.write("book_corpus.csv", CORPUS_COLS, [corpus_row()])
        self.write("shortlist.csv", SHORTLIST_COLS, [shortlist_row(pd_status="uncertain")])
        self.assertFails(self.run_validator(), "pd_status")

    def test_duplicate_book_ids_in_the_corpus(self):
        self.write("book_corpus.csv", CORPUS_COLS, [corpus_row(), corpus_row()])
        self.assertFails(self.run_validator(), "duplicate")


class TestSchema(ValidatorTestCase):
    def test_missing_required_column(self):
        cols = [c for c in CORPUS_COLS if c != "publication_year"]
        row = corpus_row(); row.pop("publication_year")
        self.write("book_corpus.csv", cols, [row])
        self.assertFails(self.run_validator(), "missing required column `publication_year`")

    def test_bad_enum_value(self):
        self.write("book_corpus.csv", CORPUS_COLS, [corpus_row()])
        self.write("pd_verification.csv", VERIFY_COLS, [verify_row(pd_status="probably")])
        self.assertFails(self.run_validator(), "expected one of")

    def test_blank_where_a_value_is_required(self):
        self.write("book_corpus.csv", CORPUS_COLS, [corpus_row()])
        self.write("pd_verification.csv", VERIFY_COLS, [verify_row(pd_status="")])
        self.assertFails(self.run_validator(), "must have a value")

    def test_non_integer_year(self):
        self.write("book_corpus.csv", CORPUS_COLS, [corpus_row(publication_year="circa 1818")])
        self.assertFails(self.run_validator(), "expected an integer")

    def test_bad_date_format(self):
        self.write("book_corpus.csv", CORPUS_COLS, [corpus_row()])
        self.write("pd_verification.csv", VERIFY_COLS, [verify_row(verified_date="13/08/2026")])
        self.assertFails(self.run_validator(), "expected YYYY-MM-DD")

    def test_blank_is_allowed_where_the_contract_allows_it(self):
        self.write("book_corpus.csv", CORPUS_COLS,
                   [corpus_row(author_death_year="", publication_year="")])
        self.assertEqual(self.run_validator().errors, [])

    def test_undeclared_column_warns_but_does_not_fail(self):
        cols = CORPUS_COLS + ["mood"]
        row = corpus_row(); row["mood"] = "gothic"
        self.write("book_corpus.csv", cols, [row])
        rep = self.run_validator()
        self.assertEqual(rep.errors, [])
        self.assertTrue(any("not in docs/data-contracts.md" in w for w in rep.warnings))

    def test_studio_scores_may_add_subscore_columns(self):
        """data-contracts.md explicitly invites these — must not warn."""
        cols = SCORES_COLS + ["genre_fit", "genre_fit_reasoning"]
        self.write("book_corpus.csv", CORPUS_COLS, [corpus_row()])
        self.write("studio_scores.csv", cols, [{
            "book_id": BOOK_A, "studio": "A24", "total_score": "88", "reasoning": "x",
            "genre_fit": "90", "genre_fit_reasoning": "y"}])
        rep = self.run_validator()
        self.assertEqual(rep.errors, [])
        self.assertFalse([w for w in rep.warnings if "studio_scores" in w])


class TestShortlistRules(ValidatorTestCase):
    def setUp(self):
        super().setUp()
        self.write("book_corpus.csv", CORPUS_COLS, [corpus_row(), corpus_row(book_id=BOOK_B)])

    def test_more_than_ten_rows(self):
        rows = [shortlist_row(rank=i, book_id=f"b{i}__a__1900") for i in range(1, 12)]
        self.write("shortlist.csv", SHORTLIST_COLS, rows)
        self.assertFails(self.run_validator(), "capped at 10")

    def test_ranks_must_be_contiguous(self):
        rows = [shortlist_row(rank=1), shortlist_row(rank=3, book_id=BOOK_B)]
        self.write("shortlist.csv", SHORTLIST_COLS, rows)
        self.assertFails(self.run_validator(), "no gaps or repeats")

    def test_fewer_than_ten_is_fine(self):
        """project-plan.md section 5: a short list is correct, padding is not."""
        rows = [shortlist_row(rank=1), shortlist_row(rank=2, book_id=BOOK_B, total_score="80.0")]
        self.write("shortlist.csv", SHORTLIST_COLS, rows)
        self.assertEqual(self.run_validator().errors, [])

    def test_out_of_order_scores_warn(self):
        rows = [shortlist_row(rank=1, total_score="50"),
                shortlist_row(rank=2, book_id=BOOK_B, total_score="90")]
        self.write("shortlist.csv", SHORTLIST_COLS, rows)
        rep = self.run_validator()
        self.assertTrue(any("descending" in w for w in rep.warnings))


class TestMissingFiles(ValidatorTestCase):
    def test_absent_files_are_skipped_not_failed(self):
        rep = self.run_validator()
        self.assertEqual(rep.errors, [])
        self.assertEqual(len(rep.skipped), len(vc.SPECS))

    def test_an_empty_run_is_reported_as_validating_nothing(self):
        """A pass over zero files must not read as a clean bill of health."""
        rep = self.run_validator()
        self.assertEqual(rep.checked, [])
        self.assertTrue(rep.ok(strict=False))  # not a failure...
        self.assertTrue(rep.skipped)           # ...but visibly empty

    def test_downstream_file_without_a_corpus_does_not_crash(self):
        self.write("pd_verification.csv", VERIFY_COLS, [verify_row()])
        rep = self.run_validator()
        self.assertNotIn("book_corpus", " ".join(rep.errors))


class TestStrictMode(ValidatorTestCase):
    def test_warnings_fail_only_under_strict(self):
        cols = CORPUS_COLS + ["mood"]
        row = corpus_row(); row["mood"] = "gothic"
        self.write("book_corpus.csv", cols, [row])
        rep = self.run_validator()
        self.assertTrue(rep.ok(strict=False))
        self.assertFalse(rep.ok(strict=True))


if __name__ == "__main__":
    unittest.main()
