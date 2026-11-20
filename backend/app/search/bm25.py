"""Small dependency-free Okapi BM25 implementation."""

import math
import re
from collections import Counter

TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9+#.]*", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.casefold())


class BM25Index:
    """Rank a fixed document set using Okapi BM25."""

    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.documents = [tokenize(document) for document in documents]
        self.k1 = k1
        self.b = b
        self.lengths = [len(document) for document in self.documents]
        self.average_length = sum(self.lengths) / max(len(self.lengths), 1)
        self.term_frequencies = [Counter(document) for document in self.documents]
        self.document_frequency: Counter[str] = Counter()
        for frequencies in self.term_frequencies:
            self.document_frequency.update(frequencies.keys())

    def scores(self, query: str) -> list[float]:
        terms = tokenize(query)
        count = len(self.documents)
        results: list[float] = []
        for document_index, frequencies in enumerate(self.term_frequencies):
            score = 0.0
            length = self.lengths[document_index]
            for term in terms:
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                df = self.document_frequency[term]
                inverse_frequency = math.log(
                    1 + (count - df + 0.5) / (df + 0.5)
                )
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * length / max(self.average_length, 1)
                )
                score += inverse_frequency * frequency * (self.k1 + 1) / denominator
            results.append(score)
        return results
