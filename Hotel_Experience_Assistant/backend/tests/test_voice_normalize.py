from app.voice.normalize import to_hindi_speech_text


def test_plain_numbers():
    assert to_hindi_speech_text("आपके पास 42 पॉइंट्स हैं।") == "आपके पास बयालीस पॉइंट्स हैं।"


def test_rupee_amount():
    assert to_hindi_speech_text("कुल ₹1,500 है।") == "कुल एक हज़ार पांच सौ रुपये है।"


def test_lakh():
    assert to_hindi_speech_text("₹150000") == "एक लाख पचास हज़ार रुपये"


def test_year():
    assert to_hindi_speech_text("15 अक्टूबर 2026 को") == "पंद्रह अक्टूबर दो हज़ार छब्बीस को"


def test_alphanumeric_code_spelled_out_character_by_character():
    assert (
        to_hindi_speech_text("बुकिंग SVH2K9F कन्फर्म है।")
        == "बुकिंग एस वी एच दो के नौ एफ कन्फर्म है।"
    )


def test_code_word_boundary_does_not_swallow_surrounding_punctuation():
    assert to_hindi_speech_text("रेफरेंस: 3F525P.") == "रेफरेंस: तीन एफ पांच दो पांच पी."


def test_zero():
    assert to_hindi_speech_text("बैलेंस 0 है।") == "बैलेंस शून्य है।"
