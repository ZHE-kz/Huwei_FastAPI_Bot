import html
import re
import time
import urllib.parse


ARCHIVE_ARTICLES_URL = "https://nfu-digital-archive.zheforge.com/api/articles"
ARCHIVE_COLLECTION_URL = "https://nfu-digital-archive.zheforge.com/collection"
ARCHIVE_CACHE_SECONDS = 5 * 60
_articles_cache = []
_cache_until = 0.0


def build_archive_url(article: dict) -> str:
    slug = str(article.get("slug", "")).strip()
    if not slug:
        return ""
    return f"{ARCHIVE_COLLECTION_URL}?slug={urllib.parse.quote(slug, safe='')}"


def _plain_text(value) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def _query_terms(query: str) -> set[str]:
    normalized = _plain_text(query).casefold()
    terms = set(re.findall(r"[a-z0-9][a-z0-9_-]+", normalized))
    for run in re.findall(r"[\u3400-\u9fff]+", normalized):
        for size in (2, 3, 4):
            terms.update(run[index:index + size] for index in range(len(run) - size + 1))
    return {term for term in terms if len(term) >= 2}


def search_articles(articles: list, query: str, limit: int = 4) -> list[dict]:
    terms = _query_terms(query)
    if not terms:
        return []
    ranked = []
    normalized_query = _plain_text(query).casefold()
    requested_categories = set()
    category_aliases = {
        "history": ("歷史", "史蹟", "古蹟"),
        "nature-museum": ("自然博物館", "自然館藏", "農產", "農業"),
        "merchant": ("商家", "店家", "店舖", "餅店"),
    }
    for category, aliases in category_aliases.items():
        if any(alias in normalized_query for alias in aliases):
            requested_categories.add(category)
    for article in articles:
        if not isinstance(article, dict):
            continue
        title = _plain_text(article.get("title")).casefold()
        category = _plain_text(article.get("category")).casefold()
        fields = {
            "title": title,
            "summary": _plain_text(article.get("summary")).casefold(),
            "content": _plain_text(article.get("content")).casefold(),
            "metadata": _plain_text(
                " ".join(
                    str(article.get(name, ""))
                    for name in ("tag", "category", "collection_type", "period", "location_name", "source")
                )
            ).casefold(),
        }
        score = 50 if title and title in normalized_query else 0
        if category in requested_categories:
            score += 40
        for term in terms:
            score += (12 if term in fields["title"] else 0)
            score += (5 if term in fields["summary"] else 0)
            score += (2 if term in fields["metadata"] else 0)
            score += (1 if term in fields["content"] else 0)
        if score:
            ranked.append((score, article))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [article for _, article in ranked[:limit]]


async def retrieve_archive_articles(client, query: str, limit: int = 4) -> list[dict]:
    global _articles_cache, _cache_until
    now = time.monotonic()
    if now >= _cache_until:
        try:
            response = await client.get(ARCHIVE_ARTICLES_URL, timeout=10)
            response.raise_for_status()
            articles = response.json().get("articles", [])
            if isinstance(articles, list):
                _articles_cache = articles
                _cache_until = now + ARCHIVE_CACHE_SECONDS
        except Exception as error:
            print(f"[ARCHIVE] 讀取館藏失敗，使用既有快取: {error}")
    return search_articles(_articles_cache, query, limit)


def format_archive_context(articles: list[dict]) -> str:
    records = []
    for article in articles:
        records.append(
            "\n".join(
                [
                    f"Title: {_plain_text(article.get('title'))}",
                    f"Category: {_plain_text(article.get('category'))}",
                    f"Type: {_plain_text(article.get('collection_type'))}",
                    f"Period: {_plain_text(article.get('period'))}",
                    f"Location: {_plain_text(article.get('location_name'))}",
                    f"Summary: {_plain_text(article.get('summary'))[:800]}",
                    f"Content: {_plain_text(article.get('content'))[:1800]}",
                    f"Source: {build_archive_url(article)}",
                ]
            )
        )
    return "\n\n---\n\n".join(records)
