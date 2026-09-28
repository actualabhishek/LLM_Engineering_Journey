from app.voice.sentences import split_sentences


def test_splits_on_punctuation():
    assert split_sentences("Hello! How are you? Fine.") == ["Hello!", "How are you?", "Fine."]


def test_splits_on_danda():
    assert split_sentences("नमस्ते। आप कैसे हैं?") == ["नमस्ते।", "आप कैसे हैं?"]


def test_drops_empty_and_strips():
    assert split_sentences("  One sentence only  ") == ["One sentence only"]


def test_empty_string():
    assert split_sentences("") == []
