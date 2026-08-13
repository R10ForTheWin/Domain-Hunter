#!/usr/bin/env python3
"""
Validates every data/*.csv against the schemas pinned in docs/data-contracts.md.

Five people build five packages on five branches against one set of CSV shapes.
Nothing enforced those shapes until now — the process was "edit the contract doc
in your PR and mention it in the group chat", which is a social convention with
no backstop. This is the backstop.

Run from the repo root. Exits 0 if everything checks out, 1 if anything fails,
so it can gate a merge:

    python3 qa/validate_contracts.py
    python3 qa/validate_contracts.py --strict     # warnings become failures

WHAT IT CHECKS
--------------
  header      every required column present, in any order
  enums       pd_status / confidence / bool columns hold only legal values
  types       int-or-blank columns parse; dates match their required format
  jan-1st     every pd_date is a January 1st (docs/project-plan.md section 1)
  keys        book_id unique in the corpus, and resolvable from every file
              that references one
  shortlist   ranks contiguous from 1, at most 10, and pd_status is always
              "confirmed" — the no-exceptions rule from project-plan.md section 5
  committed   no contract deliverable is gitignored or untracked

MISSING FILES ARE SKIPPED, NOT FAILED. Packages land at different times and a
file that does not exist yet is not a contract violation. The report says which
were skipped so an empty run cannot be mistaken for a passing one.

WHY THE "committed" CHECK EARNS ITS PLACE
-----------------------------------------
It is the one check here that catches a bug the others structurally cannot. A
gitignored deliverable is written perfectly well on the machine that produced it
and is simply absent everywhere else — the pipeline works for its author and
returns empty for everyone else, with the *downstream* package looking like the
culprit. That exact bug reached a PR in this project (ISSUE-8), and a schema
check would never have seen it, because the file on disk was valid.
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

PD_STATUS_VALUES = {"confirmed", "not_confirmed", "uncertain"}
CONFIDENCE_VALUES = {"confirmed", "disputed", "uncertain"}
BOOL_VALUES = {"true", "false"}

SHORTLIST_MAX = 10

DATE_YMD = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_JAN_1 = re.compile(r"^\d{4}-01-01$")


# --- column specs ----------------------------------------------------------


@dataclass(frozen=True)
class Column:
    name: str
    required: bool = True
    blank_ok: bool = True
    kind: str = "string"  # string | int | bool | date | date_jan1
    enum: Optional[frozenset] = None


@dataclass(frozen=True)
class FileSpec:
    path: str
    produced_by: str
    columns: tuple
    # Extra columns are a contract violation everywhere EXCEPT studio_scores.csv,
    # where data-contracts.md explicitly invites per-rubric sub-score columns.
    extra_columns_ok: bool = False
    unique_key: Optional[str] = None
    # Every book_id here must exist in book_corpus.csv.
    references_corpus: bool = True
    row_checks: tuple = ()


def _c(name, **kw):
    return Column(name, **kw)


BOOK_CORPUS = FileSpec(
    path="data/book_corpus.csv",
    produced_by="Package 3",
    unique_key="book_id",
    references_corpus=False,  # it *is* the corpus
    columns=(
        _c("book_id", blank_ok=False),
        _c("title", blank_ok=False),
        _c("author"),
        _c("author_death_year", kind="int"),
        _c("author_death_year_disputed", kind="bool", enum=frozenset(BOOL_VALUES)),
        _c("publication_year", kind="int"),
        _c("source"),
        _c("source_url"),
        _c("language"),
        _c("notes"),
    ),
)

PD_CALENDAR = FileSpec(
    path="data/pd_calendar.csv",
    produced_by="Package 1",
    columns=(
        _c("pd_date", kind="date_jan1"),
        _c("book_id"),
        _c("title"),
        _c("author"),
        _c("author_death_year", kind="int"),
        _c("publication_year", kind="int"),
        _c("rule_applied"),
        _c("confidence", blank_ok=False, enum=frozenset(CONFIDENCE_VALUES)),
        _c("flags"),
        _c("source"),
        _c("notes"),
    ),
)

PD_VERIFICATION = FileSpec(
    path="data/pd_verification.csv",
    produced_by="Package 2",
    unique_key="book_id",
    columns=(
        _c("book_id", blank_ok=False),
        _c("pd_status", blank_ok=False, enum=frozenset(PD_STATUS_VALUES)),
        _c("reasoning"),
        _c("rule_applied"),
        _c("flags"),
        _c("verified_date", kind="date"),
    ),
)

PD_VERIFICATION_INPUTS = FileSpec(
    path="data/pd_verification_inputs.csv",
    produced_by="Package 2",
    columns=(
        _c("book_id", blank_ok=False),
        _c("country_of_first_publication"),
        _c("simultaneous_us_publication", kind="bool", enum=frozenset(BOOL_VALUES)),
        _c("is_anonymous_pseudonymous_or_corporate", kind="bool", enum=frozenset(BOOL_VALUES)),
        _c("had_copyright_notice_at_publication", kind="bool", enum=frozenset(BOOL_VALUES)),
        _c("renewal_filed", kind="bool", enum=frozenset(BOOL_VALUES)),
        _c("creation_year", kind="int"),
        _c("source"),
        _c("notes"),
    ),
)

STUDIO_SCORES = FileSpec(
    path="data/studio_scores.csv",
    produced_by="Package 4",
    unique_key="book_id",
    extra_columns_ok=True,  # per-rubric sub-scores are explicitly allowed
    columns=(
        _c("book_id", blank_ok=False),
        _c("studio", blank_ok=False),
        _c("total_score", blank_ok=False),
        _c("reasoning"),
    ),
)

SHORTLIST = FileSpec(
    path="data/shortlist.csv",
    produced_by="Package 5",
    unique_key="book_id",
    columns=(
        _c("rank", blank_ok=False, kind="int"),
        _c("book_id", blank_ok=False),
        _c("title"),
        _c("author"),
        _c("total_score", blank_ok=False),
        _c("score_reasoning"),
        _c("pd_status", blank_ok=False, enum=frozenset({"confirmed"})),
        _c("pd_reasoning"),
    ),
)

SPECS = (BOOK_CORPUS, PD_CALENDAR, PD_VERIFICATION, PD_VERIFICATION_INPUTS, STUDIO_SCORES, SHORTLIST)


# --- results ---------------------------------------------------------------


@dataclass
class Report:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    checked: list = field(default_factory=list)

    def error(self, path: str, msg: str) -> None:
        self.errors.append(f"{path}: {msg}")

    def warn(self, path: str, msg: str) -> None:
        self.warnings.append(f"{path}: {msg}")

    def ok(self, strict: bool) -> bool:
        return not self.errors and not (strict and self.warnings)


# --- checks ----------------------------------------------------------------


def _is_int(value: str) -> bool:
    return value.lstrip("-").isdigit()


def check_header(spec: FileSpec, header: list, rep: Report) -> None:
    present = set(header)
    for col in spec.columns:
        if col.required and col.name not in present:
            rep.error(spec.path, f"missing required column `{col.name}`")
    if not spec.extra_columns_ok:
        extra = present - {c.name for c in spec.columns}
        if extra:
            # A warning, not an error: an added column breaks nobody who reads by
            # name, but it means the contract doc and the file have diverged.
            rep.warn(
                spec.path,
                f"columns not in docs/data-contracts.md: {', '.join(sorted(extra))}"
                " — add them to the contract or drop them",
            )


def check_rows(spec: FileSpec, rows: list, rep: Report) -> None:
    by_name = {c.name: c for c in spec.columns}
    seen_keys: dict = {}

    for i, row in enumerate(rows, start=2):  # line 1 is the header
        for name, col in by_name.items():
            if name not in row:
                continue
            raw = (row.get(name) or "").strip()

            if not raw:
                if not col.blank_ok:
                    rep.error(spec.path, f"line {i}: `{name}` is blank but must have a value")
                continue

            if col.enum is not None and raw.lower() not in col.enum:
                rep.error(
                    spec.path,
                    f"line {i}: `{name}` is {raw!r}, expected one of "
                    f"{', '.join(sorted(col.enum))}",
                )
            elif col.kind == "int" and not _is_int(raw):
                rep.error(spec.path, f"line {i}: `{name}` is {raw!r}, expected an integer or blank")
            elif col.kind == "date" and not DATE_YMD.match(raw):
                rep.error(spec.path, f"line {i}: `{name}` is {raw!r}, expected YYYY-MM-DD")
            elif col.kind == "date_jan1" and not DATE_JAN_1.match(raw):
                rep.error(
                    spec.path,
                    f"line {i}: `{name}` is {raw!r}, expected YYYY-01-01 — copyright terms end on"
                    " Dec 31, so works enter the public domain only on January 1st"
                    " (docs/project-plan.md section 1)",
                )

        if spec.unique_key:
            key = (row.get(spec.unique_key) or "").strip()
            if key:
                if key in seen_keys:
                    rep.error(
                        spec.path,
                        f"line {i}: duplicate `{spec.unique_key}` {key!r}"
                        f" (first seen on line {seen_keys[key]})",
                    )
                else:
                    seen_keys[key] = i


def check_corpus_references(spec: FileSpec, rows: list, corpus_ids: set, rep: Report) -> None:
    """Every book_id must resolve — docs/data-contracts.md, "Primary key"."""
    if not spec.references_corpus or corpus_ids is None:
        return
    missing = {
        (r.get("book_id") or "").strip()
        for r in rows
        if (r.get("book_id") or "").strip() and (r.get("book_id") or "").strip() not in corpus_ids
    }
    if missing:
        sample = ", ".join(sorted(missing)[:3])
        rep.error(
            spec.path,
            f"{len(missing)} book_id(s) not present in data/book_corpus.csv — e.g. {sample}."
            " Package 3 is the source of truth for which book_ids exist",
        )


def check_shortlist_rules(rows: list, rep: Report) -> None:
    """project-plan.md section 5: PD-confirmed only, top 10, never padded."""
    path = SHORTLIST.path
    if len(rows) > SHORTLIST_MAX:
        rep.error(path, f"{len(rows)} rows, but the shortlist is capped at {SHORTLIST_MAX}")

    ranks = [int(r["rank"]) for r in rows if (r.get("rank") or "").strip().isdigit()]
    if ranks and sorted(ranks) != list(range(1, len(ranks) + 1)):
        rep.error(path, f"ranks must run 1..{len(ranks)} with no gaps or repeats; got {sorted(ranks)}")

    scores = []
    for r in rows:
        raw = (r.get("total_score") or "").strip()
        try:
            scores.append(float(raw))
        except ValueError:
            rep.error(path, f"total_score {raw!r} is not a number")
            return
    if scores != sorted(scores, reverse=True):
        rep.warn(path, "rows are not in descending total_score order")


def check_committed(spec: FileSpec, rep: Report, repo_root: Path) -> None:
    """A contract deliverable that git refuses is worse than one that is absent.

    See the module docstring — this is the ISSUE-8 catcher.

    `repo_root` is threaded through rather than read from the module constant so
    the check runs against the tree being validated. Using the constant made this
    report on the developer's own checkout no matter which directory it was
    pointed at, which the tests caught.
    """
    rel = spec.path
    inside_git = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=repo_root, capture_output=True, timeout=10,
    ).returncode == 0
    if not inside_git:
        return  # not a git checkout — nothing to say about tracking

    try:
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", rel],
            cwd=repo_root, capture_output=True, timeout=10,
        ).returncode == 0
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", rel],
            cwd=repo_root, capture_output=True, timeout=10,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return  # git unavailable — not this tool's problem

    if ignored:
        rep.error(
            rel,
            "is gitignored, but it is a contract deliverable other packages read."
            " It will be written locally and absent for everyone else, so the package that"
            " *reads* it will look like the broken one. Remove it from .gitignore",
        )
    elif not tracked:
        rep.warn(rel, "exists on disk but is not tracked by git — commit it so downstream packages get it")


# --- driver ----------------------------------------------------------------


def read_csv(path: Path) -> tuple:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def validate(repo_root: Path = REPO_ROOT, specs=SPECS) -> Report:
    rep = Report()

    corpus_path = repo_root / BOOK_CORPUS.path
    corpus_ids = None
    if corpus_path.exists():
        _, corpus_rows = read_csv(corpus_path)
        corpus_ids = {(r.get("book_id") or "").strip() for r in corpus_rows}

    for spec in specs:
        path = repo_root / spec.path
        if not path.exists():
            rep.skipped.append(f"{spec.path} (not produced yet — {spec.produced_by})")
            continue

        rep.checked.append(spec.path)
        header, rows = read_csv(path)
        check_header(spec, header, rep)
        check_rows(spec, rows, rep)
        check_corpus_references(spec, rows, corpus_ids, rep)
        check_committed(spec, rep, repo_root)
        if spec is SHORTLIST:
            check_shortlist_rules(rows, rep)

    return rep


def print_report(rep: Report, strict: bool) -> None:
    for path in rep.checked:
        print(f"  checked  {path}")
    for note in rep.skipped:
        print(f"  skipped  {note}")

    if rep.warnings:
        print(f"\n{len(rep.warnings)} warning(s):")
        for w in rep.warnings:
            print(f"  ! {w}")
    if rep.errors:
        print(f"\n{len(rep.errors)} error(s):")
        for e in rep.errors:
            print(f"  x {e}")

    print()
    if rep.ok(strict):
        note = "" if not rep.warnings else f" ({len(rep.warnings)} warning(s))"
        print(f"PASS — {len(rep.checked)} file(s) match docs/data-contracts.md{note}")
    else:
        print(f"FAIL — {len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
    if rep.skipped and not rep.checked:
        print("NOTE: every contract file was missing — this run validated nothing.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate data/*.csv against docs/data-contracts.md")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)

    rep = validate(args.repo_root)
    print_report(rep, args.strict)
    return 0 if rep.ok(args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
