"""Quick latency benchmark for the FastAPI chat endpoint.

The benchmark swaps in a lightweight recommendation pipeline so that we can
measure HTTP request overhead and serialization latency without incurring
external API calls. It is intended to verify that the service framework
responds in under a second on a typical developer laptop.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path
from types import ModuleType

from httpx import AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))


def _install_langchain_stubs() -> None:
    """Provide lightweight stand-ins so imports succeed without heavy deps."""
    if "langchain_core" not in sys.modules:
        langchain_core_module = ModuleType("langchain_core")
        sys.modules["langchain_core"] = langchain_core_module

        class DummyChain:
            def __init__(self, *components):
                self.components = list(components)

            def __or__(self, other):
                self.components.append(other)
                return self

            async def ainvoke(self, *_args, **_kwargs):
                return "{}"

        class DummyStrOutputParser:
            def __ror__(self, other):
                return DummyChain(other, self)

            async def ainvoke(self, *_args, **_kwargs):
                return "{}"

        output_parsers_module = ModuleType("langchain_core.output_parsers")
        output_parsers_module.StrOutputParser = DummyStrOutputParser
        sys.modules["langchain_core.output_parsers"] = output_parsers_module

        class DummyPromptTemplate:
            @classmethod
            def from_messages(cls, messages):
                instance = cls()
                instance.messages = messages
                return instance

            def __or__(self, other):
                return DummyChain(self, other)

        prompts_module = ModuleType("langchain_core.prompts")
        prompts_module.ChatPromptTemplate = DummyPromptTemplate
        sys.modules["langchain_core.prompts"] = prompts_module

    if "langchain_openai" not in sys.modules:
        langchain_openai_module = ModuleType("langchain_openai")

        class DummyChatOpenAI:
            def __init__(self, *args, **kwargs):
                pass

            async def ainvoke(self, *_args, **_kwargs):
                return "{}"

        class DummyOpenAIEmbeddings:
            def __init__(self, *args, **kwargs):
                pass

        langchain_openai_module.ChatOpenAI = DummyChatOpenAI
        langchain_openai_module.OpenAIEmbeddings = DummyOpenAIEmbeddings
        sys.modules["langchain_openai"] = langchain_openai_module

    if "langchain_community" not in sys.modules:
        langchain_community_module = ModuleType("langchain_community")
        vectorstores_module = ModuleType("langchain_community.vectorstores")

        class DummyChroma:
            def __init__(self, *args, **kwargs):
                pass

            def similarity_search(self, *_args, **_kwargs):
                return []

        vectorstores_module.Chroma = DummyChroma
        langchain_community_module.vectorstores = vectorstores_module
        sys.modules["langchain_community"] = langchain_community_module
        sys.modules["langchain_community.vectorstores"] = vectorstores_module


_install_langchain_stubs()

from backend.main import create_app
from backend.services import rag_pipeline


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
    rag_pipeline.generate_recommendations = _fake_generate_recommendations  # type: ignore[assignment]
    app = create_app()
    timings: list[float] = []
    async with AsyncClient(app=app, base_url="http://testserver") as client:
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

    timings = asyncio.run(run_benchmark(args.iterations))
    avg = statistics.mean(timings)
    p95 = statistics.quantiles(timings, n=20)[18] if len(timings) >= 20 else max(timings)
    print(f"Ran {len(timings)} requests.")
    print(f"Average latency: {avg:.2f} ms")
    print(f"Max latency: {max(timings):.2f} ms")
    print(f"p95 latency: {p95:.2f} ms")


if __name__ == "__main__":
    main()
