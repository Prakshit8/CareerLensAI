"""Standard retrieval and ranking metrics for graded relevance labels."""

import math
from collections.abc import Sequence


def _relevance_list(ranked_ids: Sequence[str], relevance: dict[str, int]) -> list[int]:
    return [max(0, int(relevance.get(job_id, 0))) for job_id in ranked_ids]


def precision_at_k(
    ranked_ids: Sequence[str], relevant_ids: set[str], k: int
) -> float:
    if k <= 0:
        raise ValueError("k must be positive.")
    return sum(job_id in relevant_ids for job_id in ranked_ids[:k]) / k


def recall_at_k(
    ranked_ids: Sequence[str], relevant_ids: set[str], k: int
) -> float:
    if k <= 0:
        raise ValueError("k must be positive.")
    if not relevant_ids:
        return 0.0
    hits = sum(job_id in relevant_ids for job_id in ranked_ids[:k])
    return min(1.0, hits / len(relevant_ids))


def reciprocal_rank(ranked_ids: Sequence[str], relevant_ids: set[str]) -> float:
    for rank, job_id in enumerate(ranked_ids, start=1):
        if job_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def hit_rate_at_k(
    ranked_ids: Sequence[str], relevant_ids: set[str], k: int
) -> float:
    if k <= 0:
        raise ValueError("k must be positive.")
    return float(any(job_id in relevant_ids for job_id in ranked_ids[:k]))


def ndcg_at_k(
    ranked_ids: Sequence[str], relevance: dict[str, int], k: int
) -> float:
    if k <= 0:
        raise ValueError("k must be positive.")

    def dcg(values: Sequence[int]) -> float:
        return sum((2**value - 1) / math.log2(index + 2) for index, value in enumerate(values))

    actual = dcg(_relevance_list(ranked_ids[:k], relevance))
    ideal = dcg(sorted((max(0, int(value)) for value in relevance.values()), reverse=True)[:k])
    return actual / ideal if ideal else 0.0


def retrieval_metrics(
    ranked_ids: Sequence[str],
    relevance: dict[str, int],
    *,
    ks: tuple[int, ...] = (5, 10),
) -> dict[str, float]:
    relevant_ids = {job_id for job_id, grade in relevance.items() if grade > 0}
    results = {
        "mrr": reciprocal_rank(ranked_ids, relevant_ids),
    }
    for k in ks:
        results[f"precision@{k}"] = precision_at_k(ranked_ids, relevant_ids, k)
        results[f"recall@{k}"] = recall_at_k(ranked_ids, relevant_ids, k)
        results[f"hit_rate@{k}"] = hit_rate_at_k(ranked_ids, relevant_ids, k)
        results[f"ndcg@{k}"] = ndcg_at_k(ranked_ids, relevance, k)
    return results
