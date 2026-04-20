import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.services.openclaw_chat_bridge import probe_openclaw_gateway, stream_openclaw_reply

router = APIRouter(
    prefix="/chat",
    tags=["OpenClaw 对话"],
)


async def _send_json(websocket: WebSocket, payload: dict[str, Any]) -> None:
    # FastAPI/WebSocket will serialize JSON for us if we call send_json.
    await websocket.send_json(payload)


@router.websocket("/ws")
async def chat_ws(websocket: WebSocket) -> None:
    await websocket.accept()

    # Current implementation is sequential per WS connection:
    # the client should not send a new user_message while one is running.
    active_session_key: str | None = None
    try:
        while True:
            incoming = await websocket.receive_json()
            if not isinstance(incoming, dict):
                continue

            msg_type = incoming.get("type")
            if msg_type != "user_message":
                continue

            if active_session_key is not None:
                await _send_json(
                    websocket,
                    {
                        "type": "assistant_error",
                        "sessionKey": incoming.get("sessionKey"),
                        "error": "Server busy: wait for the current reply to finish.",
                    },
                )
                continue

            user_text = incoming.get("text") or ""
            session_key = incoming.get("sessionKey")
            if not session_key or not user_text.strip():
                await _send_json(
                    websocket,
                    {
                        "type": "assistant_error",
                        "sessionKey": session_key,
                        "error": "Invalid user_message payload.",
                    },
                )
                continue

            active_session_key = session_key
            # Optional: send an early processing update for better UX.
            await _send_json(
                websocket,
                {
                    "type": "assistant_delta",
                    "sessionKey": session_key,
                    "text": "",
                    "done": False,
                    "status": "processing",
                },
            )

            async def on_assistant_update(delta_text: str, done: bool) -> None:
                await _send_json(
                    websocket,
                    {
                        "type": "assistant_delta",
                        "sessionKey": session_key,
                        "text": delta_text,
                        "done": done,
                    },
                )

            try:
                probe = await probe_openclaw_gateway(
                    openclaw_ws_url=settings.openclaw_ws_url,
                    timeout_seconds=settings.openclaw_gateway_probe_timeout_seconds,
                )
                if not probe.get("ok"):
                    raise RuntimeError(
                        "OpenClaw Gateway 当前不可用，请稍后重试。"
                        + (f" detail={probe.get('detail')}" if probe.get("detail") else "")
                    )
                await stream_openclaw_reply(
                    openclaw_ws_url=settings.openclaw_ws_url,
                    user_text=user_text,
                    session_key=session_key,
                    on_assistant_update=on_assistant_update,
                )
            except Exception as exc:
                await _send_json(
                    websocket,
                    {
                        "type": "assistant_error",
                        "sessionKey": session_key,
                        "error": str(exc),
                    },
                )
            finally:
                active_session_key = None

    except WebSocketDisconnect:
        return

