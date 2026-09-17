from news2video_ai.tts import normalize_for_tts, normalize_numbers_for_tts


def test_integer_is_expanded_in_persian():
    assert normalize_numbers_for_tts("سال 2026") == "سال دو هزار و بیست و شش"


def test_percentage_is_expanded():
    assert normalize_numbers_for_tts("12٪") == "دوازده درصد"


def test_known_german_name_is_pronunciation_friendly():
    assert "کارلْس‌روهِه" in normalize_for_tts("Karlsruhe")
