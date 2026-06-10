from __future__ import annotations

"""
data/news/embedder.py

Embeds news articles using sentence-transformers.
Runs locally -- no API key or internet needed after first download.

Model: all-MiniLM-L6-v2
    - 90MB download on first use
    - 384-dimensional embeddings
    - Fast and accurate for semantic similarity
"""

from sentence_transformers import SentenceTransformer

# --- Model -------------------------------------------------------------------

MODEL_NAME = "all-MiniLM-L6-v2"
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Lazy load model -- only downloads on first call."""
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


# --- Embed -------------------------------------------------------------------

def embed_articles(articles: list[dict]) -> list[dict]:
    """
    Add an embedding vector to each article.
    Embeds title + summary together.

    Args:
        articles: list of article dicts from fetcher.fetch_news()

    Returns:
        Same list with "embedding" key added to each dict.
    """
    if not articles:
        return []

    model  = _get_model()
    texts  = [f"{a['title']}. {a['summary']}" for a in articles]
    vectors = model.encode(texts, show_progress_bar=False)

    for article, vector in zip(articles, vectors):
        article["embedding"] = vector.tolist()

    return articles


def embed_query(query: str) -> list[float]:
    """
    Embed a search query for similarity search.

    Args:
        query: e.g. "Mexico injury suspension form"

    Returns:
        384-dimensional embedding vector as a list of floats.
    """
    model = _get_model()
    return model.encode(query, show_progress_bar=False).tolist()