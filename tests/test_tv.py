"""Protocol checks for the built-in uploader with a fake TV (no network)."""
import importlib.util
import json
import unittest
from pathlib import Path

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


class UploaderTests(unittest.TestCase):
    def test_frame_layout(self):
        frame = tv.upload_frame(b"JPEG", "none")
        size = int.from_bytes(frame[:2], "big")
        header = json.loads(frame[2:2 + size])
        self.assertEqual(json.loads(header["params"]["data"])["request"], "send_image")
        self.assertEqual(frame[2 + size:], b"JPEG")

    def test_publish_uploads_shows_and_deletes_only_old_ids(self):
        fake = FakeTV([art("image_added", content_id="MY_F0012"), art("image_deleted"), art("image_deleted")])
        result = tv.publish("10.0.0.5", "T0", b"JPEG", ["MY_F0011", "MY_F0010"], connector=fake)
        self.assertEqual(result["content_id"], "MY_F0012")
        self.assertEqual(result["pending"], [])
        self.assertEqual(result["token"], "T1")
        self.assertIn("token=T0", fake.url)
        requests = [m["request"] for m in fake.sent]
        self.assertEqual(requests, ["select_image", "delete_image_list", "delete_image_list"])
        deleted = [m["content_id_list"][0]["content_id"] for m in fake.sent[1:]]
        self.assertEqual(deleted, ["MY_F0011", "MY_F0010"])
        self.assertTrue(fake.closed)

    def test_unconfirmed_upload_raises(self):
        fake = FakeTV([])
        with self.assertRaises(tv.FrameError):
            tv.publish("10.0.0.5", "T0", b"JPEG", [], connector=fake)
        self.assertTrue(fake.closed)

    def test_tv_error_raises(self):
        with self.assertRaises(tv.FrameError):
            tv.publish("10.0.0.5", "T0", b"JPEG", [], connector=FakeTV([art("error", error_code="-1")]))

    def test_failed_delete_is_kept_for_retry(self):
        fake = FakeTV([art("image_added", content_id="MY_F0012")])
        result = tv.publish("10.0.0.5", "T0", b"JPEG", ["MY_F0011"], connector=fake)
        self.assertEqual(result["pending"], ["MY_F0011"])
        self.assertIsNotNone(result["delete_error"])

    def test_refused_pairing_raises(self):
        fake = FakeTV([])
        fake.replies = [json.dumps({"event": "ms.channel.unauthorized"})]
        with self.assertRaises(tv.FrameError):
            tv.pair("10.0.0.5", connector=fake)


if __name__ == "__main__":
    unittest.main()
