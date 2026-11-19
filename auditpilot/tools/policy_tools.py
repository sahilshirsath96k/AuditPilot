"""Policy clause retrieval using TF-IDF."""

from collections import Counter
from math import log, sqrt
from pathlib import Path
import re


def retrieve_policy(
    query: str,
    k: int = 3,
    policy_path: str = "data/policy.md",
) -> list[dict]:
    """Retrieve the most relevant policy clauses using TF-IDF."""

    if not isinstance(query, str) or not query.strip():
        return []

    path = Path(policy_path)
    if not path.exists():
        return []

    content = path.read_text(encoding="utf-8")

    pattern = re.compile(
	r"^\s*-\s*\*\*Clause\s+([\d.]+):\s*(.*?)\*\*\s*(.*?)(?=^\s*-\s*\*\*Clause\s+[\d.]+:|^\s*---\s*$|\Z)",
        re.MULTILINE | re.DOTALL,
    )

    clauses = []
    for match in pattern.finditer(content):
        clause_id, title, body = match.groups()
        text = f"Clause {clause_id}: {title}. {body.strip()}"
        clauses.append({
            "clause_id": clause_id,
            "title": title.strip(),
            "text": text,
        })

    if not clauses:
        return []

    def tokenize(text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", text.lower())

    documents = [tokenize(clause["text"]) for clause in clauses]
    query_tokens = tokenize(query)

    if not query_tokens:
        return []

    document_count = len(documents)
    document_frequency = Counter(
        token
        for document in documents
        for token in set(document)
    )

    def vectorize(tokens: list[str]) -> dict[str, float]:
        frequencies = Counter(tokens)
        vector = {}

        for token, frequency in frequencies.items():
            idf = log((1 + document_count) / (1 + document_frequency[token])) + 1
            vector[token] = (frequency / len(tokens)) * idf

        return vector

    query_vector = vectorize(query_tokens)

    def cosine_similarity(a: dict, b: dict) -> float:
        common = set(a) & set(b)
        dot = sum(a[token] * b[token] for token in common)

        norm_a = sqrt(sum(value ** 2 for value in a.values()))
        norm_b = sqrt(sum(value ** 2 for value in b.values()))

        if not norm_a or not norm_b:
            return 0.0

        return dot / (norm_a * norm_b)

    results = []

    for clause, tokens in zip(clauses, documents):
        score = cosine_similarity(query_vector, vectorize(tokens))

        # Give additional weight to terms matching the clause title.
        title_tokens = set(tokenize(clause["title"]))
        title_matches = set(query_tokens) & title_tokens
        score += 0.30 * len(title_matches)

        if score > 0:
            results.append({**clause, "score": round(score, 4)})

    results.sort(key=lambda item: (-item["score"], item["clause_id"]))

    return results[:max(0, k)]
