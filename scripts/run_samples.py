"""Run OppScout once against the real Clocked API and save outputs to samples/.

Usage: CLOCKED_API_KEY=... python scripts/run_samples.py
"""
import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.clocked import ClockedClient  # noqa: E402
from app.fetcher import fetch_text  # noqa: E402
from app.pipeline import analyze, rank  # noqa: E402

URLS = {
    "clocked_rules": "https://clocked.rezolve.ai/build-challenge/rules",
    "elevenlabs_thesearch": "https://elevenlabs.io/creative/thesearch",
}
OUT = pathlib.Path(__file__).resolve().parents[1] / "samples"


async def main():
    OUT.mkdir(exist_ok=True)
    client = ClockedClient()
    listings = []
    for name, url in URLS.items():
        text = await fetch_text(url)
        res = await analyze(text, client, source_url=url)
        (OUT / f"{name}.analysis.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
        print(name, [(s["name"], s["ok"], s.get("note"), s.get("error")) for s in res["steps"]])
        print("  verdict:", res["recommendation"])
        listings.append({"id": name, "title": (res["fields"].get("title") or {}).get("value") or name,
                         "fields": {k: v.get("value") for k, v in res["fields"].items()}, "text": res["text"][:3000]})
    ranked = await rank(listings, client)
    (OUT / "rank.json").write_text(json.dumps(ranked, indent=2, ensure_ascii=False))
    print("rank:", ranked)


if __name__ == "__main__":
    asyncio.run(main())
