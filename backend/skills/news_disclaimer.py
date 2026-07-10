"""PA-62 — News via RSS: "what's the news" / "top headlines"."""
from __future__ import annotations
import xml.etree.ElementTree as ET

from backend.core.http_client import get as http_get

META = {
    "name": "news_disclaimer",
    "description": "Fetches the latest headlines from BBC News RSS.",
    "triggers": [
        "what's the news",
        "what is the news",
        "any news",
        "news today",
        "what is happening",
        "what's happening in the world",
        "what war",
        "current events",
        "latest news",
        "top headlines",
        "top news",
        "news headlines",
    ],
}

_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.bbci.co.uk/news/rss.xml",
]


def _parse_headlines(xml_text: str, max_items: int = 3) -> list[str]:
    root = ET.fromstring(xml_text)
    titles = []
    for item in root.findall(".//item"):
        t = item.find("title")
        if t is not None and t.text:
            titles.append(t.text.strip())
        if len(titles) >= max_items:
            break
    return titles


def run(args: dict | None = None) -> str:
    for feed_url in _FEEDS:
        try:
            resp = http_get(feed_url)
            resp.raise_for_status()
            headlines = _parse_headlines(resp.text)
            if headlines:
                if len(headlines) == 1:
                    return f"Top headline: {headlines[0]}."
                items = "; ".join(headlines[:-1]) + f"; and {headlines[-1]}."
                return f"Top {len(headlines)} headlines: {items}"
        except Exception:
            continue
    return "I couldn't fetch the latest news right now."


def self_test() -> bool:
    sample = (
        '<?xml version="1.0"?><rss><channel>'
        "<item><title>Headline one</title></item>"
        "<item><title>Headline two</title></item>"
        "</channel></rss>"
    )
    titles = _parse_headlines(sample)
    return titles == ["Headline one", "Headline two"]
