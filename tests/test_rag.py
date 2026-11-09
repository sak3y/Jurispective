"""Evaluate retrieval using a JSON list of {question, expected, note} cases.

Run from the project root:
    python -m tests.test_rag --cases tests/test_set.json --k 5 15

The 'expected' field is a regular expression matched against a retrieved URI.
A case passes if ANY of the top-k URIs matches. This tests retrieval, not LLM accuracy.
"""

import argparse
import json
import re
from pathlib import Path

from backend import rag


def load_cases(path):
    with Path(path).open(encoding="utf-8") as file:
        cases = json.load(file)
    if not isinstance(cases, list):
        raise ValueError("Test file must contain a JSON array")
    for i, case in enumerate(cases, start=1):
        if not isinstance(case, dict) or not isinstance(case.get("question"), str):
            raise ValueError(f"Case {i} needs a string 'question'")
        if not isinstance(case.get("expected"), str):
            raise ValueError(f"Case {i} needs a string 'expected' regex (not 'expected_sections')")
        re.compile(case["expected"])
    return cases


def evaluate(cases, ks):
    store = rag.get_store()
    max_k = max(ks)
    totals = {k: 0 for k in ks}
    print(f"Evaluating {len(cases)} questions at k={', '.join(map(str, ks))}\n")

    evaluated = 0
    for i, case in enumerate(cases, start=1):
        if case["expected"] == "Waffle is not in the corpus":
            print(f"{i:02d}. SKIP (out-of-corpus answer test, not a retrieval URI test) | {case['question']}")
            continue
        evaluated += 1
        hits = rag.retrieve(store, case["question"], k=max_k)
        uris = [doc.metadata.get("uri", "") for doc, _ in hits]
        pattern = re.compile(case["expected"])
        matched_ranks = [rank for rank, uri in enumerate(uris, 1) if pattern.search(uri)]
        first_rank = matched_ranks[0] if matched_ranks else None
        results = []
        for k in ks:
            success = first_rank is not None and first_rank <= k
            totals[k] += int(success)
            results.append(f"R@{k}: {'PASS' if success else 'FAIL'}")
        print(f"{i:02d}. {' | '.join(results)} | rank={first_rank or '-'} | {case['question']}")
        if first_rank is None:
            print("    No matching URI in retrieved candidates")

    print("\nRetrieval hit rate (at least one expected URI in top k):")
    for k in ks:
        count = totals[k]
        print(f"  R@{k}: {count}/{evaluated} = {count / evaluated:.1%}" if evaluated else f"  R@{k}: no cases")

    return totals[max_k] / evaluated if evaluated else 0


def main():
    parser = argparse.ArgumentParser(description="Evaluate Wiggle Room retrieval")
    parser.add_argument("--cases", default=str(Path(__file__).resolve().parent / "test_set.json"), help="Path to evaluation JSON")
    parser.add_argument("--k", type=int, nargs="+", default=[5, 15], help="Top-k cutoffs")
    parser.add_argument("--min-recall", type=float, default=0.70, help="Minimum required recall at highest k")
    args = parser.parse_args()

    if any(k < 1 for k in args.k):
        parser.error("All k values must be positive")
    if not 0 <= args.min_recall <= 1:
        parser.error("--min-recall must be between 0 and 1")

    try:
        cases = load_cases(args.cases)
    except (OSError, json.JSONDecodeError, ValueError, re.error) as exc:
        parser.error(f"Cannot load cases: {exc}")

    recall = evaluate(cases, sorted(set(args.k)))
    if recall < args.min_recall:
        print(f"\nFAIL: Recall {recall:.1%} is below {args.min_recall:.0%}")
        raise SystemExit(1)

    print(f"\nPASS: Recall {recall:.1%} meets {args.min_recall:.0%} threshold")


if __name__ == "__main__":
    main()
