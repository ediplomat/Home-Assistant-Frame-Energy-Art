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
import logging
import ssl
import threading
import time
import uuid

_LOGGER = logging.getLogger(__name__)

CLIENT_NAME = "FrameEnergyArt"
PORT = 8002
CONNECT_TIMEOUT = 10
PAIRING_TIMEOUT = 35  # time for a person to press "Allow" on the TV
REPLY_TIMEOUT = 15
LIST_REPLY_TIMEOUT = 60  # older Frames can be slow to send the picture list
TOTAL_TIMEOUT = 120  # the whole talk with the TV must end within this time
MAX_DELETES = 5  # old images tried per update; the rest wait for the next one
MY_PHOTOS = "MY-C0002"  # Art Mode category of uploaded pictures


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


def time_left(deadline: float | None) -> float | None:
    """Seconds left until ``deadline`` (a time.monotonic() value); raise when over."""
    if deadline is None:
        return None
    left = deadline - time.monotonic()
    if left <= 0:
        raise FrameError("The TV took too long to answer")
    return left


def skipped_name(raw, data: dict | None) -> str:
    """Short name of a message we were not waiting for (for the log and errors)."""
    if data:
        return str(data.get("event"))
    try:
        return str(json.loads(raw).get("event"))
    except (TypeError, ValueError, AttributeError):
        return "unreadable message"


def wait_for(conn, events: set[str], max_messages: int = 20, deadline: float | None = None,
             reply_timeout: float = REPLY_TIMEOUT) -> dict:
    """Read until one of ``events`` (or an error) arrives; raise otherwise.

    Every read has its own timeout (``reply_timeout``), but a TV that keeps
    sending other messages could still hold us for minutes, so ``deadline``
    limits the total. Messages we did not wait for are logged, and the last
    few names are added to the error, so we can see what the TV really sent.
    """
    skipped: list[str] = []

    def got() -> str:
        return f" (got: {skipped[-5:]})" if skipped else ""

    for _ in range(max_messages):
        left = time_left(deadline)
        if left is not None:
            conn.settimeout(min(reply_timeout, left))
        try:
            raw = conn.recv()
        except Exception as exc:  # timeout or closed socket
            raise FrameError(f"No reply from TV ({exc}){got()}") from exc
        data = art_event(raw)
        if data and data.get("event") == "error":
            raise FrameError(f"TV error: {data}")
        if data and data.get("event") in events:
            return data
        text = raw if isinstance(raw, str) else repr(raw)
        _LOGGER.debug("TV message skipped while waiting for %s: %s", sorted(events), text[:300])
        skipped.append(skipped_name(raw, data))
    raise FrameError(f"TV did not send {sorted(events)}{got()}")


class FrameClient:
    """One short-lived connection to the TV's Art Mode channel."""

    # Replaceable in tests. The watchdog runs in its own thread.
    timer_factory = threading.Timer

    def __init__(self, host: str, token: str | None, connector=None):
        self.host = host
        self.token = token
        self._connector = connector
        self.conn = None
        self.ready = False
        self.deadline = None
        self.timed_out = False
        self._watchdog = None

    def _arm(self) -> None:
        """Give the next socket operation what is left of the total time."""
        self.conn.settimeout(min(REPLY_TIMEOUT, time_left(self.deadline)))

    def _force_close(self) -> None:
        """Called by the watchdog when the total time is over.

        A socket timeout alone is not enough: a TV that keeps the connection
        alive with ping frames (for example while it waits for "Allow") makes
        every read wait again, so the read never ends. Closing the socket from
        outside makes the blocked read fail at once.
        """
        self.timed_out = True
        abort = getattr(self.conn, "abort", None)  # websocket-client: shuts the socket down
        try:
            if abort is not None:
                abort()
            self.conn.close()
        except Exception:  # already closed or broken: nothing more to do
            pass

    def _stop_watchdog(self) -> None:
        if self._watchdog is not None:
            self._watchdog.cancel()
            self._watchdog = None

    def _fail(self, message: str, exc: Exception | None = None) -> FrameError:
        self._stop_watchdog()
        try:
            self.conn.close()
        except Exception:
            pass
        if self.timed_out:
            message = "The TV took too long to answer (is an \"Allow\" message waiting on the TV?)"
        return FrameError(f"{message} ({exc})" if exc and not self.timed_out else message)

    def __enter__(self):
        connect = self._connector
        if connect is None:
            import websocket  # websocket-client, installed via manifest requirements
            connect = websocket.create_connection
        self.deadline = time.monotonic() + TOTAL_TIMEOUT
        self.conn = connect(
            art_url(self.host, self.token),
            timeout=CONNECT_TIMEOUT,
            sslopt={"cert_reqs": ssl.CERT_NONE},  # the TV uses a self-signed certificate
        )
        self._watchdog = self.timer_factory(TOTAL_TIMEOUT, self._force_close)
        self._watchdog.daemon = True
        self._watchdog.start()
        for _ in range(10):
            try:
                self.conn.settimeout(min(PAIRING_TIMEOUT, time_left(self.deadline)))
                msg = json.loads(self.conn.recv())
            except Exception as exc:
                raise self._fail("TV did not accept the connection", exc) from exc
            event = msg.get("event")
            if event == "ms.channel.connect":
                new_token = (msg.get("data") or {}).get("token")
                if new_token:
                    self.token = str(new_token)
            elif event == "ms.channel.unauthorized":
                raise self._fail("Connection was refused on the TV")
            elif event == "ms.channel.ready":
                self.ready = True
                break
        self.conn.settimeout(REPLY_TIMEOUT)
        return self

    def __exit__(self, *exc):
        self._stop_watchdog()
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass

    def upload(self, jpeg: bytes, matte: str = "none") -> str:
        self._arm()
        self.conn.send_binary(upload_frame(jpeg, matte))
        content_id = wait_for(self.conn, {"image_added"}, deadline=self.deadline).get("content_id")
        if not content_id:
            raise FrameError("TV confirmed the upload without a content_id")
        return str(content_id)

    def art_mode_on(self) -> bool:
        """True only if the TV says it is showing Art Mode right now.

        Unknown counts as "no": interrupting live TV is worse than waiting
        for the next update.
        """
        try:
            self._arm()
            self.conn.send(request_message({"request": "get_artmode_status", "id": str(uuid.uuid4())}))
            return wait_for(self.conn, {"artmode_status"}, max_messages=10, deadline=self.deadline).get("value") == "on"
        except FrameError:
            return False

    def select(self, content_id: str, show: bool) -> None:
        """Make the image the current artwork; ``show`` switches the screen to it."""
        self._arm()
        self.conn.send(request_message({"request": "select_image", "content_id": content_id, "show": show}))

    def delete(self, content_id: str) -> None:
        """Delete exactly one image. Callers pass only IDs this project uploaded or the user named."""
        self._arm()
        self.conn.send(request_message({"request": "delete_image_list", "content_id_list": [{"content_id": content_id}]}))
        wait_for(self.conn, {"image_deleted"}, max_messages=10, deadline=self.deadline)

    def content_list(self, category: str = MY_PHOTOS) -> list[dict]:
        """Pictures the TV keeps in one Art Mode category (``MY-C0002`` = My Photos)."""
        self._arm()
        self.conn.send(request_message({"request": "get_content_list", "category": category, "id": str(uuid.uuid4())}))
        data = wait_for(self.conn, {"content_list"}, max_messages=50, deadline=self.deadline,
                        reply_timeout=LIST_REPLY_TIMEOUT)
        # The list is normally under "content_list"; accept "data" or "items" too.
        items = data.get("content_list") or data.get("data") or data.get("items") or []
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except ValueError as exc:
                raise FrameError("The TV sent a picture list that could not be read") from exc
        if not isinstance(items, list):
            raise FrameError("The TV sent a picture list that could not be read")
        return [item for item in items if isinstance(item, dict)]


def pair(host: str, connector=None) -> str:
    """Connect once; the TV may ask "Allow" and issue a token.

    Some models (for example the 2019 Frame) open the Art Mode channel without
    any token. That is a successful pairing too: an empty token is returned.
    """
    with FrameClient(host, None, connector) as client:
        if not client.ready:
            raise FrameError("The TV did not open the Art Mode channel")
        return client.token or ""


def publish(host: str, token: str | None, jpeg: bytes, old_ids: list[str], connector=None,
            confirmed: list[str] | None = None) -> dict:
    """Upload and show the new image, then remove this project's older images.

    ``old_ids`` holds only content IDs this integration uploaded earlier.
    IDs that were not deleted (failed, skipped or cut off by a lost
    connection) are returned in ``pending``, so the next run retries them
    instead of forgetting them on the TV.

    ``confirmed`` is an optional list that gets the new ID the moment the TV
    confirms the upload. If this call never returns, the caller still knows
    the ID and can delete that picture later.
    """
    with FrameClient(host, token, connector) as client:
        content_id = client.upload(jpeg)
        if confirmed is not None:
            confirmed.append(content_id)
        # From here the new image exists on the TV, so its ID must always be
        # returned, whatever fails next (for example a dropped connection).
        old = [i for i in old_ids if i != content_id]
        pending, error, failed = list(old), None, {}
        try:
            # Never switch away from live TV: show now only if Art Mode is already on.
            client.select(content_id, show=client.art_mode_on())
            for image in old[:MAX_DELETES]:
                try:
                    client.delete(image)
                except FrameError as exc:
                    error = failed[image] = str(exc)  # the TV refused this one; others may still work
                else:
                    pending.remove(image)
        except Exception as exc:  # connection lost after the upload
            error = f"Connection lost after upload ({exc})"
        return {"content_id": content_id, "pending": pending, "delete_error": error, "failed": failed,
                "token": client.token}


def list_images(host: str, token: str | None, connector=None) -> dict:
    """Read the pictures in My Photos. Nothing is changed on the TV."""
    with FrameClient(host, token, connector) as client:
        items = client.content_list()
        _LOGGER.warning("TV pictures in My Photos (%d): %s", len(items),
                        ", ".join(f"{i.get('content_id')} ({i.get('image_date')})" for i in items) or "none")
        return {"images": items, "token": client.token}


def delete_images(host: str, token: str | None, content_ids: list[str], connector=None) -> dict:
    """Delete exactly the pictures named in ``content_ids``, one by one.

    Used only when the user names the IDs himself (for example after
    ``list_images``). One refused picture does not stop the others.
    """
    deleted, failed = [], {}
    with FrameClient(host, token, connector) as client:
        for content_id in content_ids:
            try:
                client.delete(content_id)
            except FrameError as exc:
                failed[content_id] = str(exc)
                _LOGGER.warning("TV refused to delete %s: %s", content_id, exc)
            else:
                deleted.append(content_id)
                _LOGGER.warning("Deleted TV picture %s", content_id)
        return {"deleted": deleted, "failed": failed, "token": client.token}
