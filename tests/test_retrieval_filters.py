from corpus.lexical import tokenize
from corpus.retrieval import matches_filters, metadata_value

ITEM = {
    "document_type": "legal",
    "source_file": "PflAPrV.html",
    "content_type": "kompetenz",
    "kompetenz_code": "I.1.h",
    "structure": {"section": "Anlage 2 (zu § 9 Absatz 1 Satz 2)", "unit": "2"},
}


def test_matches_top_level_and_nested_fields() -> None:
    assert matches_filters(ITEM, {"document_type": "LEGAL", "structure.unit": "2"})


def test_requires_all_filters_to_match() -> None:
    assert not matches_filters(ITEM, {"document_type": "legal", "source_file": "PflBG.html"})


def test_missing_nested_path_does_not_raise() -> None:
    assert metadata_value(ITEM, "structure.paragraph.deeper") is None


def test_filter_can_select_one_anlage() -> None:
    """Family B must be able to restrict retrieval to Anlage 2 alone."""
    assert matches_filters(ITEM, {"structure.unit": "2"})
    assert not matches_filters(ITEM, {"structure.unit": "1"})


def test_tokenize_strips_terminal_punctuation() -> None:
    assert tokenize("Was verlangt der Operator begründen?") == [
        "was", "verlangt", "der", "operator", "begründen",
    ]


def test_tokenize_keeps_german_characters() -> None:
    assert tokenize("Überprüfung, äußerste Maßstäbe!") == [
        "überprüfung", "äußerste", "maßstäbe",
    ]
