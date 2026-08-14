#!/usr/bin/env python3
"""
Tests for build_calendar — the corpus -> pd_calendar.csv producer.

Covers the contract shape, the funnel arithmetic, and the cases where a row must
NOT get a date. Uses tempfiles rather than data/book_corpus.csv, so the suite
runs on any branch whether or not Package 3 has been merged.
"""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import build_calendar
from pd_rules import next_cliffs

NOW = 2026

CORPUS_HEADER = [
    "book_id", "title", "author", "author_death_year", "author_death_year_disputed",
    "publication_year", "source", "source_url", "language", "notes",
]


def corpus_row(book_id, title, author, death="", disputed="false", pub="", language="en"):
    return {
        "book_id": book_id, "title": title, "author": author,
        "author_death_year": death, "author_death_year_disputed": disputed,
        "publication_year": pub, "source": "test", "source_url": "",
        "language": language, "notes": "",
    }


SAMPLE = [
    # already public domain — pub+95 elapsed long ago
    corpus_row("frankenstein__shelley-mary__1818", "Frankenstein", "Shelley, Mary", "1851", pub="1818"),
    # enters 2027
    corpus_row("a__a-author__1931", "Nineteen Thirty-One", "A, Author", "1940", pub="1931"),
    # enters 2030 — pub+95, NOT life+70 (which would say 2047)
    corpus_row("orient__christie-agatha__1934", "Orient Express", "Christie, Agatha", "1976", pub="1934"),
    # no publication year, long-dead author -> inferred already-PD
    corpus_row("unk__old-writer__unk", "Untitled", "Old, Writer", "1900"),
    # nothing on file at all
    corpus_row("void__nobody__unk", "Nothing Known", "Nobody"),
    # reprint date recorded as first publication -> no date published
    corpus_row("reprint__dead-author__1970", "Reprint", "Dead, Author", "1932", pub="1970"),
]


class CalendarTestCase(unittest.TestCase):
    def build(self, rows=SAMPLE, **kwargs):
        """Run the producer over `rows`, return (csv_rows, report_text, funnel)."""
        tmp = Path(tempfile.mkdtemp())
        corpus, out_csv, out_md = tmp / "corpus.csv", tmp / "cal.csv", tmp / "cal.md"
        with corpus.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CORPUS_HEADER)
            w.writeheader()
            w.writerows(rows)

        argv = ["--input", str(corpus), "--output", str(out_csv), "--report", str(out_md),
                "--as-of-year", str(NOW)]
        for k, v in kwargs.items():
            argv.append(f"--{k.replace('_', '-')}") if v is True else argv.extend(
                [f"--{k.replace('_', '-')}", str(v)])
        self.assertEqual(build_calendar.main(argv), 0)

        with out_csv.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f)), out_md.read_text(encoding="utf-8")


class TestContractShape(CalendarTestCase):
    def test_columns_match_the_contract_exactly(self):
        rows, _ = self.build()
        self.assertTrue(rows, "expected at least one windowed row")
        self.assertEqual(list(rows[0].keys()), build_calendar.FIELDNAMES)

    def test_pd_date_is_always_january_first(self):
        rows, _ = self.build()
        for r in rows:
            self.assertRegex(r["pd_date"], r"^\d{4}-01-01$")

    def test_confidence_is_always_a_contract_value(self):
        rows, _ = self.build(all=True)
        for r in rows:
            self.assertIn(r["confidence"], ("confirmed", "disputed", "uncertain"))

    def test_publication_year_is_carried_through(self):
        """The column the amendment added — a reviewer must be able to check the date."""
        rows, _ = self.build(all=True)
        by_id = {r["book_id"]: r for r in rows}
        self.assertEqual(by_id["orient__christie-agatha__1934"]["publication_year"], "1934")


class TestWindowing(CalendarTestCase):
    def test_default_writes_only_the_window(self):
        rows, _ = self.build()
        cliffs = {str(y) for y in next_cliffs(NOW)}
        for r in rows:
            self.assertIn(r["pd_date"][:4], cliffs)

    def test_all_flag_writes_every_book(self):
        rows, _ = self.build(all=True)
        self.assertEqual(len(rows), len(SAMPLE))

    def test_christie_lands_in_2030_not_2047(self):
        rows, _ = self.build(all=True)
        by_id = {r["book_id"]: r for r in rows}
        self.assertEqual(by_id["orient__christie-agatha__1934"]["pd_date"], "2030-01-01")
        self.assertEqual(by_id["orient__christie-agatha__1934"]["rule_applied"], "pub+95")

    def test_horizon_is_adjustable(self):
        rows, _ = self.build(horizon=1)
        self.assertTrue(all(r["pd_date"].startswith("2027") for r in rows))


class TestRowsWithoutDates(CalendarTestCase):
    def test_undated_rows_are_kept_with_a_blank_date_under_all(self):
        """They must not be silently dropped — a blank date is a real answer."""
        rows, _ = self.build(all=True)
        by_id = {r["book_id"]: r for r in rows}
        self.assertEqual(by_id["void__nobody__unk"]["pd_date"], "")
        self.assertEqual(by_id["void__nobody__unk"]["rule_applied"], "unknown")
        self.assertEqual(by_id["void__nobody__unk"]["confidence"], "uncertain")

    def test_reprint_date_yields_no_calendar_entry(self):
        rows, _ = self.build(all=True)
        by_id = {r["book_id"]: r for r in rows}
        self.assertEqual(by_id["reprint__dead-author__1970"]["pd_date"], "")
        self.assertIn("publication_after_death", by_id["reprint__dead-author__1970"]["flags"])

    def test_undated_rows_never_reach_the_windowed_file(self):
        rows, _ = self.build()
        self.assertTrue(all(r["pd_date"] for r in rows))


class TestReport(CalendarTestCase):
    def test_report_names_every_cliff_year(self):
        _, report = self.build()
        for year in next_cliffs(NOW):
            self.assertIn(f"January 1, {year}", report)

    def test_report_states_the_funnel(self):
        _, report = self.build()
        self.assertIn(f"| Books read | {len(SAMPLE)} |", report)
        self.assertIn("No determinable date", report)

    def test_report_lists_the_work_and_its_author(self):
        _, report = self.build()
        self.assertIn("Christie, Agatha", report)
        self.assertIn("Orient Express", report)

    def test_report_says_a_date_is_not_clearance(self):
        """Package 2 is what confirms a claim — the report must not imply otherwise."""
        _, report = self.build()
        self.assertIn("pd_verification", report)

    def test_empty_window_is_stated_not_hidden(self):
        rows, report = self.build(rows=[SAMPLE[0]])  # already-PD book only
        self.assertEqual(rows, [])
        self.assertIn("No works in this window", report)


class TestMissingInput(unittest.TestCase):
    def test_missing_corpus_exits_nonzero_with_a_useful_message(self):
        tmp = Path(tempfile.mkdtemp())
        rc = build_calendar.main(["--input", str(tmp / "nope.csv"),
                                  "--output", str(tmp / "o.csv"),
                                  "--report", str(tmp / "o.md")])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
