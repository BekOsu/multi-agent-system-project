"""Query the vector store and format results as a context block for the planner."""

from rag.vector_store import query


def get_context(user_request: str, k: int = 3) -> str:
    """Return a formatted context string from similar project examples.

    Returns empty string when no results are available.
    """
    results = query(user_request, k=k)
    if not results:
        return ""

    lines = []
    for r in results:
        category = r["metadata"].get("category", "general")
        lines.append(f"- **[{category}]** {r['document']}")
    return "\n".join(lines)
