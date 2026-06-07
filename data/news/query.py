"""
data/news/query.py

Retrieves relevant news chunks from ChromaDB.
Called by the orchestrator before the Gemini reasoning call.
"""

from data.news.embedder import embed_query
from data.news.store    import _get_collection


def retrieve(
    home_name: str,
    away_name: str,
    top_k: int = 5,
) -> list[dict]:
    """
    Retrieve the most relevant news articles for a fixture.

    Args:
        home_name: e.g. "Mexico"
        away_name: e.g. "South Africa"
        top_k:     number of results to return

    Returns:
        List of result dicts:
        {
            "title":     str,
            "summary":   str,
            "source":    str,
            "url":       str,
            "published": str,
            "teams":     str,
        }
    """
    collection = _get_collection()

    if collection.count() == 0:
        return []

    query_text = f"{home_name} {away_name} injury suspension form tactics"
    vector     = embed_query(query_text)

    results = collection.query(
        query_embeddings=[vector],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas"],
    )

    articles = []
    metadatas = results.get("metadatas", [[]])[0]
    documents = results.get("documents", [[]])[0]

    for meta, doc in zip(metadatas, documents):
        articles.append({
            "title":     meta.get("title", ""),
            "summary":   doc,
            "source":    meta.get("source", ""),
            "url":       meta.get("url", ""),
            "published": meta.get("published", ""),
            "teams":     meta.get("teams", ""),
        })

    return articles


def get_news_context(home_name: str, away_name: str) -> str:
    """
    Returns a plain text summary of top news for Gemini context.
    This is what gets fed into the reasoning prompt.

    Returns:
        Formatted string of top 5 relevant articles.
    """
    articles = retrieve(home_name, away_name)

    if not articles:
        return "No recent news found for this fixture."

    lines = [f"Recent news for {home_name} vs {away_name}:\n"]
    for i, a in enumerate(articles, 1):
        lines.append(
            f"{i}. [{a['source']}] {a['title']}\n"
            f"   {a['summary'][:200]}\n"
            f"   Published: {a['published'][:10]}\n"
        )

    return "\n".join(lines)