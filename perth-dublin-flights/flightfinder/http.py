"""Tiny stdlib HTTP helper with JSON, gzip and a single retry on transient errors."""

from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "perth-dublin-flight-finder/1.0"
RETRY_STATUSES = {429, 500, 502, 503, 504}


class HTTPError(RuntimeError):
    def __init__(self, status: int, body: str, url: str):
        super().__init__(f"HTTP {status} from {url.split('?')[0]}: {body[:300]}")
        self.status = status
        self.body = body


def request_json(
    method: str,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    body: dict | None = None,
    timeout: float = 30,
    retries: int = 1,
) -> dict:
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        url = f"{url}?{urllib.parse.urlencode(clean)}"
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Accept": "application/json", "Accept-Encoding": "gzip", "User-Agent": USER_AGENT}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})

    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read()
            if e.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            if e.code in RETRY_STATUSES and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise HTTPError(e.code, raw.decode("utf-8", "replace"), url) from None
    raise AssertionError("unreachable")
