"""Thin async client for the Clocked API.

Every call returns a uniform envelope instead of raising, so the pipeline can
keep going when one step fails and the UI can show exactly which step broke:

    {"ok": True,  "endpoint": "extract", "data": {...}, "ms": 812}
    {"ok": False, "endpoint": "extract", "error": "...", "status": 429, "ms": 40}
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Any

import httpx

DEFAULT_BASE = "https://clocked.rezolve.ai/clocked"
RETRYABLE = {408, 409, 425, 429, 500, 502, 503, 504}


class ClockedClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 timeout: float = 90.0, transport: httpx.AsyncBaseTransport | None = None):
        self.api_key = api_key if api_key is not None else os.getenv("CLOCKED_API_KEY", "")
        self.base_url = (base_url or os.getenv("CLOCKED_BASE_URL") or DEFAULT_BASE).rstrip("/")
        self.timeout = timeout
        self.transport = transport

    def _headers(self, idem_key: str) -> dict[str, str]:
        h = {"Content-Type": "application/json", "Idempotency-Key": idem_key}
        # Only send Authorization when a key is configured. In environments where
        # an egress proxy injects credentials, leave CLOCKED_API_KEY unset.
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def call(self, endpoint: str, payload: dict[str, Any], retries: int = 1) -> dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        # One idempotency key per logical request; reused on retry so a timed-out
        # attempt is never charged twice (per Clocked's Errors & retries guide).
        idem = str(uuid.uuid4())
        started = time.perf_counter()
        last: dict[str, Any] = {}
        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as c:
                    r = await c.post(url, json=payload, headers=self._headers(idem))
                ms = int((time.perf_counter() - started) * 1000)
                if r.status_code < 300:
                    return {"ok": True, "endpoint": endpoint, "data": r.json(), "ms": ms}
                try:
                    msg = r.json()
                    msg = msg.get("error") or msg.get("message") or msg.get("detail") or msg
                except Exception:
                    msg = r.text[:300]
                if isinstance(msg, dict):
                    msg = msg.get("message") or str(msg)
                last = {"ok": False, "endpoint": endpoint, "status": r.status_code,
                        "error": str(msg)[:400], "ms": ms}
                if r.status_code == 401:
                    last["error"] = "Unauthorized: set CLOCKED_API_KEY (Authorization: Bearer <key>)."
                if r.status_code not in RETRYABLE:
                    return last
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = {"ok": False, "endpoint": endpoint, "status": None,
                        "error": f"{type(e).__name__}: {e}"[:400],
                        "ms": int((time.perf_counter() - started) * 1000)}
            except ValueError as e:  # bad JSON body
                return {"ok": False, "endpoint": endpoint, "status": None,
                        "error": f"Invalid JSON from API: {e}"[:400], "ms": 0}
        return last

    async def injection(self, **kw): return await self.call("injection", kw)
    async def pii(self, **kw): return await self.call("pii", kw)
    async def extract(self, **kw): return await self.call("extract", kw)
    async def grounding(self, **kw): return await self.call("grounding", kw)
    async def decide(self, **kw): return await self.call("decide", kw)
    async def rerank(self, **kw): return await self.call("rerank", kw)
