# WhatsApp Bridge Contract

What the agent expects from the WhatsApp bridge (`/messages`, `/stream`, `/send`).

## Current state ✅

| Endpoint | Status | Used by |
|---|---|---|
| `GET /stream` | Working (SSE) | `agent.ingest.webhook_client.iter_sse` |
| `GET /messages?since=<ms>` | Working (polling) | `agent.ingest.webhook_client.poll` |
| `POST /send` | Working | `agent.deliver.sender.HTTPSender` |

### `POST /send`
```http
POST /send HTTP/1.1
Content-Type: application/json

{ "number": "5519988008998", "text": "..." }
```
Errors with `{"ok": false, "error": "informe { number, text }"}` when fields are missing.
Returns `{"ok": true, "id": "<msg-id>"}` on success.

## What's missing for vision-live 🟡

When an image arrives, the webhook payload currently includes the Baileys
`raw.message.imageMessage` block — but the `url` inside it points to WhatsApp's
encrypted CDN (`mmg.whatsapp.net`), which we **cannot fetch from outside Baileys**
without the `mediaKey` and the AES-CBC + HMAC decryption routine.

The bridge already has the decryption code (Baileys does it natively). All
we need is for the bridge to **expose the decrypted bytes** to the agent.

Two contracts the agent already supports — pick whichever is easier:

### Contract A — top-level `media_url` (preferred)
The bridge adds a `media_url` field to the webhook payload pointing at an
endpoint the bridge hosts (e.g. `GET /media/{message_id}` returning the
decoded image as `image/jpeg` bytes):

```jsonc
{
  "id": "3A7501F522823F4FC189",
  "from": "5519999998888@s.whatsapp.net",
  "name": "Eduardo MILFARMA",
  "text": null,
  "timestamp": 1782396413000,
  "media_url": "https://used-pad-interstate-smithsonian.trycloudflare.com/media/3A7501F522823F4FC189",
  "raw": { ... }
}
```

The agent's Stage 1 picks up `media_url`, passes to Stage 2 vision, which
fetches via httpx and embeds as base64 in the Claude messages call.

### Contract B — inline `media_b64`
The bridge decodes the bytes itself and ships them base64-encoded inside the
webhook payload:

```jsonc
{
  "id": "3A7501F522823F4FC189",
  "from": "5519999998888@s.whatsapp.net",
  "name": "Eduardo MILFARMA",
  "text": null,
  "timestamp": 1782396413000,
  "media_b64": "<base64 of decoded jpeg bytes>",
  "raw": { ... }
}
```

Simpler from the agent's side (no second round-trip) but increases payload size
and may bloat the in-memory `/messages` buffer if there are many images.

**Recommendation:** Contract A. The bridge already needs an HTTP server; one
more route is cheaper than blowing up the polling JSON.

## Caveats

- WhatsApp image captions arrive at `raw.message.imageMessage.caption`.
  Stage 1 already lifts that into `RawMessage.body` so the LLM sees it
  alongside the image.
- Some reps send **image followed by a follow-up text bubble** with the
  price (Paulinho does this). For V1 each bubble is processed separately.
  Fusion of `image + text from same sender within 60s` is a follow-up PR.
- Audio (`.opus`) and PDF/Excel attachments come through `raw.message.audioMessage`
  and `raw.message.documentMessage`. Stage 1 already labels the
  `message_type` correctly; processing of audio/PDF/Excel is a future PR.
