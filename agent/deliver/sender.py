"""WhatsApp senders — pluggable backends for shipping alerts to the buyer.

Two implementations:
  - LogSender: prints to stdout and appends to runs/alerts.jsonl.
    Works today, no external dependency.
  - HTTPSender: POSTs to a webhook bridge endpoint.
    Ready for when Cole exposes a /send route on his bridge.
    Format expected: POST {url} -d {"to": "<phone>", "text": "<body>"}.

Add new senders here as the bridge evolves (Twilio, official Cloud API, etc.).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional, Protocol

import httpx


class WhatsAppSender(Protocol):
    """Anything with a `send(to, text)` that returns True on success."""

    def send(self, *, to: str, text: str, context: Optional[dict] = None) -> bool: ...


class LogSender:
    """Default fallback — prints + persists. Use until bridge exposes /send."""

    def __init__(self, jsonl_path: str | Path = "runs/alerts.jsonl") -> None:
        self.path = Path(jsonl_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def send(self, *, to: str, text: str, context: Optional[dict] = None) -> bool:
        rec = {
            "ts": int(time.time() * 1000),
            "to": to,
            "text": text,
            "context": context or {},
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        # Display with clear borders so it's obvious in the run_pipeline output.
        print("\n" + "─" * 60)
        print(f"📨 ALERT → {to}")
        print("─" * 60)
        print(text)
        print("─" * 60 + "\n")
        return True


class HTTPSender:
    """POST {url} -d {number, text}. Matches the hackathon bridge's /send contract.

    `number` must be digits only (no '+', no '@s.whatsapp.net'). HTTPSender
    normalizes whatever string you pass to that shape.
    """

    def __init__(
        self,
        url: str,
        *,
        bearer_token: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        self.url = url
        self.headers = {"Content-Type": "application/json"}
        if bearer_token:
            self.headers["Authorization"] = f"Bearer {bearer_token}"
        self.timeout = timeout

    @staticmethod
    def _normalize_number(raw: str) -> str:
        """+5519988008998 → 5519988008998. Strip '+', JID suffix, whitespace."""
        s = (raw or "").strip()
        if s.startswith("+"):
            s = s[1:]
        if "@" in s:
            s = s.split("@", 1)[0]
        return "".join(ch for ch in s if ch.isdigit())

    def send(self, *, to: str, text: str, context: Optional[dict] = None) -> bool:
        number = self._normalize_number(to)
        body = {"number": number, "text": text}
        try:
            r = httpx.post(self.url, headers=self.headers, json=body, timeout=self.timeout)
            r.raise_for_status()
            print(f"📨 sent → {number} (http {r.status_code})")
            return True
        except httpx.HTTPError as e:
            print(f"[sender] HTTPSender failed for {number}: {e!r}")
            return False
