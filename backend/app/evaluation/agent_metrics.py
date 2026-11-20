"""Metrics for labeled tool decisions and recorded assistant workflows."""

from collections.abc import Mapping, Sequence


def tool_selection_accuracy(
    expected: Sequence[Sequence[str]], selected: Sequence[Sequence[str]]
) -> float | None:
    """Return exact per-case tool-sequence accuracy; None when unlabeled."""
    if not expected:
        return None
    count = min(len(expected), len(selected))
    if not count:
        return 0.0
    return sum(list(expected[i]) == list(selected[i]) for i in range(count)) / len(expected)


def tool_execution_success_rate(successes: Sequence[bool]) -> float | None:
    """Return successful executed calls divided by recorded calls."""
    return sum(successes) / len(successes) if successes else None


def task_completion_rate(completions: Sequence[bool]) -> float | None:
    """Return completed labeled tasks divided by evaluated tasks."""
    return sum(completions) / len(completions) if completions else None


def preference_retention_accuracy(
    expected: Sequence[Mapping[str, object]],
    observed: Sequence[Mapping[str, object]],
) -> float | None:
    """Measure exact persisted key/value matches over labeled expectations."""
    if not expected:
        return None
    return sum(
        all(actual.get(key) == value for key, value in case.items())
        for case, actual in zip(expected, observed)
    ) / len(expected)
