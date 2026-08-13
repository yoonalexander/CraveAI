"""Quick latency benchmark for the FastAPI chat endpoint.

The benchmark swaps in a lightweight recommendation pipeline so that we can
measure HTTP request overhead and serialization latency without incurring
external API calls. It is intended to verify that the service framework
responds in under a second on a typical developer laptop.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

from httpx import ASGITransport, AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# Keep this local harness independent from production secrets and services.
os.environ["APP_ENV"] = "test"
_BENCHMARK_TEMP_DIR = tempfile.TemporaryDirectory(prefix="craveai-benchmark-")
_BENCHMARK_DB = Path(_BENCHMARK_TEMP_DIR.name, "benchmark.db").as_posix()
os.environ["DATABASE_URL"] = f"sqlite:///{_BENCHMARK_DB}"
os.environ.setdefault("OPENAI_API_KEY", "benchmark-openai")
os.environ.setdefault("GOOGLE_API_KEY", "benchmark-google")

from backend.main import create_app
from backend.database import reset_database_cache
from backend.routers import chat
from backend.services import rag_pipeline
from backend.services.storage import init_storage


async def _fake_generate_recommendations(*_args, **_kwargs):
    """Simulate RAG output with a short delay to mimic processing cost."""
    await asyncio.sleep(0.05)
    return {
        "reply": "Testing latency pipeline response.",
        "recommendations": [
            {
                "name": "Benchmark Bistro",
                "rating": 4.7,
                "address": "123 Sample Street",
                "reason": "Synthetic result for timing harness.",
                "lat": 43.6532,
                "lng": -79.3832,
            }
        ],
    }


async def run_benchmark(iterations: int) -> list[float]:
    """Execute the /chat endpoint multiple times and capture durations in ms."""
    init_storage()
    rag_pipeline.generate_recommendations = _fake_generate_recommendations  # type: ignore[assignment]
    chat.generate_recommendations = _fake_generate_recommendations  # type: ignore[assignment]
    app = create_app()
    timings: list[float] = []
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        payload = {
            "query": "Need something warm nearby.",
            "location": {"lat": 43.6532, "lng": -79.3832},
        }
        for _ in range(iterations):
            start = time.perf_counter()
            response = await client.post("/chat", json=payload)
            response.raise_for_status()
            timings.append((time.perf_counter() - start) * 1000)
    return timings


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark /chat latency.")
    parser.add_argument(
        "-n",
        "--iterations",
        type=int,
        default=10,
        help="Number of requests to issue (default: 10).",
    )
    args = parser.parse_args()

    try:
        timings = asyncio.run(run_benchmark(args.iterations))
        avg = statistics.mean(timings)
        p95 = statistics.quantiles(timings, n=20)[18] if len(timings) >= 20 else max(timings)
        print(f"Ran {len(timings)} requests.")
        print(f"Average latency: {avg:.2f} ms")
        print(f"Max latency: {max(timings):.2f} ms")
        print(f"p95 latency: {p95:.2f} ms")
    finally:
        reset_database_cache()
        _BENCHMARK_TEMP_DIR.cleanup()


if __name__ == "__main__":
    main()
