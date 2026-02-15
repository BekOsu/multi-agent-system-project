"""ChromaDB-backed vector store for RAG context retrieval."""

import os

_collection = None


def _get_collection():
    """Lazy-init a ChromaDB persistent collection."""
    global _collection
    if _collection is not None:
        return _collection

    try:
        import chromadb
    except ImportError:
        print("[rag] chromadb not installed — RAG disabled")
        _collection = False
        return _collection

    persist_dir = os.path.join(os.path.dirname(__file__), ".chroma_data")
    client = chromadb.PersistentClient(path=persist_dir)
    _collection = client.get_or_create_collection(
        name="project_examples",
        metadata={"hnsw:space": "cosine"},
    )

    # Seed if empty
    if _collection.count() == 0:
        seed_examples()

    return _collection


# ── Example seeds ────────────────────────────────────────────────────────────

_EXAMPLES = [
    {
        "id": "todo-app",
        "document": (
            "Todo App Pattern: Pages — dashboard, task list, task detail. "
            "Endpoints — GET /api/tasks, POST /api/tasks, PUT /api/tasks/{id}, "
            "DELETE /api/tasks/{id}. Models — Task(id, title, description, "
            "completed, created_at). Use optimistic UI updates and local state."
        ),
        "metadata": {"category": "productivity"},
    },
    {
        "id": "ecommerce",
        "document": (
            "E-commerce Pattern: Pages — product listing, product detail, cart, "
            "checkout. Endpoints — GET /api/products, GET /api/products/{id}, "
            "POST /api/cart, POST /api/orders. Models — Product(id, name, price, "
            "description, image_url), CartItem(product_id, quantity), "
            "Order(id, items, total, status). Implement cart as client-side state."
        ),
        "metadata": {"category": "ecommerce"},
    },
    {
        "id": "auth-pattern",
        "document": (
            "Authentication Pattern: Pages — login, register, profile. "
            "Endpoints — POST /api/auth/login, POST /api/auth/register, "
            "GET /api/auth/me. Models — User(id, email, hashed_password, name). "
            "Use JWT tokens stored in httpOnly cookies. Middleware checks "
            "Authorization header on protected routes."
        ),
        "metadata": {"category": "auth"},
    },
    {
        "id": "dashboard",
        "document": (
            "Dashboard Pattern: Pages — overview, analytics, settings. "
            "Components — StatCard, Chart, DataTable. Use grid layout with "
            "responsive breakpoints. Fetch summary stats from "
            "GET /api/stats/overview. Support date-range filtering."
        ),
        "metadata": {"category": "dashboard"},
    },
]


def seed_examples() -> None:
    """Pre-load example project patterns into the vector store."""
    col = _get_collection()
    if not col:
        return
    col.add(
        ids=[e["id"] for e in _EXAMPLES],
        documents=[e["document"] for e in _EXAMPLES],
        metadatas=[e["metadata"] for e in _EXAMPLES],
    )
    print(f"[rag] Seeded {len(_EXAMPLES)} example patterns into vector store")


def query(text: str, k: int = 3) -> list[dict]:
    """Return top-k relevant chunks with metadata.

    Each result dict has keys: id, document, metadata, distance.
    """
    col = _get_collection()
    if not col or col.count() == 0:
        return []

    results = col.query(query_texts=[text], n_results=min(k, col.count()))

    items = []
    for i in range(len(results["ids"][0])):
        items.append({
            "id": results["ids"][0][i],
            "document": results["documents"][0][i],
            "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
            "distance": results["distances"][0][i] if results["distances"] else None,
        })
    return items
