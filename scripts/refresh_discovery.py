"""Refresh source-backed discoveries using durable leases and provider ceilings."""
import argparse
import asyncio
import json

from backend.config import get_settings
from backend.services.discovery import refresh_source
from backend.services.discovery_sources import SOURCES, fetch_articles
from backend.services.storage import init_storage
import httpx


async def run(live: bool, force: bool) -> int:
    if live and get_settings().AUTO_CREATE_SCHEMA:
        init_storage()
    outcomes = []
    for source in SOURCES:
        if live:
            outcome = await refresh_source(source, force=force)
        else:
            # Source-only assessment: never calls OpenAI/Google or writes signals.
            try:
                async with httpx.AsyncClient(timeout=25, follow_redirects=False) as client:
                    articles = await fetch_articles(source, client)
                outcome = {"source": source.id, "status": "source_checked", "articles": len(articles), "licence_url": source.licence_url}
            except Exception as exc:
                outcome = {"source": source.id, "status": "source_unavailable", "error_type": type(exc).__name__}
                if isinstance(exc, httpx.HTTPStatusError):
                    outcome["http_status"] = exc.response.status_code
        outcomes.append(outcome)
        print(json.dumps(outcome))
    return int(any(item["status"] in {"error", "source_unavailable", "lease_expired"} for item in outcomes))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Ingest and match using bounded paid providers")
    parser.add_argument("--force", action="store_true", help="Ignore cadence; active leases and quotas still apply")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.live, args.force)))
