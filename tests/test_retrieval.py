import math

from backend.app.search.bm25 import BM25Index
from backend.app.ingestion.normalizer import normalize_job


def test_bm25_ranks_matching_documents_and_handles_no_matches():
    index = BM25Index([
        "Python backend APIs with FastAPI",
        "Product analytics with SQL",
        "Python and retrieval augmented generation with LLM",
    ])
    scores = index.scores("Python LLM")
    assert scores[2] > scores[0] > scores[1]
    assert BM25Index(["unrelated"]).scores("missing") == [0.0]


def test_normalizer_accepts_csv_aliases_and_generates_stable_identity():
    first = normalize_job(
        {"title": "  AI   Engineer ", "company": " Example Co ",
         "job_type": "Internship", "skills": "Python; RAG"},
        "test-source",
    )
    second = normalize_job(
        {"title": "AI Engineer", "company": "Example Co", "job_type": "Internship",
         "skills": "Python; RAG"},
        "test-source",
    )
    assert first.title == "AI Engineer"
    assert first.skills == ["Python", "RAG"]
    assert first.external_id == second.external_id


def test_metrics_are_bounded_and_match_hand_calculated_example():
    from backend.app.evaluation.metrics import (
        hit_rate_at_k, ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank,
    )

    ranked = ["irrelevant", "b", "a"]
    relevant = {"a", "b"}
    assert precision_at_k(ranked, relevant, 3) == 2 / 3
    assert recall_at_k(ranked, relevant, 3) == 1
    assert recall_at_k(ranked, relevant, 1) <= 1
    assert reciprocal_rank(ranked, relevant) == 0.5
    assert hit_rate_at_k(ranked, relevant, 1) == 0
    expected = (1 + 3 / math.log2(3)) / (3 + 1 / math.log2(3))
    assert abs(ndcg_at_k(["b", "a"], {"a": 2, "b": 1}, 2) - expected) < 1e-9


def test_agent_metrics_report_rates_without_inventing_unlabeled_values():
    from backend.app.evaluation.agent_metrics import (
        preference_retention_accuracy, task_completion_rate,
        tool_execution_success_rate, tool_selection_accuracy,
    )

    assert tool_selection_accuracy([["search"]], [["search"]]) == 1
    assert tool_selection_accuracy([], []) is None
    assert tool_execution_success_rate([True, False]) == 0.5
    assert task_completion_rate([True, False, True]) == 2 / 3
    assert preference_retention_accuracy(
        [{"preferred_locations": ["Remote"]}],
        [{"preferred_locations": ["Remote"]}],
    ) == 1

