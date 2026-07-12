"""News / disclosure collectors: earnings, IR, Nikkei, Reuters, Bloomberg, SEC, SNS."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import NewsArticle
from app.services.ingestion import DataIngestionService

# Public RSS / free endpoints (licenses apply; replace with paid feeds in production)
RSS_FEEDS: dict[str, dict[str, str]] = {
    "reuters": {
        "url": "https://feeds.reuters.com/reuters/businessNews",
        "category": "news",
    },
    "nikkei_proxy": {
        # Nikkei full feed requires subscription; use Google News Nikkei query as research proxy
        "url": "https://news.google.com/rss/search?q=%E6%97%A5%E6%9C%AC%E7%B5%8C%E6%B8%88%E6%96%B0%E8%81%9E&hl=ja&gl=JP&ceid=JP:ja",
        "category": "news",
    },
    "bloomberg_proxy": {
        "url": "https://news.google.com/rss/search?q=Bloomberg+markets&hl=en-US&gl=US&ceid=US:en",
        "category": "news",
    },
    "earnings": {
        "url": "https://news.google.com/rss/search?q=%E6%B1%BA%E7%AE%97+OR+earnings&hl=ja&gl=JP&ceid=JP:ja",
        "category": "earnings",
    },
    "ir_disclosure": {
        "url": "https://news.google.com/rss/search?q=%E9%81%A9%E6%99%82%E9%96%8B%E7%A4%BA+OR+IR&hl=ja&gl=JP&ceid=JP:ja",
        "category": "ir",
    },
}


async def fetch_rss(source: str, url: str, category: str, limit: int = 20) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.text)
    items = []
    for e in parsed.entries[:limit]:
        published = None
        if getattr(e, "published_parsed", None):
            published = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
        items.append(
            {
                "source": source,
                "category": category,
                "title": e.get("title") or "",
                "url": e.get("link"),
                "published_at": published,
                "raw_text": e.get("summary") or e.get("description") or "",
            }
        )
    return items


async def fetch_sec_filings(ticker: str, limit: int = 10) -> list[dict[str, Any]]:
    """SEC EDGAR recent filings (US tickers). Japanese tickers return empty."""
    # Map Yahoo-style ticker to bare symbol for SEC
    symbol = ticker.split(".")[0].upper()
    if ticker.endswith(".T"):
        return []
    url = (
        "https://data.sec.gov/submissions/CIK{cik}.json"
    )
    # Resolve CIK via company tickers JSON
    async with httpx.AsyncClient(
        timeout=30,
        headers={"User-Agent": "StockAI research bot contact@example.com"},
    ) as client:
        tickers = await client.get("https://www.sec.gov/files/company_tickers.json")
        tickers.raise_for_status()
        data = tickers.json()
        cik = None
        for row in data.values():
            if str(row.get("ticker", "")).upper() == symbol:
                cik = str(row["cik_str"]).zfill(10)
                break
        if not cik:
            return []
        sub = await client.get(url.format(cik=cik))
        sub.raise_for_status()
        recent = sub.json().get("filings", {}).get("recent", {})
    items = []
    forms = recent.get("form", [])
    for i in range(min(limit, len(forms))):
        items.append(
            {
                "source": "sec",
                "category": "sec_filing",
                "title": f"{symbol} {forms[i]} — {recent.get('primaryDocDescription', [''])[i] if recent.get('primaryDocDescription') else forms[i]}",
                "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{recent['accessionNumber'][i].replace('-', '')}/{recent['primaryDocument'][i]}",
                "published_at": datetime.fromisoformat(recent["filingDate"][i]).replace(tzinfo=timezone.utc),
                "raw_text": f"SEC filing {forms[i]} filed on {recent['filingDate'][i]}",
            }
        )
    return items


async def fetch_finnhub_news(ticker: str, limit: int = 20) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.finnhub_api_key:
        return []
    symbol = ticker.replace(".T", ".T")  # keep JP suffix; Finnhub may need mapping
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            "https://finnhub.io/api/v1/company-news",
            params={
                "symbol": symbol.split(".")[0],
                "from": "2024-01-01",
                "to": datetime.now(timezone.utc).date().isoformat(),
                "token": settings.finnhub_api_key,
            },
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    items = []
    for row in data[:limit]:
        items.append(
            {
                "source": "finnhub",
                "category": "news",
                "title": row.get("headline") or "",
                "url": row.get("url"),
                "published_at": datetime.fromtimestamp(row.get("datetime", 0), tz=timezone.utc),
                "raw_text": row.get("summary") or "",
            }
        )
    return items


async def fetch_sns_mentions(ticker: str) -> list[dict[str, Any]]:
    """X/Twitter mentions — requires bearer token; returns placeholder when unset."""
    settings = get_settings()
    if not settings.x_bearer_token:
        return [
            {
                "source": "sns",
                "category": "sns",
                "title": f"[stub] SNS mentions for {ticker}",
                "url": None,
                "published_at": datetime.now(timezone.utc),
                "raw_text": f"Configure X_BEARER_TOKEN to pull live social mentions for {ticker}.",
            }
        ]
    query = ticker.split(".")[0]
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            "https://api.twitter.com/2/tweets/search/recent",
            params={"query": query, "max_results": 10},
            headers={"Authorization": f"Bearer {settings.x_bearer_token}"},
        )
        if resp.status_code != 200:
            return []
        data = resp.json().get("data") or []
    return [
        {
            "source": "sns",
            "category": "sns",
            "title": (t.get("text") or "")[:120],
            "url": f"https://x.com/i/web/status/{t['id']}",
            "published_at": datetime.now(timezone.utc),
            "raw_text": t.get("text") or "",
        }
        for t in data
    ]


class NewsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.ingestion = DataIngestionService(db)

    async def collect(self, ticker: str | None = None) -> dict:
        articles: list[dict[str, Any]] = []
        for name, cfg in RSS_FEEDS.items():
            try:
                articles.extend(await fetch_rss(name, cfg["url"], cfg["category"]))
            except Exception as e:
                articles.append(
                    {
                        "source": name,
                        "category": cfg["category"],
                        "title": f"fetch error: {e}",
                        "url": None,
                        "published_at": datetime.now(timezone.utc),
                        "raw_text": str(e),
                    }
                )
        if ticker:
            articles.extend(await fetch_sec_filings(ticker))
            articles.extend(await fetch_finnhub_news(ticker))
            articles.extend(await fetch_sns_mentions(ticker))

        symbol_id = None
        if ticker:
            sym = await self.ingestion.ensure_symbol(ticker)
            symbol_id = sym.id

        saved = 0
        for a in articles:
            if not a.get("title"):
                continue
            self.db.add(
                NewsArticle(
                    symbol_id=symbol_id,
                    source=a["source"],
                    category=a["category"],
                    title=a["title"],
                    url=a.get("url"),
                    published_at=a.get("published_at"),
                    raw_text=a.get("raw_text"),
                )
            )
            saved += 1
        await self.db.commit()
        return {"saved": saved, "sources": sorted({a["source"] for a in articles})}
