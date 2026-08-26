from app.lexical import tokenize


def test_tokenize_strips_terminal_punctuation() -> None:
    assert tokenize("Was verlangt der Operator begründen?") == [
        "was", "verlangt", "der", "operator", "begründen"
    ]


def test_tokenize_keeps_german_characters() -> None:
    assert tokenize("Überprüfung, äußerste Maßstäbe!") == [
        "überprüfung", "äußerste", "maßstäbe"
    ]
