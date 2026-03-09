"""
WebSocket router — real-time pipeline status and live updates.
Streams analysis progress to the trade-dashboard UI.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config.settings import settings

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages active WebSocket connections for broadcasting."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active.append(websocket)
        logger.info("ws_connected", total=len(self.active))

    def disconnect(self, websocket: WebSocket) -> None:
        self.active.remove(websocket)
        logger.info("ws_disconnected", total=len(self.active))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a message to all connected clients."""
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)

    async def send_to(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        await websocket.send_json(message)


ws_manager = ConnectionManager()


@router.websocket("/ws/pipeline")
async def pipeline_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for streaming pipeline progress.

    Message types sent to client:
      - {"type": "status", "agent": "flow_analyst", "status": "running"}
      - {"type": "progress", "agent": "news_analyst", "pct": 50}
      - {"type": "result", "agent": "opex_analyst", "data": {...}}
      - {"type": "complete", "docx_path": "..."}
      - {"type": "error", "message": "..."}
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            # Receive commands from client
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "ping":
                await ws_manager.send_to(websocket, {"type": "pong"})
            elif msg.get("type") == "subscribe":
                await ws_manager.send_to(websocket, {
                    "type": "subscribed",
                    "channels": msg.get("channels", ["pipeline"]),
                })
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error("ws_error", error=str(e))
        ws_manager.disconnect(websocket)


@router.websocket("/ws/market")
async def market_feed_websocket(websocket: WebSocket):
    """
    WebSocket for streaming market data updates.
    Useful for live price feeds to the dashboard.
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            # Client can request specific symbols to watch
            if msg.get("type") == "watch":
                await ws_manager.send_to(websocket, {
                    "type": "watching",
                    "symbols": msg.get("symbols", []),
                })
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
