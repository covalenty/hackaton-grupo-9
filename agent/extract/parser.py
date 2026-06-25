"""WhatsApp export parser.

Takes the raw `.txt` from "Exportar conversa" and yields RawMessage objects.

WhatsApp export format (PT-BR locale):
    DD/MM/YYYY HH:MM - Sender Name: Message body
    DD/MM/YYYY HH:MM - System message (no colon)

Multiline messages: subsequent lines without a date prefix belong to the
previous message.

Media: lines ending with "<Mídia oculta>" indicate attached media.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from ..schemas import MessageType, RawMessage

LINE_RE = re.compile(
    r"^(?P<date>\d{2}/\d{2}/\d{4}) (?P<time>\d{2}:\d{2}) - (?P<rest>.*)$"
)
SENDER_RE = re.compile(r"^(?P<sender>[^:]{1,60}): (?P<body>.*)$", re.DOTALL)
SYSTEM_PHRASES = (
    "criou o grupo",
    "criou uma lista de transmissão",
    "adicionou você",
    "adicionado à lista",
    "removido(a) da lista",
    "foram adicionados",
    "foi removido",
    "mudou as configurações",
    "código de segurança",
    "As mensagens e ligações são protegidas",
    "Você criou uma lista",
)
MEDIA_MARKERS = ("<Mídia oculta>", "<arquivo de mídia oculto>", "<Media omitted>")


def _is_system_message(text: str) -> bool:
    return any(phrase in text for phrase in SYSTEM_PHRASES)


def _make_id(received_at: datetime, sender: Optional[str], body: str) -> str:
    seed = f"{received_at.isoformat()}|{sender or ''}|{body[:200]}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _detect_media(body: str) -> bool:
    return any(marker in body for marker in MEDIA_MARKERS)


def iter_messages(
    path: str | Path,
    group_name: Optional[str] = None,
    buyer_name_aliases: Optional[list[str]] = None,
) -> Iterator[RawMessage]:
    """Yield RawMessage objects from a WhatsApp export file.

    Skips system messages. Collapses multiline messages. Detects media markers.
    If `buyer_name_aliases` is given, messages from those senders are marked
    `is_from_buyer=True` — Stage 2 then treats them as buyer_request candidates.
    """
    aliases = {a.strip().lower() for a in (buyer_name_aliases or [])}
    path = Path(path)
    current_date: Optional[str] = None
    current_time: Optional[str] = None
    current_sender: Optional[str] = None
    current_body: list[str] = []

    def flush() -> Optional[RawMessage]:
        if current_date is None or not current_body:
            return None
        body = "\n".join(current_body).strip()
        if not body:
            return None
        if _is_system_message(body):
            return None
        received_at = datetime.strptime(f"{current_date} {current_time}", "%d/%m/%Y %H:%M")
        has_media = _detect_media(body)
        is_from_buyer = bool(current_sender) and current_sender.strip().lower() in aliases
        return RawMessage(
            message_id=_make_id(received_at, current_sender, body),
            source_name=current_sender,
            group_name=group_name,
            received_at=received_at,
            body=body,
            has_media=has_media,
            message_type=MessageType.IMAGE if has_media else MessageType.TEXT,
            is_from_buyer=is_from_buyer,
        )

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            m = LINE_RE.match(line)
            if m is None:
                if current_body:
                    current_body.append(line)
                continue
            msg = flush()
            if msg is not None:
                yield msg
            current_date = m.group("date")
            current_time = m.group("time")
            rest = m.group("rest")
            sender_m = SENDER_RE.match(rest)
            if sender_m:
                current_sender = sender_m.group("sender").strip()
                current_body = [sender_m.group("body")]
            else:
                current_sender = None
                current_body = [rest]
        last = flush()
        if last is not None:
            yield last
