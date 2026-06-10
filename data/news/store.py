"""
data/news/store.py

ChromaDB vector store for news articles.
Runs locally -- no server needed.
"""

from __future__ import annotations
import chromadb

# --- Client ------------------------------------------------------------------

_client = None
COLLECTION_NAME = "match_news"


def _get_client():
    """Lazy init ChromaDB persistent client."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=".chroma")
    return _client


def _get_collection():
    """Get or create the news collection."""
    client = _get_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


# --- Store -------------------------------------------------------------------

def store_articles(articles: list[dict]) -> int:
    """
    Store embedded articles in ChromaDB.
    Uses article id for deduplication.
    """
    collection = _get_collection()
    embedded   = [a for a in articles if "embedding" in a]

    if not embedded:
        return 0

    collection.upsert(
        ids        = [a["id"] for a in embedded],
        embeddings = [a["embedding"] for a in embedded],
        documents  = [f"{a['title']}. {a['summary']}" for a in embedded],
        metadatas  = [{
            "source":    a["source"],
            "title":     a["title"],
            "url":       a["url"],
            "published": a["published"] or "",
            "teams":     ",".join(a["teams"]),
        } for a in embedded],
    )

    return len(embedded)


def clear_collection() -> None:
    """Clear all articles from the collection."""
    client = _get_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass


def count() -> int:
    """Return number of articles currently stored."""
    return _get_collection().count()