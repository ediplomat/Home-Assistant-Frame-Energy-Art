"""Protocol checks for the TV client with a fake TV (no network)."""
import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("frame_tv", ROOT / "custom_components/frame_energy/tv.py")
tv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tv)


def art(event, **data):
    return json.dumps({"event": "d2d_service_message", "data": json.dumps({"event": event, **data})})


class FakeTV:
    """Replays scripted replies and records what the client sent."""

    def __init__(self, replies, token="T1"):
        self.replies = [json.dumps({"event": "ms.channel.connect", "data": {"token": token}}),
                        json.dumps({"event": "ms.channel.ready"}), *replies]
        self.sent, self.binary, self.url, self.closed = [], [], None, False

    def __call__(self, url, **kwargs):
        self.url = url
        return self

    def settimeout(self, value):
        pass

    def recv(self):
        if not self.replies:
            raise TimeoutError("timed out")
        return self.replies.pop(0)

    def send(self, text):
        self.sent.append(json.loads(json.loads(text)["params"]["data"]))

    def send_binary(self, data):
        self.binary.append(data)

    def close(self):
        self.closed = True


class Clock:
    """A fake time.monotonic(), so the tests need no real waiting."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class ChattyTV(FakeTV):
    """After the scripted replies it keeps sending other messages, 50 s apart."""

    def __init__(self, clock, replies=()):
        super().__init__(list(replies))
        self.clock, self.reads = clock, 0

    def recv(self):
        if self.replies:
            return self.replies.pop(0)
        self.reads += 1
        self.clock.now += 50
        return art("other_event")


class UploaderTests(unittest.TestCase):
    def test_frame_layout(self):
        frame = tv.upload_frame(b"JPEG", "none")
        size = int.from_bytes(frame[:2], "big")
        header = json.loads(frame[2:2 + size])
        self.assertEqual(json.loads(header["params"]["data"])["request"], "send_image")
        self.assertEqual(frame[2 + size:], b"JPEG")

    def test_publish_uploads_shows_and_deletes_only_old_ids(self):
        fake = FakeTV([art("image_added", content_id="MY_F0012"), art("artmode_status", value="on"),
                       art("image_deleted"), art("image_deleted")])
        result = tv.publish("10.0.0.5", "T0", b"JPEG", ["MY_F0011", "MY_F0010"], connector=fake)
        self.assertEqual(result["content_id"], "MY_F0012")
        self.assertEqual(result["pending"], [])
        self.assertEqual(result["token"], "T1")
        self.assertIn("token=T0", fake.url)
        requests = [m["request"] for m in fake.sent]
        self.assertEqual(requests, ["get_artmode_status", "select_image", "delete_image_list", "delete_image_list"])
        self.assertTrue(fake.sent[1]["show"])
        deleted = [m["content_id_list"][0]["content_id"] for m in fake.sent[2:]]
        self.assertEqual(deleted, ["MY_F0011", "MY_F0010"])
        self.assertTrue(fake.closed)

    def test_live_tv_is_not_interrupted(self):
        fake = FakeTV([art("image_added", content_id="MY_F0012"), art("artmode_status", value="off"),
                       art("image_deleted")])
        result = tv.publish("10.0.0.5", "T0", b"JPEG", ["MY_F0011"], connector=fake)
        select = next(m for m in fake.sent if m["request"] == "select_image")
        self.assertEqual(select["content_id"], "MY_F0012")
        self.assertFalse(select["show"])
        self.assertEqual(result["pending"], [])

    def test_unknown_art_mode_does_not_switch(self):
        fake = FakeTV([art("image_added", content_id="MY_F0012")])
        result = tv.publish("10.0.0.5", "T0", b"JPEG", [], connector=fake)
        select = next(m for m in fake.sent if m["request"] == "select_image")
        self.assertFalse(select["show"])
        self.assertEqual(result["content_id"], "MY_F0012")

    def test_unconfirmed_upload_raises(self):
        fake = FakeTV([])
        with self.assertRaises(tv.FrameError):
            tv.publish("10.0.0.5", "T0", b"JPEG", [], connector=fake)
        self.assertTrue(fake.closed)

    def test_tv_error_raises(self):
        with self.assertRaises(tv.FrameError):
            tv.publish("10.0.0.5", "T0", b"JPEG", [], connector=FakeTV([art("error", error_code="-1")]))

    def test_failed_delete_is_kept_for_retry(self):
        fake = FakeTV([art("image_added", content_id="MY_F0012"), art("artmode_status", value="on")])
        result = tv.publish("10.0.0.5", "T0", b"JPEG", ["MY_F0011"], connector=fake)
        self.assertEqual(result["pending"], ["MY_F0011"])
        self.assertIsNotNone(result["delete_error"])

    def test_lost_connection_after_upload_keeps_all_ids(self):
        fake = FakeTV([art("image_added", content_id="MY_F0012")])

        def broken_send(text):
            raise ConnectionError("socket closed")

        fake.send = broken_send
        result = tv.publish("10.0.0.5", "T0", b"JPEG", ["MY_F0011", "MY_F0010"], connector=fake)
        self.assertEqual(result["content_id"], "MY_F0012")
        self.assertEqual(result["pending"], ["MY_F0011", "MY_F0010"])
        self.assertIn("Connection lost", result["delete_error"])
        self.assertTrue(fake.closed)

    def test_long_retry_list_is_kept_not_dropped(self):
        old = [f"MY_F{n:04d}" for n in range(1, 31)]
        replies = [art("image_added", content_id="MY_F0099"), art("artmode_status", value="on")]
        fake = FakeTV(replies + [art("image_deleted")] * tv.MAX_DELETES)
        result = tv.publish("10.0.0.5", "T0", b"JPEG", old, connector=fake)
        self.assertEqual(result["pending"], old[tv.MAX_DELETES:])
        self.assertIsNone(result["delete_error"])

    def test_refused_pairing_raises(self):
        fake = FakeTV([])
        fake.replies = [json.dumps({"event": "ms.channel.unauthorized"})]
        with self.assertRaises(tv.FrameError):
            tv.pair("10.0.0.5", connector=fake)


    def test_pairing_without_token_is_ok(self):
        fake = FakeTV([])
        fake.replies = [json.dumps({"event": "ms.channel.connect", "data": {}}), json.dumps({"event": "ms.channel.ready"})]
        self.assertEqual(tv.pair("10.0.0.5", connector=fake), "")
        self.assertNotIn("token=", fake.url)

    def test_pairing_without_ready_fails(self):
        fake = FakeTV([])
        fake.replies = [json.dumps({"event": "ms.channel.connect", "data": {}})] + [json.dumps({"event": "other"})] * 9
        with self.assertRaises(tv.FrameError):
            tv.pair("10.0.0.5", connector=fake)

    def test_total_time_limit_stops_a_chatty_tv(self):
        clock = Clock()
        fake = ChattyTV(clock)
        with mock.patch.object(tv.time, "monotonic", clock):
            with self.assertRaises(tv.FrameError) as caught:
                tv.publish("10.0.0.5", "T0", b"JPEG", [], connector=fake)
        self.assertIn("too long", str(caught.exception))
        self.assertLess(fake.reads, 5)
        self.assertTrue(fake.closed)

    def test_total_time_limit_stops_a_slow_handshake(self):
        clock = Clock()
        fake = ChattyTV(clock, replies=[json.dumps({"event": "ms.channel.connect", "data": {}})])
        fake.replies = fake.replies[2:]  # drop the scripted "ready": the TV never says it
        with mock.patch.object(tv.time, "monotonic", clock):
            with self.assertRaises(tv.FrameError):
                tv.pair("10.0.0.5", connector=fake)
        self.assertLess(fake.reads, 5)
        self.assertTrue(fake.closed)

    def test_confirmed_id_is_reported_at_once(self):
        class Stop(BaseException):
            """Stands for a call that never comes back."""

        fake = FakeTV([art("image_added", content_id="MY_F0012")])

        def hang(text):
            raise Stop()

        fake.send = hang
        confirmed = []
        with self.assertRaises(Stop):
            tv.publish("10.0.0.5", "T0", b"JPEG", ["MY_F0011"], connector=fake, confirmed=confirmed)
        self.assertEqual(confirmed, ["MY_F0012"])


if __name__ == "__main__":
    unittest.main()
