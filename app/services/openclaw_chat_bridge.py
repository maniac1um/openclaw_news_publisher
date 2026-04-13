import base64
import json
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Awaitable, Callable, Optional

import websockets


def _b64url_encode(raw: bytes) -> str:
    s = base64.b64encode(raw).decode("ascii")
    s = s.replace("+", "-").replace("/", "_")
    return s.rstrip("=")


def _extract_chat_text(message: object) -> str:
    """
    Gateway `chat` events have a `payload.message` like:
      { role: "assistant", content: [ {type:"text", text:"..."}, ... ], timestamp: ... }
    """
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
            parts.append(part["text"])
    return "".join(parts)


def _sign_ed25519_openssl(private_key_pem: str, payload: str) -> str:
    """
    Node side uses:
      crypto.sign(null, Buffer.from(payload,'utf8'), privateKey)
    for Ed25519 (algorithm=null => Ed25519 signs the raw message).
    """
    with tempfile.TemporaryDirectory() as td:
        priv_path = Path(td) / "priv.pem"
        msg_path = Path(td) / "payload.txt"
        priv_path.write_text(private_key_pem, encoding="utf-8")
        msg_path.write_text(payload, encoding="utf-8")
        proc = subprocess.run(
            ["openssl", "pkeyutl", "-sign", "-inkey", str(priv_path), "-rawin", "-in", str(msg_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return _b64url_encode(proc.stdout)


async def stream_openclaw_reply(
    *,
    openclaw_ws_url: str,
    user_text: str,
    session_key: str,
    on_assistant_update: Callable[[str, bool], Awaitable[None]],
    flush_interval_seconds: float = 0.2,
) -> None:
    """
    Proxy one OpenClaw Gateway chat.send run for a single browser session.

    Implementation details:
    - Perform Gateway `connect` handshake (requires device identity + Ed25519 signature).
    - Call `chat.send` with the given `session_key`.
    - Listen to `event: "chat"` stream and extract assistant text from `payload.message`.
    - Throttle client pushes: aggregate and send updates every `flush_interval_seconds`.
    """

    # 勿硬编码本机用户名；公开仓库可配合 OPENCLAW_STATE_DIR 覆盖
    openclaw_state_dir = Path(
        os.environ.get("OPENCLAW_STATE_DIR", str(Path.home() / ".openclaw"))
    )
    openclaw_json_path = openclaw_state_dir / "openclaw.json"
    device_auth_path = openclaw_state_dir / "identity" / "device.json"
    paired_devices_path = openclaw_state_dir / "devices" / "paired.json"

    openclaw_cfg = json.loads(openclaw_json_path.read_text("utf-8"))
    gateway_token = openclaw_cfg["gateway"]["auth"]["token"]

    device_auth = json.loads(device_auth_path.read_text("utf-8"))
    device_id: str = device_auth["deviceId"]
    private_key_pem: str = device_auth["privateKeyPem"]

    paired_devices = json.loads(paired_devices_path.read_text("utf-8"))
    paired_entry: Optional[dict] = paired_devices.get(device_id)
    if not paired_entry:
        raise RuntimeError(f"Missing paired device identity for deviceId={device_id}")

    client_id: str = paired_entry["clientId"]
    client_mode: str = paired_entry["clientMode"]
    role: str = paired_entry["role"]
    scopes: list[str] = paired_entry["scopes"]
    public_key_b64url: str = paired_entry["publicKey"]
    platform: str = paired_entry.get("platform") or "linux"
    device_family: str = ""  # leave empty (signature payload still valid)

    signed_at_ms = int(time.time() * 1000)

    buffer = ""
    last_flushed_at = 0.0
    last_sent_text = None

    # Expected OpenClaw emitted sessionKey looks like:
    #   agent:<defaultAgentId>:<session_key>
    # We can match by suffix to avoid depending on defaultAgentId.
    session_key_suffix = ":" + session_key

    async with websockets.connect(openclaw_ws_url) as oc_ws:
        # 1) Wait for connect.challenge
        first_raw = await oc_ws.recv()
        first = json.loads(first_raw)
        if first.get("type") != "event" or first.get("event") != "connect.challenge":
            raise RuntimeError(f"Expected connect.challenge, got: {first}")
        connect_nonce = first["payload"]["nonce"]

        # 2) Build device signature for Gateway connect
        scopes_csv = ",".join(scopes)
        payload_v3 = "|".join(
            [
                "v3",
                device_id,
                client_id,
                client_mode,
                role,
                scopes_csv,
                str(signed_at_ms),
                gateway_token,
                connect_nonce,
                platform,
                device_family,
            ]
        )
        signature_b64url = _sign_ed25519_openssl(private_key_pem, payload_v3)

        connect_req = {
            "type": "req",
            "id": "c1",
            "method": "connect",
            "params": {
                "minProtocol": 3,
                "maxProtocol": 3,
                "client": {
                    "id": client_id,
                    "displayName": "openclaw-news-publisher",
                    "version": "0.1.0",
                    "platform": platform,
                    "mode": client_mode,
                },
                "role": role,
                "scopes": scopes,
                "caps": [],
                "commands": [],
                "permissions": {},
                "auth": {"token": gateway_token},
                "locale": "zh-CN",
                "userAgent": "openclaw-news-publisher/0.1",
                "device": {
                    "id": device_id,
                    "publicKey": public_key_b64url,
                    "signature": signature_b64url,
                    "signedAt": signed_at_ms,
                    "nonce": connect_nonce,
                },
            },
        }
        await oc_ws.send(json.dumps(connect_req, ensure_ascii=False))

        # 3) Wait for connect res (or any auth failure)
        while True:
            res_raw = await oc_ws.recv()
            res = json.loads(res_raw)
            if res.get("type") == "res" and res.get("id") == "c1":
                if not res.get("ok"):
                    raise RuntimeError(f"OpenClaw connect failed: {res}")
                break

        # 4) chat.send
        chat_req_id = "chat.send:" + session_key
        # Important: idempotencyKey must be unique per user message.
        # If we reuse the same sessionKey across multi-turn conversations,
        # but keep idempotencyKey identical, the Gateway may treat subsequent
        # chat.send calls as duplicates and fail to advance the conversation.
        idem = "idem:" + session_key + ":" + str(uuid.uuid4())
        chat_req = {
            "type": "req",
            "id": chat_req_id,
            "method": "chat.send",
            "params": {
                "sessionKey": session_key,
                "message": user_text,
                "idempotencyKey": idem,
            },
        }
        await oc_ws.send(json.dumps(chat_req, ensure_ascii=False))

        # 5) Stream chat events and throttle to frontend
        while True:
            raw = await oc_ws.recv()
            msg = json.loads(raw)
            if msg.get("type") != "event" or msg.get("event") != "chat":
                continue
            payload = msg.get("payload")
            if not isinstance(payload, dict):
                continue
            emitted_session_key = payload.get("sessionKey")
            if not isinstance(emitted_session_key, str):
                continue
            if not emitted_session_key.endswith(session_key_suffix):
                continue

            state = payload.get("state")
            message = payload.get("message")
            text_part = _extract_chat_text(message)
            if text_part:
                buffer = text_part

            now = time.monotonic()
            if (now - last_flushed_at) >= flush_interval_seconds and buffer and buffer != last_sent_text:
                await on_assistant_update(buffer, False)
                last_flushed_at = now
                last_sent_text = buffer

            if state in ("final", "error", "aborted"):
                # Ensure final content is sent immediately.
                await on_assistant_update(buffer, True)
                break

