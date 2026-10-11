"""Minimal Samsung The Frame Art Mode client.

Written for this project from the publicly known Art Mode WebSocket protocol
(tested shape: Art API used by the 2019 Frame). Blocking code: call it from
Home Assistant's executor, never from the event loop.

Only four operations are needed:
  upload  -> the TV must confirm with ``image_added``, otherwise we raise
  status  -> is Art Mode on right now? (live TV must never be interrupted)
  select  -> make the uploaded image current; switch to it only in Art Mode
  delete  -> remove ONE image by its content_id (never "delete all")
"""
from __future__ import annotations

import base64
import json
import ssl
import uuid

CLIENT_NAME = "FrameEnergyArt"
PORT = 8002
CONNECT_TIMEOUT = 10
PAIRING_TIMEOUT = 35  # time for a person to press "Allow" on the TV
REPLY_TIMEOUT = 15


class FrameError(Exception):
    """The TV refused, did not answer or answered with an error."""


def art_url(host: str, token: str | None) -> str:
    name = base64.b64encode(CLIENT_NAME.encode()).decode()
    url = f"wss://{host}:{PORT}/api/v2/channels/com.samsung.art-app?name={name}"
    return f"{url}&token={token}" if token else url


def request_message(data: dict) -> str:
    return json.dumps({
        "method": "ms.channel.emit",
        "params": {"event": "art_app_request", "to": "host", "data": json.dumps(data)},
    })


def upload_frame(jpeg: bytes, matte: str = "none") -> bytes:
    """Binary frame: 2-byte big-endian header length, JSON header, JPEG bytes."""
    inner = {"request": "send_image", "file_type": "JPEG", "matte_id": matte, "id": str(uuid.uuid4())}
    header = json.dumps(
        {"method": "ms.channel.emit", "params": {"data": json.dumps(inner), "to": "host", "event": "art_app_request"}},
        separators=(",", ":"),
    ).encode()
    return len(header).to_bytes(2, "big") + header + jpeg


def art_event(raw) -> dict | None:
    """Return the inner Art Mode event from one WebSocket message, if any."""
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if msg.get("event") != "d2d_service_message":
        return None
    data = msg.get("data", "{}")
    try:
        return json.loads(data) if isinstance(data, str) else data
    except ValueError:
        return None


def wait_for(conn, events: set[str], max_messages: int = 20) -> dict:
    """Read until one of ``events`` (or an error) arrives; raise otherwise."""
    for _ in range(max_messages):
        try:
            raw = conn.recv()
        except Exception as exc:  # timeout or closed socket
            raise FrameError(f"No reply from TV ({exc})") from exc
        data = art_event(raw)
        if not data:
            continue
        if data.get("event") == "error":
            raise FrameError(f"TV error: {data}")
        if data.get("event") in events:
            return data
    raise FrameError(f"TV did not send {sorted(events)}")


class FrameClient:
    """One short-lived connection to the TV's Art Mode channel."""

    def __init__(self, host: str, token: str | None, connector=None):
        self.host = host
        self.token = token
        self._connector = connector
        self.conn = None
        self.ready = False

    def __enter__(self):
        connect = self._connector
        if connect is None:
            import websocket  # websocket-client, installed via manifest requirements
            connect = websocket.create_connection
        self.conn = connect(
            art_url(self.host, self.token),
            timeout=CONNECT_TIMEOUT,
            sslopt={"cert_reqs": ssl.CERT_NONE},  # the TV uses a self-signed certificate
        )
        self.conn.settimeout(PAIRING_TIMEOUT)
        for _ in range(10):
            try:
                msg = json.loads(self.conn.recv())
            except Exception as exc:
                self.conn.close()
                raise FrameError(f"TV did not accept the connection ({exc})") from exc
            event = msg.get("event")
            if event == "ms.channel.connect":
                new_token = (msg.get("data") or {}).get("token")
                if new_token:
                    self.token = str(new_token)
            elif event == "ms.channel.unauthorized":
                self.conn.close()
                raise FrameError("Connection was refused on the TV")
            elif event == "ms.channel.ready":
                self.ready = True
                break
        self.conn.settimeout(REPLY_TIMEOUT)
        return self

    def __exit__(self, *exc):
        if self.conn is not None:
            self.conn.close()

    def upload(self, jpeg: bytes, matte: str = "none") -> str:
        self.conn.send_binary(upload_frame(jpeg, matte))
        content_id = wait_for(self.conn, {"image_added"}).get("content_id")
        if not content_id:
            raise FrameError("TV confirmed the upload without a content_id")
        return str(content_id)

    def art_mode_on(self) -> bool:
        """True only if the TV says it is showing Art Mode right now.

        Unknown counts as "no": interrupting live TV is worse than waiting
        for the next update.
        """
        self.conn.send(request_message({"request": "get_artmode_status", "id": str(uuid.uuid4())}))
        try:
            return wait_for(self.conn, {"artmode_status"}, max_messages=10).get("value") == "on"
        except FrameError:
            return False

    def select(self, content_id: str, show: bool) -> None:
        """Make the image the current artwork; ``show`` switches the screen to it."""
        self.conn.send(request_message({"request": "select_image", "content_id": content_id, "show": show}))

    def delete(self, content_id: str) -> None:
        """Delete exactly one image. Callers pass only IDs this project uploaded."""
        self.conn.send(request_message({"request": "delete_image_list", "content_id_list": [{"content_id": content_id}]}))
        wait_for(self.conn, {"image_deleted"}, max_messages=10)


def pair(host: str, connector=None) -> str:
    """Connect once; the TV may ask "Allow" and issue a token.

    Some models (for example the 2019 Frame) open the Art Mode channel without
    any token. That is a successful pairing too: an empty token is returned.
    """
    with FrameClient(host, None, connector) as client:
        if not client.ready:
            raise FrameError("The TV did not open the Art Mode channel")
        return client.token or ""


def publish(host: str, token: str | None, jpeg: bytes, old_ids: list[str], connector=None) -> dict:
    """Upload and show the new image, then remove this project's older images.

    ``old_ids`` holds only content IDs this integration uploaded earlier.
    IDs that could not be deleted are returned in ``pending`` so the next run
    retries them instead of forgetting them on the TV.
    """
    with FrameClient(host, token, connector) as client:
        content_id = client.upload(jpeg)
        # Never switch away from live TV: show now only if Art Mode is already on.
        client.select(content_id, show=client.art_mode_on())
        pending, delete_error = [], None
        for old in old_ids:
            if old == content_id:
                continue
            try:
                client.delete(old)
            except FrameError as exc:
                pending.append(old)
                delete_error = str(exc)
        return {"content_id": content_id, "pending": pending, "delete_error": delete_error, "token": client.token}
