"""Webhook client — reads WhatsApp messages from the hackathon bridge.

Two modes:
  - SSE (recommended): real-time, server-sent events on /stream.
  - Polling: GET /messages?since=<ms>; for environments without keep-alive.

Both yield dicts with the bridge's wire format:
  { "id", "from", "name", "text", "timestamp", "raw" }

`text` is null when the message isn't text (image / audio / etc).
`from` is a JID like "5511999998888@s.whatsapp.net".
`timestamp` is epoch ms.
"""
from __future__ import annotations

import json
import time
from typing import Iterator, Optional

import httpx
from httpx_sse import connect_sse


DEFAULT_BASE = "https://used-pad-interstate-smithsonian.trycloudflare.com"


def iter_sse(base_url: str = DEFAULT_BASE, *, timeout: float = 60.0) -> Iterator[dict]:
    """Block on /stream and yield every message as a dict. Reconnects on error."""
    url = f"{base_url.rstrip('/')}/stream"
    while True:
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout, read=None)) as client:
                with connect_sse(client, "GET", url) as event_source:
                    for sse in event_source.iter_sse():
                        if not sse.data:
                            continue
                        try:
                            yield json.loads(sse.data)
                        except json.JSONDecodeError:
                            continue
        except (httpx.HTTPError, httpx.NetworkError) as e:
            print(f"[ingest] SSE error: {e!r} · reconnecting in 3s")
            time.sleep(3)


def poll(base_url: str = DEFAULT_BASE, *, interval: float = 2.0, since_ms: Optional[int] = None) -> Iterator[dict]:
    """Poll /messages?since=<ms> at `interval` seconds. Yields each new message once."""
    last = since_ms if since_ms is not None else int(time.time() * 1000)
    url = f"{base_url.rstrip('/')}/messages"
    seen_ids: set[str] = set()
    while True:
        try:
            r = httpx.get(url, params={"since": last}, timeout=10.0)
            r.raise_for_status()
            batch = r.json()
            if isinstance(batch, dict) and "messages" in batch:
                batch = batch["messages"]
            for msg in batch or []:
                mid = msg.get("id")
                if mid and mid in seen_ids:
                    continue
                if mid:
                    seen_ids.add(mid)
                ts = msg.get("timestamp")
                if isinstance(ts, int) and ts > last:
                    last = ts
                yield msg
        except (httpx.HTTPError, httpx.NetworkError) as e:
            print(f"[ingest] poll error: {e!r}")
        time.sleep(interval)
