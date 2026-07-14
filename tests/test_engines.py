"""Synapse 엔진 테스트 — 실제 API 호출 (키 필요)"""
import json
import sys
import os
import time
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from orchestrator import build_engines, aggregate_search


QUERIES_PATH = os.path.join(os.path.dirname(__file__), "test_queries.json")


def load_queries():
    with open(QUERIES_PATH) as f:
        return json.load(f)


async def test_all_engines():
    """각 쿼리별로 모든 활성 엔진 테스트"""
    engines = build_engines()
    queries = load_queries()

    if not engines:
        print("⚠️  No engines configured — set API keys in .env first")
        return

    print(f"🔍 Testing {len(queries)} queries across {len(engines)} engines\n")
    print(f"   Engines: {[e.name for e in engines]}")
    print(f"   Engine timeout: {settings.engine_timeout}s")
    print(f"   Hard timeout: {settings.search_hard_timeout}s\n")

    results = {}
    for qdata in queries:
        q = qdata["query"]
        print(f"\n{'='*60}")
        print(f"📝 Query: {q}")
        print(f"   Desc: {qdata['description']}")
        print(f"{'='*60}")

        start = time.time()
        response = await aggregate_search(
            query=q,
            engines=engines,
            max_results=10,
        )
        elapsed = time.time() - start

        results[q] = {
            "total_results": len(response["results"]),
            "unresponsive_engines": response["unresponsive_engines"],
            "elapsed_seconds": round(elapsed, 2),
        }

        print(f"   Results: {len(response['results'])}")
        print(f"   Unresponsive: {response['unresponsive_engines']}")
        print(f"   Time: {elapsed:.2f}s")

        for i, r in enumerate(response["results"][:3], 1):
            print(f"   {i}. [{r['engine']}] {r['title'][:60]}")
            print(f"      {r['url'][:70]}")

    print(f"\n{'='*60}")
    print("📊 SUMMARY")
    print(f"{'='*60}")
    for q, r in results.items():
        print(f"  {q[:40]:40s} → {r['total_results']:2d} results, "
              f"{r['elapsed_seconds']:4.2f}s, "
              f"unresponsive: {r['unresponsive_engines']}")


if __name__ == "__main__":
    asyncio.run(test_all_engines())
