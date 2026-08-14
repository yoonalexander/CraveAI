from __future__ import annotations

import asyncio
import html
import ipaddress
import json
import logging
import re
import socket
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Iterable, Sequence
from urllib.parse import urljoin, urlparse

import httpx

from backend.services.recommendation_models import CravingIntent, EvidenceItem

logger = logging.getLogger(__name__)

MAX_WEBSITES = 10
MAX_LINKS_PER_WEBSITE = 2
MAX_MENU_ITEMS_PER_CANDIDATE = 14
MAX_RESPONSE_BYTES = 1_500_000
MAX_REDIRECTS = 3
FETCH_TIMEOUT_SECONDS = 5.0

_SKIP_TAGS = {"script", "style", "svg", "noscript", "template"}
_MENU_LINK_WORDS = ("menu", "order", "food", "dishes")
_STOPWORDS = {
    "and",
    "but",
    "for",
    "from",
    "have",
    "like",
    "maybe",
    "nearby",
    "not",
    "something",
    "that",
    "the",
    "this",
    "want",
    "with",
}


@dataclass
class ParsedPage:
    menu_items: list[tuple[str, str]] = field(default_factory=list)
    visible_blocks: list[str] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)


class _MenuHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_json_ld = False
        self._json_parts: list[str] = []
        self._json_documents: list[str] = []
        self._active_href: str | None = None
        self._active_link_text: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.visible_blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and (attributes.get("type") or "").lower() == "application/ld+json":
            self._in_json_ld = True
            self._json_parts = []
            return
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "a" and self._skip_depth == 0:
            self._active_href = attributes.get("href")
            self._active_link_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_json_ld:
            self._json_documents.append("".join(self._json_parts))
            self._in_json_ld = False
            self._json_parts = []
            return
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "a" and self._active_href is not None:
            text = _clean_text(" ".join(self._active_link_text), 160)
            self.links.append((self._active_href, text))
            self._active_href = None
            self._active_link_text = []

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._json_parts.append(data)
            return
        if self._skip_depth:
            return
        cleaned = _clean_text(data, 350)
        if len(cleaned) < 2:
            return
        self.visible_blocks.append(cleaned)
        if self._active_href is not None:
            self._active_link_text.append(cleaned)

    def parsed(self) -> ParsedPage:
        items: list[tuple[str, str]] = []
        for document in self._json_documents:
            try:
                payload = json.loads(document)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            _walk_json_ld(payload, items)
        return ParsedPage(
            menu_items=_deduplicate_menu_items(items),
            visible_blocks=_deduplicate_text(self.visible_blocks),
            links=self.links,
        )


async def enrich_candidates_with_menu_evidence(
    candidates: list[dict[str, Any]],
    intent: CravingIntent,
) -> list[dict[str, Any]]:
    """Fetch official sites ephemerally and attach bounded dish/menu evidence."""
    crawlable = [item for item in candidates if item.get("website")][:MAX_WEBSITES]
    if not crawlable:
        return candidates

    semaphore = asyncio.Semaphore(5)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(FETCH_TIMEOUT_SECONDS),
        follow_redirects=False,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "CraveAI/1.0 (+menu evidence for user-initiated recommendations)",
        },
    ) as client:
        tasks = [
            _enrich_one(client, semaphore, candidate, intent)
            for candidate in crawlable
        ]
        await asyncio.gather(*tasks)
    return candidates


async def _enrich_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    candidate: dict[str, Any],
    intent: CravingIntent,
) -> None:
    website = str(candidate.get("website") or "").strip()
    if not website:
        return
    try:
        async with semaphore:
            home_url, home_html = await _safe_fetch_html(client, website)
            home_page = _parse_html(home_html)
            pages: list[tuple[str, ParsedPage, bool]] = [
                (home_url, home_page, _looks_like_menu_url(home_url))
            ]
            links = _select_menu_links(home_page.links, home_url)
            for link in links[:MAX_LINKS_PER_WEBSITE]:
                try:
                    page_url, page_html = await _safe_fetch_html(client, link)
                    if _same_document(page_url, home_url):
                        continue
                    pages.append((page_url, _parse_html(page_html), True))
                except Exception as exc:
                    logger.info(
                        "menu_evidence place_id=%s outcome=skipped error_type=%s",
                        candidate.get("place_id"),
                        type(exc).__name__,
                    )
    except Exception as exc:
        logger.info(
            "menu_evidence place_id=%s outcome=unavailable error_type=%s",
            candidate.get("place_id"),
            type(exc).__name__,
        )
        return

    all_menu_items: list[tuple[str, str, str]] = []
    all_blocks: list[tuple[str, str]] = []
    for page_url, page, is_menu_context in pages:
        all_menu_items.extend((name, description, page_url) for name, description in page.menu_items)
        if is_menu_context:
            all_blocks.extend((block, page_url) for block in page.visible_blocks)

    selected_items = _select_relevant_items(all_menu_items, intent)
    evidence: list[dict[str, Any]] = list(candidate.get("evidence") or [])
    for name, description, source_url in selected_items:
        evidence.append(
            EvidenceItem(
                id="pending",
                kind="official_menu",
                label=name,
                detail=description,
                source_url=source_url,
                quality=1.0,
            ).model_dump()
        )

    if not selected_items:
        for block, source_url in _select_relevant_blocks(all_blocks, intent)[:6]:
            evidence.append(
                EvidenceItem(
                    id="pending",
                    kind="official_website",
                    label=block,
                    source_url=source_url,
                    quality=0.8,
                ).model_dump()
            )

    candidate["evidence"] = _deduplicate_evidence(evidence)
    _assign_evidence_ids(candidate)


async def _safe_fetch_html(
    client: httpx.AsyncClient,
    url: str,
) -> tuple[str, str]:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        await _validate_public_url(current)
        async with client.stream("GET", current) as response:
            if response.status_code in {301, 302, 303, 307, 308}:
                target = response.headers.get("location")
                if not target:
                    raise ValueError("Redirect did not provide a location.")
                current = urljoin(current, target)
                continue
            response.raise_for_status()
            content_type = (response.headers.get("content-type") or "").lower()
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                raise ValueError(f"Unsupported menu content type: {content_type or 'unknown'}")
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise ValueError("Menu page exceeded the response size limit.")
                chunks.append(chunk)
            encoding = response.encoding or "utf-8"
            return str(response.url), b"".join(chunks).decode(encoding, errors="replace")
    raise ValueError("Menu page exceeded the redirect limit.")


async def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public HTTP(S) menu URLs are allowed.")
    if parsed.username or parsed.password:
        raise ValueError("Credential-bearing menu URLs are not allowed.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid menu URL port.") from exc
    if port not in {None, 80, 443}:
        raise ValueError("Non-standard menu URL ports are not allowed.")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("Local menu URLs are not allowed.")

    try:
        literal_ip = ipaddress.ip_address(hostname)
        addresses = [literal_ip]
    except ValueError:
        loop = asyncio.get_running_loop()
        resolved = await loop.run_in_executor(
            None,
            lambda: socket.getaddrinfo(hostname, port or (443 if parsed.scheme == "https" else 80)),
        )
        addresses = []
        for result in resolved:
            try:
                addresses.append(ipaddress.ip_address(result[4][0]))
            except ValueError:
                continue
    if not addresses or any(not _is_public_ip(address) for address in addresses):
        raise ValueError("Menu URL resolved to a non-public network address.")


def _is_public_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _parse_html(source: str) -> ParsedPage:
    parser = _MenuHTMLParser()
    parser.feed(source)
    return parser.parsed()


def _walk_json_ld(value: Any, items: list[tuple[str, str]]) -> None:
    if isinstance(value, dict):
        raw_type = value.get("@type")
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        if any(item_type in {"MenuItem", "Product"} for item_type in types):
            name = _clean_text(str(value.get("name") or ""), 180)
            description = _clean_text(str(value.get("description") or ""), 320)
            if name:
                items.append((name, description))
        for child in value.values():
            _walk_json_ld(child, items)
    elif isinstance(value, list):
        for child in value:
            _walk_json_ld(child, items)


def _select_menu_links(links: Sequence[tuple[str, str]], base_url: str) -> list[str]:
    scored: list[tuple[int, str]] = []
    seen_documents: set[str] = set()
    for href, anchor_text in links:
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        haystack = f"{href} {anchor_text}".lower()
        if not any(word in haystack for word in _MENU_LINK_WORDS):
            continue
        absolute = urljoin(base_url, href)
        document_key = _document_key(absolute)
        if document_key in seen_documents:
            continue
        seen_documents.add(document_key)
        anchor = anchor_text.lower()
        path = urlparse(absolute).path.lower()
        if "menu" in anchor:
            score = 0
        elif "menu" in path:
            score = 1
        elif "order" in anchor:
            score = 2
        elif "order" in path:
            score = 3
        else:
            score = 5
        if urlparse(absolute).netloc != urlparse(base_url).netloc:
            score += 1
        scored.append((score, absolute))
    scored.sort(key=lambda item: item[0])
    return [item for _, item in scored]


def _select_relevant_items(
    items: Sequence[tuple[str, str, str]],
    intent: CravingIntent,
) -> list[tuple[str, str, str]]:
    terms = _intent_terms(intent)
    scored: list[tuple[float, tuple[str, str, str]]] = []
    for item in items:
        name, description, _ = item
        score = _lexical_score(f"{name} {description}", terms)
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    selected: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for _, item in scored:
        key = _normalize(item[0])
        if key in seen:
            continue
        seen.add(key)
        selected.append(item)
        if len(selected) >= MAX_MENU_ITEMS_PER_CANDIDATE:
            break
    return selected


def _select_relevant_blocks(
    blocks: Sequence[tuple[str, str]],
    intent: CravingIntent,
) -> list[tuple[str, str]]:
    terms = _intent_terms(intent)
    windows: list[tuple[str, str]] = []
    for block, source_url in blocks:
        if len(block) > 240:
            continue
        windows.append((block, source_url))
    scored = [
        (_lexical_score(block, terms), block, source_url)
        for block, source_url in windows
    ]
    scored = [item for item in scored if item[0] > 0]
    scored.sort(key=lambda item: item[0], reverse=True)
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for _, block, source_url in scored:
        key = _normalize(block)
        if key in seen:
            continue
        seen.add(key)
        result.append((block, source_url))
    return result


def _intent_terms(intent: CravingIntent) -> list[str]:
    values = [item.value for item in intent.constraints]
    values.extend(intent.candidate_dishes)
    values.extend(item.text for item in intent.search_queries)
    return _deduplicate_text([_normalize(value) for value in values if value])


def _lexical_score(text: str, terms: Sequence[str]) -> float:
    normalized = _normalize(text)
    tokens = set(normalized.split())
    score = 0.0
    for term in terms:
        term_tokens = [token for token in term.split() if token not in _STOPWORDS]
        if not term_tokens:
            continue
        overlap = sum(1 for token in term_tokens if token in tokens)
        score += overlap / len(term_tokens)
        if term in normalized:
            score += 1.2
    return score


def _deduplicate_menu_items(
    items: Iterable[tuple[str, str]],
) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, description in items:
        key = _normalize(name)
        if key and key not in seen:
            seen.add(key)
            result.append((name, description))
    return result


def _deduplicate_text(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean_text(html.unescape(value), 420)
        key = _normalize(cleaned)
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _deduplicate_evidence(values: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        key = (str(value.get("kind")), _normalize(str(value.get("label") or "")))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _assign_evidence_ids(candidate: dict[str, Any]) -> None:
    place_id = candidate.get("place_id") or "place"
    for index, evidence in enumerate(candidate.get("evidence") or [], start=1):
        evidence["id"] = f"{place_id}:e{index}"


def _looks_like_menu_url(url: str) -> bool:
    parsed = urlparse(url)
    haystack = f"{parsed.netloc} {parsed.path}".lower()
    return any(word in haystack for word in ("menu", "order", "chownow", "restosuite"))


def _document_key(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/') or '/'}"


def _same_document(left: str, right: str) -> bool:
    return _document_key(left) == _document_key(right)


def _clean_text(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s-]", " ", value.lower())).strip()
