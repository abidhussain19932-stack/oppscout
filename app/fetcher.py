"""Fetch a public page and reduce it to plain text.

Fetched pages are UNTRUSTED: their text is only ever sent to Clocked as data
(Guard first), never executed or treated as instructions.
"""
from __future__ import annotations

import html
import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx

MAX_CHARS = 18000  # keeps every downstream call inside Decide's 20k document cap
UA = "Mozilla/5.0 (compatible; OppScout/1.0; +https://github.com/abidhussain19932-stack/oppscout)"


class FetchError(Exception):
    pass


def html_to_text(raw: str) -> str:
    t = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", raw)
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr|section)>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def _is_public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


async def fetch_text(url: str, timeout: float = 20.0,
                     transport: httpx.AsyncBaseTransport | None = None,
                     check_host: bool = True) -> str:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise FetchError("Only http(s) URLs are supported.")
    if check_host and not _is_public_host(p.hostname):
        raise FetchError("That host is private or could not be resolved.")
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True,
                                     headers={"User-Agent": UA}, transport=transport) as c:
            r = await c.get(url)
    except httpx.HTTPError as e:
        raise FetchError(f"Could not fetch page: {type(e).__name__}") from e
    if r.status_code >= 400:
        raise FetchError(f"Page returned HTTP {r.status_code}.")
    ctype = r.headers.get("content-type", "")
    text = html_to_text(r.text) if "html" in ctype or "<html" in r.text[:500].lower() else r.text
    if len(text) < 80:
        raise FetchError("Page has almost no readable text (it may need JavaScript). Paste the text instead.")
    return text[:MAX_CHARS]
