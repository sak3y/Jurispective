"""Evaluate retrieval recall against expected legislation sections.

Each test case uses:
    question: user query
    expected: legislation.gov.uk section URL (or a legacy escaped URL)
    note: explanation of the expected provision

A test passes when at least one of the top-k retrieved documents belongs
specifically to the expected section, including its subsections.
"""

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from backend.rag import get_store, retrieve

DEFAULT_TEST_PATH = Path(__file__).resolve().parent / "tests" / "test_full.json"


def section_path(value):
    """Normalise an expected URL or retrieved URI for section-level matching."""
    if not isinstance(value, str):
        return None
    # The existing dataset escapes URL punctuation as if it were a regex.
    value = value.replace(r"\/", "/").replace(r"\.", ".").strip()
    path = urlsplit(value).path.rstrip("/")
    match = re.search(r"/(?:section|schedule)/[^/]+", path, re.IGNORECASE)
    if not match:
        return None
    return path[:match.end()].lower()


def matches_expected(uri, expected):
    actual_path = section_path(uri)
    expected_path = section_path(expected)
    return actual_path is not None and actual_path == expected_path


def evaluate(store, k=4, path=DEFAULT_TEST_PATH):
    """Evaluate retrieval at one value of k; no re-indexing is performed."""
    with open(path, encoding="utf-8") as handle:
        cases = json.load(handle)

    if not isinstance(cases, list):
        raise ValueError("Test JSON must contain a list of test cases")

    hits_at_k = 0
    evaluated = 0
    for number, case in enumerate(cases, start=1):
        question = case.get("question")
        expected = case.get("expected")
        if not question or not isinstance(expected, str):
            print(f"SKIP  case {number}: missing question or expected URL")
            continue

        # Non-legislation questions are not retrieval-recall tests.
        if section_path(expected) is None:
            print(f"SKIP  {question} (no expected legislation section)")
            continue

        results = retrieve(store, question, k=k)
        found = any(matches_expected(doc.metadata.get("uri", ""), expected)
                    for doc, _ in results)
        evaluated += 1
        hits_at_k += int(found)
        print(f"{'PASS' if found else 'FAIL'}  {question}")
        if not found:
            print(f"      Expected: {expected}")
            if case.get("note"):
                print(f"      Note: {case['note']}")

    percentage = 100 * hits_at_k / evaluated if evaluated else 0
    print(f"\nRecall@{k}: {hits_at_k}/{evaluated} ({percentage:.1f}%)")
    print(f"Skipped: {len(cases) - evaluated}")
    return hits_at_k, evaluated


if __name__ == "__main__":
    store = get_store()
    for k in (4, 10):
        print(f"\n{'=' * 20} K={k} {'=' * 20}")
        evaluate(store, k=k)
