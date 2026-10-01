"""Trusted source adapters. Publisher articles are never fetched or scraped."""
from __future__ import annotations

import hashlib
import html
import ipaddress
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree

import httpx

UTC = timezone.utc
MAX_SOURCE_BYTES = 1_000_000


@dataclass(frozen=True)
class Region:
    id: str
    label: str
    cities: tuple[str, ...]
    bounds: tuple[float, float, float, float]  # south, west, north, east


TORONTO = Region("toronto-gta", "Toronto & GTA", ("Toronto", "Mississauga", "Markham", "Brampton", "Vaughan", "Richmond Hill", "Oakville", "Burlington", "Ajax", "Pickering", "Whitby", "Oshawa"), (43.35, -80.0, 44.2, -78.6))
REGIONS = (TORONTO,)


@dataclass(frozen=True)
class NewsSource:
    id: str
    region: Region
    kind: str
    url: str
    licence_url: str
    approved: bool = False


SOURCES = (NewsSource("gdelt-toronto", TORONTO, "gdelt", "https://api.gdeltproject.org/api/v2/doc/doc", "https://gdeltproject.org/about.html", approved=True),)


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", value))


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def canonical_url(value: str) -> str | None:
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower().removeprefix("www.")
        if url.scheme != "https" or not host or url.username or url.password or url.port not in (None, 443):
            return None
        if host in {"localhost", "beliapp.com"} or "." not in host or host.endswith((".beliapp.com", ".local", ".internal", ".test")):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            pass
        query = [(key, val) for key, val in parse_qsl(url.query) if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}]
        path = re.sub(r"/amp/?$", "/", url.path or "/")
        result = urlunsplit(("https", host, path, urlencode(sorted(query)), ""))
        return result if len(result) <= 2048 else None
    except ValueError:
        return None


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def parse_date(value: str) -> datetime | None:
    try:
        if re.fullmatch(r"\d{8}T\d{6}Z", value):
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        return utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except (TypeError, ValueError):
        try:
            return utc(parsedate_to_datetime(value))
        except (TypeError, ValueError, OverflowError):
            return None


def plain_text(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value)).split())


@dataclass(frozen=True)
class Article:
    url: str
    title: str
    text: str
    observed_at: datetime
    published_at: datetime | None = None

    @property
    def key(self) -> str:
        return fingerprint(self.url)


def parse_gdelt(payload: dict) -> list[Article]:
    if not isinstance(payload, dict) or not isinstance(payload.get("articles"), list):
        raise ValueError("invalid_source_payload")
    result = {}
    for item in payload["articles"][:50]:
        if not isinstance(item, dict):
            continue
        url = canonical_url(str(item.get("url", "")))
        seen = parse_date(str(item.get("seendate", "")))
        title = plain_text(str(item.get("title", "")))[:240]
        if url and seen and title:
            # seendate is an index observation, never invented publisher publication time.
            result.setdefault(url, Article(url, title, title, seen))
    if payload["articles"] and not result:
        raise ValueError("invalid_source_records")
    return list(result.values())


def parse_rss(content: bytes) -> list[Article]:
    if len(content) > MAX_SOURCE_BYTES:
        raise ValueError("unsafe_feed")
    # UTF-8 only: alternate encodings cannot conceal an entity declaration.
    text = content.decode("utf-8-sig")
    if re.search(r"<!\s*(DOCTYPE|ENTITY)\b", text, re.I):
        raise ValueError("unsafe_feed")
    root = ElementTree.fromstring(text)
    if root.tag != "rss" or root.find("channel") is None:
        raise ValueError("invalid_feed")
    result = {}
    for item in root.findall(".//item")[:50]:
        url = canonical_url(item.findtext("link", ""))
        published = parse_date(item.findtext("pubDate", ""))
        title = plain_text(item.findtext("title", ""))[:240]
        description = item.findtext("description", "")
        if url and published and title:
            result.setdefault(url, Article(url, title, plain_text(f"{title} {description}")[:1040], published, published))
    return list(result.values())


async def fetch_articles(source: NewsSource, client: httpx.AsyncClient) -> list[Article]:
    # Sources are code-reviewed constants, not URLs accepted from a public request.
    if not source.approved or not canonical_url(source.url) or not canonical_url(source.licence_url):
        raise ValueError("source_not_approved")
    params = None
    if source.kind == "gdelt":
        cities = " OR ".join(f'"{city}"' for city in source.region.cities)
        params = {"query": f"(restaurant OR cafe) ({cities})", "mode": "artlist", "format": "json", "timespan": "14d", "maxrecords": 50, "sort": "DateDesc"}
    async with client.stream("GET", source.url, params=params, headers={"User-Agent": "CraveAI/1.0 (+https://github.com/yoonalexander/CraveAI)"}) as response:
        response.raise_for_status()  # redirects/403/429 are failures, not bypassed.
        chunks = bytearray()
        async for chunk in response.aiter_bytes():
            chunks.extend(chunk)
            if len(chunks) > MAX_SOURCE_BYTES:
                raise ValueError("source_too_large")
    if source.kind == "rss":
        return parse_rss(bytes(chunks))
    if source.kind == "gdelt":
        import json
        return parse_gdelt(json.loads(chunks))
    raise ValueError("unsupported_source")


# Known editorial owners, not one vote per subdomain. Unknown owners never
# establish independence; syndicated identical headlines count only once.
PUBLISHER_GROUPS = {
    "thestar.com": "torstar", "cbc.ca": "cbc", "theglobeandmail.com": "globe",
    "nationalpost.com": "postmedia", "torontosun.com": "postmedia",
    "torontolife.com": "st-joseph", "blogto.com": "zoomer", "dailyhive.com": "zoomer",
    "ctvnews.ca": "bell", "cp24.com": "bell", "globalnews.ca": "corus",
}


def publisher_group(host: str) -> str | None:
    return next((group for domain, group in PUBLISHER_GROUPS.items() if host == domain or host.endswith("." + domain)), None)
