# Search evaluation

Run `python -m scripts.evaluate_search` after importing the labeled dataset. The script writes timestamped JSON and CSV reports under `data/evaluation/reports/` and stores a copy in SQLite. It measures:

- Precision@5/10 using `relevant results / k`.
- Recall@5/10 using `relevant retrieved / all labeled relevant`, bounded by 1.
- MRR using the reciprocal rank of the first relevant result.
- Hit rate@5/10 as a binary query-level hit.
- nDCG@5/10 with graded gain `2^relevance - 1` and logarithmic rank discount.
- Per-mode p50/p95 observed retrieval latency and query error rate.

The checked-in ground truth references stable synthetic source IDs and states its role-category labeling method in `data/evaluation/queries.json`. It is a small demonstration benchmark, not a representative labor-market dataset. Semantic and hybrid modes report errors/warnings if model retrieval is unavailable; the evaluator does not substitute fabricated scores. A hybrid warning means the run degraded to BM25 and should not be interpreted as a full dense+lexical comparison.

Tool execution success rate is computed from persisted tool-run records. Tool-selection accuracy, task-completion rate, and preference-retention accuracy remain `null` until labeled agent scenarios are supplied; they are not inferred from unlabelled conversations. Metric helpers are implemented and covered by hand-checked tests. Preference persistence and tool workflows are also covered by deterministic integration tests.
