"""On-demand Places photos. Never persist or cache expiring photo resource names."""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from urllib.parse import parse_qsl, unquote, urlsplit

import httpx

from backend.config import get_settings


class PhotoProviderError(Exception):
    """Sanitized failure; provider URLs and credentials must not reach clients/logs."""


def safe_google_uri(value: object, *, image: bool = False) -> str | None:
    if not isinstance(value, str) or len(value) > 8192:
        return None
    uri = "https:" + value if value.startswith("//") else value
    try:
        parsed = urlsplit(uri)
        host = (parsed.hostname or "").lower()
        domains = ("googleusercontent.com", "ggpht.com") if image else ("google.com", "maps.app.goo.gl")
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            return None
        if not any(host == domain or host.endswith("." + domain) for domain in domains):
            return None
        if any(key.lower() in {"key", "api_key", "apikey", "x-goog-api-key"} for key, _ in parse_qsl(parsed.query)):
            return None
        secret = get_settings().GOOGLE_API_KEY
        if secret and secret in unquote(uri):
            return None
    except ValueError:
        return None
    return uri


async def fetch_place_photo(
    place_id: str, index: int, *, before_request: Callable[[], Awaitable[None]] | None = None,
) -> dict:
    """Refresh only id/photos, resolve a single image, and return display-only data."""
    settings = get_settings()
    headers = {"X-Goog-Api-Key": settings.GOOGLE_API_KEY}
    async def reserve() -> None:
        if before_request:
            await before_request()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(6.0), follow_redirects=False) as client:
            await reserve()
            details = await client.get(
                f"https://places.googleapis.com/v1/places/{place_id}",
                headers={**headers, "X-Goog-FieldMask": "id,photos"},
            )
            details.raise_for_status()
            data = details.json()
            if data.get("id") != place_id:
                raise PhotoProviderError()
            photos = data.get("photos") or []
            if not isinstance(photos, list):
                raise PhotoProviderError()
            photos = photos[:10]
            if not photos:
                return {"place_id": place_id, "index": 0, "total": 0, "photo": None}
            index = min(index, len(photos) - 1)
            selected = photos[index]
            name = selected.get("name", "")
            # A provider response must never attach another venue's photo.
            if not isinstance(name, str) or not re.fullmatch(rf"places/{re.escape(place_id)}/photos/[A-Za-z0-9_=-]{{1,4096}}", name):
                raise PhotoProviderError()
            await reserve()
            media = await client.get(
                f"https://places.googleapis.com/v1/{name}/media", headers=headers,
                params={"maxWidthPx": 800, "maxHeightPx": 600, "skipHttpRedirect": "true"},
            )
            media.raise_for_status()
            uri = safe_google_uri(media.json().get("photoUri"), image=True)
            if not uri:
                raise PhotoProviderError()
            authors = [{
                "name": author.get("displayName") or "Photo contributor",
                "uri": safe_google_uri(author.get("uri")),
                "avatar_uri": safe_google_uri(author.get("photoUri"), image=True),
            } for author in selected.get("authorAttributions", [])]
            return {"place_id": place_id, "index": index, "total": len(photos), "photo": {
                "uri": uri, "authors": authors,
                "source_uri": safe_google_uri(selected.get("googleMapsUri")),
                "report_uri": safe_google_uri(selected.get("flagContentUri")),
            }}
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        raise PhotoProviderError() from exc
