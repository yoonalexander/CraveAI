"""Run a resumable first pass over independently sourced catalog websites."""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urldefrag, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from scripts.import_restaurant_catalog import SNAPSHOT, read_catalog_rows
from scripts.probe_menu_index import probe

USER_AGENT = "CraveAI"
ROBOTS_LIMIT = 512_000


class RobotsPolicy:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.rules = {}
        self.locks = defaultdict(asyncio.Lock)

    async def _read(self, origin: str) -> RobotFileParser:
        rules = RobotFileParser()
        async with self.client.stream("GET", f"{origin}/robots.txt") as response:
            if response.status_code in (404, 410):
                rules.allow_all = True
            elif response.status_code != 200:
                raise ValueError("Robots policy unavailable")
            else:
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > ROBOTS_LIMIT:
                        raise ValueError("Robots policy exceeded size limit")
                lines = data.decode("utf-8-sig", errors="replace").splitlines()
                # The standard library understands prefixes. Treat wildcard
                # disallows conservatively as disallows on their known prefix.
                rules.parse([
                    re.split(r"[*$]", line, maxsplit=1)[0]
                    if line.lstrip().lower().startswith("disallow:") else line
                    for line in lines
                ])
        return rules

    async def check(self, url: str) -> None:
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        async with self.locks[parsed.hostname]:
            if origin not in self.rules:
                try:
                    self.rules[origin] = await self._read(origin)
                except (httpx.RequestError, ValueError):
                    self.rules[origin] = None
            rules = self.rules[origin]
            if rules is None:
                raise ValueError("Robots policy unavailable")
            if not rules.can_fetch(USER_AGENT, url):
                raise ValueError("Robots policy disallows menu URL")
            await asyncio.sleep(max(0.25, rules.crawl_delay(USER_AGENT) or 0))


async def run(output: Path, workers: int, checked_on: str) -> None:
    finished = set()
    if output.exists():
        with output.open(encoding="utf-8") as previous:
            finished = {json.loads(line)["restaurant_id"] for line in previous if line.strip()}
    sites = defaultdict(lambda: defaultdict(list))
    missing = []
    for row in read_catalog_rows(SNAPSHOT):
        if not row["listed"] or row["id"] in finished:
            continue
        url = urldefrag(row["website"]).url
        if url:
            sites[urlsplit(url).hostname.removeprefix("www.")][url].append(row)
        else:
            missing.append(row)

    pdf_tool = shutil.which("pdftotext")
    queue = asyncio.Queue()
    for urls in sites.values():
        queue.put_nowait(urls)
    with output.open("a", encoding="utf-8", buffering=1) as report:
        def record(row, outcome, candidates=0, docs=None, issues=None):
            report.write(json.dumps({
                "restaurant_id": row["id"], "checked_on": checked_on,
                "outcome": outcome, "candidates": candidates,
                "documents": docs or {}, "issues": issues or {},
            }, ensure_ascii=True, separators=(",", ":")) + "\n")

        for row in missing:
            record(row, "no_website")
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5), follow_redirects=False, trust_env=False,
            headers={"User-Agent": f"{USER_AGENT}/1.0 (public restaurant menu availability)"},
        ) as client:
            policy = RobotsPolicy(client)

            async def worker():
                while not queue.empty():
                    urls = queue.get_nowait()
                    for rows in urls.values():
                        result = await probe(client, rows[0], pdf_tool, before_fetch=policy.check)
                        candidates = result["candidates"]
                        outcome = "candidates" if candidates else "no_readable_dishes"
                        if not candidates and result["issues"]:
                            outcome = "source_issue"
                        for row in rows:
                            record(row, outcome, candidates, result["documents"], result["issues"])

            await asyncio.gather(*(worker() for _ in range(workers)))
    print(f"Checked {len(missing)} listings without websites and {sum(map(len, sites.values()))} website URLs.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checked-on", type=date.fromisoformat, required=True)
    parser.add_argument("--workers", type=int, choices=range(1, 33), default=16, metavar="1-32")
    args = parser.parse_args()
    asyncio.run(run(args.output, args.workers, args.checked_on.isoformat()))


if __name__ == "__main__":
    main()
