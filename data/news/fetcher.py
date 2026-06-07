"""
data/news/fetcher.py

Fetches and filters football news from RSS feeds.
No API keys needed -- RSS is public and free.

Sources:
    BBC Sport Football
    ESPN FC
    Guardian Football
    Sky Sports Football

Filters applied:
    1. Recency  -- last 7 days only
    2. Relevance -- must mention at least one team name
    3. Deduplication -- same title not stored twice
"""

import hashlib
import feedparser
from datetime import datetime, timezone, timedelta


# --- RSS feed sources ---------------------------------------------------------

FEEDS = {
    "BBC Sport":      "http://feeds.bbci.co.uk/sport/football/rss.xml",
    "ESPN FC":        "https://www.espn.com/espn/rss/soccer/news",
    "Guardian":       "https://www.theguardian.com/football/rss",
    "Sky Sports":     "https://www.skysports.com/rss/12040",
}

RECENCY_DAYS = 7


# --- Helpers ------------------------------------------------------------------

def _article_id(title: str) -> str:
    """Stable hash of the title — used for deduplication."""
    return hashlib.md5(title.strip().lower().encode()).hexdigest()


def _parse_date(entry) -> datetime | None:
    """Parse published date from feedparser entry."""
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        if hasattr(entry, "updated_parsed") and entry.updated_parsed:
            return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
    except Exception:
        pass
    return None


def _is_recent(published: datetime | None, days: int = RECENCY_DAYS) -> bool:
    """Return True if article was published within the last N days."""
    if published is None:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return published >= cutoff


def _is_relevant(title: str, summary: str, team_names: list[str]) -> bool:
    """
    Return True if title or summary mentions at least one team name.
    Case insensitive.
    """
    text = (title + " " + summary).lower()
    return any(name.lower() in text for name in team_names)


def _extract_text(entry) -> tuple[str, str]:
    """Extract title and summary from a feedparser entry."""
    title   = getattr(entry, "title",   "") or ""
    summary = getattr(entry, "summary", "") or ""

    # strip HTML tags from summary
    import re
    summary = re.sub(r"<[^>]+>", " ", summary).strip()
    summary = re.sub(r"\s+", " ", summary)

    return title.strip(), summary.strip()


# --- Main fetch function ------------------------------------------------------

def fetch_news(home_name: str, away_name: str) -> list[dict]:
    """
    Fetch and filter news articles relevant to the two teams.

    Args:
        home_name: e.g. "Mexico"
        away_name: e.g. "South Africa"

    Returns:
        List of article dicts, deduplicated and sorted newest first.
        Each dict:
        {
            "id":        str,   # md5 hash of title
            "source":    str,
            "title":     str,
            "summary":   str,
            "url":       str,
            "published": str,  # ISO format
            "teams":     list[str],
        }
    """
    team_names = [home_name, away_name]

    # also search short variants e.g. "South Africa" -> "Africa" is too broad
    # so we keep full names only
    seen_ids = set()
    articles = []

    for source_name, feed_url in FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
        except Exception:
            continue

        for entry in feed.entries:
            title, summary = _extract_text(entry)

            if not title:
                continue

            # deduplication
            article_id = _article_id(title)
            if article_id in seen_ids:
                continue

            # recency filter
            published = _parse_date(entry)
            if not _is_recent(published):
                continue

            # relevance filter
            if not _is_relevant(title, summary, team_names):
                continue

            # which teams are mentioned
            text  = (title + " " + summary).lower()
            teams = [n for n in team_names if n.lower() in text]

            seen_ids.add(article_id)
            articles.append({
                "id":        article_id,
                "source":    source_name,
                "title":     title,
                "summary":   summary[:500],   # cap at 500 chars
                "url":       getattr(entry, "link", ""),
                "published": published.isoformat() if published else None,
                "teams":     teams,
            })

    # sort newest first
    articles.sort(
        key=lambda a: a["published"] or "",
        reverse=True,
    )

    return articles