"""OppScout FastAPI app."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .clocked import ClockedClient
from .fetcher import FetchError, fetch_text, MAX_CHARS
from .pipeline import DEFAULT_PROFILE, analyze, rank

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="OppScout", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def get_client() -> ClockedClient:
    return ClockedClient()


class AnalyzeIn(BaseModel):
    url: Optional[str] = None
    text: Optional[str] = Field(default=None, max_length=60000)
    profile: Optional[dict[str, Any]] = None


class RankIn(BaseModel):
    listings: list[dict[str, Any]] = Field(min_length=1, max_length=20)
    profile: Optional[dict[str, Any]] = None


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/profile")
async def profile():
    return DEFAULT_PROFILE


@app.post("/api/analyze")
async def api_analyze(body: AnalyzeIn):
    text = (body.text or "").strip()
    if not text and not body.url:
        raise HTTPException(400, "Give a URL or paste the listing text.")
    if not text:
        try:
            text = await fetch_text(body.url.strip())
        except FetchError as e:
            raise HTTPException(422, str(e))
    text = text[:MAX_CHARS]
    if len(text) < 40:
        raise HTTPException(400, "Text is too short to analyse.")
    return await analyze(text, get_client(), body.profile or DEFAULT_PROFILE, source_url=body.url)


@app.post("/api/rank")
async def api_rank(body: RankIn):
    return await rank(body.listings, get_client(), body.profile or DEFAULT_PROFILE)
