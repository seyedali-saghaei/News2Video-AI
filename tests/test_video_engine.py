import base64

from news2video_ai.video_engine import decode_base64_text, seconds_to_ass_time


def test_decodes_utf8_subtitle():
    encoded = base64.b64encode("خبر امروز".encode("utf-8")).decode("ascii")
    assert decode_base64_text(encoded) == "خبر امروز"


def test_ass_timestamp():
    assert seconds_to_ass_time(65.25) == "0:01:05.25"
