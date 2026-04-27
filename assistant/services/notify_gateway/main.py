"""
Notify Gateway — stateless dispatcher for Home Assistant webhook notifications.

HA posts a single payload describing the message and the targets it should be
delivered to. The gateway fans the message out to each target. No device
registry is kept here — all routing info comes from HA per request.

Endpoints
---------
  POST /notify  JSON: {"message": "...", "targets": [{"type": "tts", "url": "..."}, {"type": "telegram"}]}
  GET  /health

Target types
------------
  tts       → POST {url}/text  with {"text": message, "device_id": "ha-notify"}
              and X-Api-Key: GATEWAY_API_KEY  (delivered to a voice_gateway).
  telegram  → sendMessage to MY_CHAT_ID via Bot API using BOT_TOKEN.
"""
import logging
import os
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from core.config import BOT_TOKEN, MY_CHAT_ID, GATEWAY_API_KEY

logging.basicConfig(
    format="%(asctime)s [notify-gateway] %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

NOTIFY_PORT: int = int(os.getenv("NOTIFY_PORT", "8766"))
HTTP_TIMEOUT: float = float(os.getenv("NOTIFY_HTTP_TIMEOUT", "10"))

app = FastAPI(title="Notify Gateway", version="1.0")


class Target(BaseModel):
    type: Literal["tts", "telegram"]
    url: str | None = None


class NotifyRequest(BaseModel):
    message: str
    targets: list[Target]


async def _dispatch_tts(client: httpx.AsyncClient, message: str, url: str) -> dict:
    if not url:
        return {"ok": False, "error": "tts target missing url"}
    headers = {}
    if GATEWAY_API_KEY:
        headers["X-Api-Key"] = GATEWAY_API_KEY
    try:
        r = await client.post(
            f"{url.rstrip('/')}/text",
            json={"text": message, "device_id": "ha-notify"},
            headers=headers,
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        return {"ok": True, "status": r.status_code}
    except Exception as e:
        logger.warning(f"tts dispatch to {url} failed: {e}")
        return {"ok": False, "error": str(e)}


async def _dispatch_telegram(client: httpx.AsyncClient, message: str) -> dict:
    if not BOT_TOKEN or not MY_CHAT_ID:
        return {"ok": False, "error": "BOT_TOKEN or MY_CHAT_ID not configured"}
    try:
        r = await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": MY_CHAT_ID, "text": message},
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        return {"ok": True, "status": r.status_code}
    except Exception as e:
        logger.warning(f"telegram dispatch failed: {e}")
        return {"ok": False, "error": str(e)}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "port": NOTIFY_PORT}


@app.post("/notify")
async def notify(req: NotifyRequest) -> dict:
    if not req.targets:
        raise HTTPException(status_code=400, detail="targets must not be empty")

    results: list[dict] = []
    async with httpx.AsyncClient() as client:
        for t in req.targets:
            if t.type == "tts":
                res = await _dispatch_tts(client, req.message, t.url or "")
            elif t.type == "telegram":
                res = await _dispatch_telegram(client, req.message)
            else:
                res = {"ok": False, "error": f"unknown target type: {t.type}"}
            results.append({"type": t.type, "url": t.url, **res})

    logger.info(f"dispatched message={req.message!r} results={results}")
    return {"results": results}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=NOTIFY_PORT)
